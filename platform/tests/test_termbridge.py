"""Test termbridge: WebSocket <-> PTY, tanpa docker (shell diganti, cek container di-patch)."""
import json
import os
import re
import sys
import time
import unittest
from pathlib import Path
from concurrent.futures import CancelledError
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import termbridge
from instance import Instance

LAB = Path(__file__).resolve().parents[2] / "labs" / "net-001"
SHELL = ["bash", "--norc", "-i"]


class connect:
    """websocket_connect yang menelan CancelledError saat keluar.

    TestClient membatalkan task aplikasi segera setelah mengirim disconnect, jadi
    saat keluar `with` kadang CancelledError bocor. Itu artefak harness, bukan
    perilaku server asli; pembersihan proses tetap diperiksa lewat pid/_active.
    """

    def __init__(self, client, url):
        self.cm = client.websocket_connect(url)

    def __enter__(self):
        return self.cm.__enter__()

    def __exit__(self, *exc):
        try:
            return self.cm.__exit__(*exc)
        except CancelledError:
            return False


def inp(data):
    return json.dumps({"type": "input", "data": data})


def read_until(ws, needle, limit=50):
    buf = b""
    for _ in range(limit):
        buf += ws.receive_bytes()
        if needle in buf:
            return buf
    raise AssertionError(f"{needle!r} tidak muncul, dapat {buf!r}")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # zombie yang belum di-wait tetap dianggap hidup oleh kill(0)
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


class TermBridgeTest(unittest.TestCase):
    def setUp(self):
        self.inst = Instance(LAB, "local")
        self.node = next(iter(self.inst.topology["topology"]["nodes"]))
        app = FastAPI()
        app.include_router(termbridge.router)
        self.client = TestClient(app)
        self.url = f"/api/labs/net-001/term/{self.node}"
        self.patches = [
            mock.patch.object(termbridge, "_resolver", None),
            mock.patch.object(termbridge, "build_command", lambda i, n: SHELL),
            mock.patch.object(termbridge, "node_running", lambda i, n: n in i.topology["topology"]["nodes"]),
        ]
        for p in self.patches:
            p.start()
        termbridge.set_resolver(lambda ws, lab_id: self.inst)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        termbridge._active.clear()

    def close_code(self, url):
        with self.assertRaises(WebSocketDisconnect) as cm:
            with self.client.websocket_connect(url) as ws:
                ws.receive_bytes()
        return cm.exception.code

    def test_default_resolver_rejects(self):
        termbridge._resolver = None
        self.assertEqual(self.close_code(self.url), 4401)

    def test_resolver_none_and_async(self):
        termbridge.set_resolver(lambda ws, lab_id: None)
        self.assertEqual(self.close_code(self.url), 4401)

        async def deny(ws, lab_id):
            return None
        termbridge.set_resolver(deny)
        self.assertEqual(self.close_code(self.url), 4401)

    def test_invalid_or_unknown_node(self):
        self.assertEqual(self.close_code("/api/labs/net-001/term/NOPE"), 4404)
        self.assertEqual(self.close_code("/api/labs/net-001/term/tidak-ada"), 4404)

    def test_node_not_running(self):
        with mock.patch.object(termbridge, "node_running", lambda i, n: False):
            self.assertEqual(self.close_code(self.url), 4404)

    def test_node_running_validates_before_docker(self):
        with mock.patch.object(termbridge.subprocess, "run", side_effect=AssertionError("tidak boleh")):
            self.assertFalse(termbridge.node_running(self.inst, "../x"))
            self.assertFalse(termbridge.node_running(self.inst, "tidak-ada"))

    def test_echo_roundtrip_env_and_resize(self):
        with connect(self.client, self.url) as ws:
            ws.send_text(json.dumps({"type": "resize", "cols": 100, "rows": 30}))
            ws.send_text("bukan json")             # diabaikan
            ws.send_text(json.dumps({"type": "aneh"}))
            ws.send_text(json.dumps({"type": "resize", "cols": "x", "rows": -1}))
            ws.send_text(inp("echo LAB=$LAB_INSTANCE T=$TERM S=$(stty size)\n"))
            out = read_until(ws, b"T=xterm-256color S=30 100")
            self.assertIn(b"LAB=local", out)

    def test_process_exit_closes_with_1000(self):
        with connect(self.client, self.url) as ws:
            ws.send_text(inp("echo selesai-ya; exit\n"))
            read_until(ws, b"selesai-ya")
            with self.assertRaises(WebSocketDisconnect) as cm:
                while True:
                    ws.receive_bytes()
            self.assertEqual(cm.exception.code, 1000)

    def test_process_killed_when_websocket_closes(self):
        with connect(self.client, self.url) as ws:
            ws.send_text(inp("echo PID=$$=\n"))
            out = b""
            while not re.search(rb"PID=(\d+)=", out):
                out += ws.receive_bytes()
            pid = int(re.search(rb"PID=(\d+)=", out).group(1))
            self.assertTrue(alive(pid))
        for _ in range(60):
            if not alive(pid):
                break
            time.sleep(0.1)
        self.assertFalse(alive(pid))
        self.assertEqual(termbridge._active, {})

    def test_reap_escalates_to_sigkill(self):
        # Proses yang mengabaikan SIGHUP tetap harus mati setelah KILL_GRACE.
        import asyncio
        master, proc = termbridge._spawn(["bash", "-c", "trap '' HUP; echo siap; while :; do sleep 0.1; done"], dict(os.environ))
        for _ in range(50):          # tunggu trap terpasang
            time.sleep(0.05)
            try:
                if b"siap" in os.read(master, 100):
                    break
            except BlockingIOError:
                pass
        termbridge._signal_group(proc, termbridge.signal.SIGHUP)
        time.sleep(0.2)
        self.assertTrue(alive(proc.pid))
        with mock.patch.object(termbridge, "KILL_GRACE", 0.3):
            asyncio.run(termbridge._reap(proc, master))
        self.assertFalse(alive(proc.pid))

    def test_limit_per_instance(self):
        with mock.patch.object(termbridge, "MAX_PER_INSTANCE", 2):
            with connect(self.client, self.url) as a, connect(self.client, self.url) as b:
                for ws in (a, b):
                    ws.send_text(inp("echo ok\n"))
                    read_until(ws, b"ok")
                self.assertEqual(self.close_code(self.url), 4429)
            # setelah ditutup, slot kembali
            for _ in range(50):
                if not termbridge._active:
                    break
                time.sleep(0.1)
            with connect(self.client, self.url) as c:
                c.send_text(inp("echo lagi\n"))
                read_until(c, b"lagi")

    def test_input_long_paste_arrives_whole(self):
        # 256 KiB jauh di atas buffer PTY: harus tertulis utuh, tidak terpotong diam-diam.
        # Baris pendek + newline: mode kanonik membatasi baris ke 4096 byte.
        with connect(self.client, self.url) as ws:
            ws.send_text(inp("stty -echo; echo REA''DY\n"))
            read_until(ws, b"READY\r\n")
            line = "x" * 63 + "\n"
            ws.send_text(inp("wc -c\n"))
            ws.send_text(inp(line * 4096))        # 262144 byte
            ws.send_text(inp("\x04"))
            read_until(ws, b"262144", limit=200)

    def test_pending_input_is_bounded(self):
        # Shell yang tidak membaca: input berlebih dibuang, server tidak menumpuk memori.
        with mock.patch.object(termbridge, "MAX_PENDING_INPUT", 1024), \
                mock.patch.object(termbridge, "build_command", lambda i, n: ["sleep", "30"]):
            with connect(self.client, self.url) as ws:
                for _ in range(20):
                    ws.send_text(inp("y" * 60000))
                ws.send_text(inp("z"))     # tetap tidak error

    def test_env_is_allowlisted(self):
        with mock.patch.dict(os.environ, {"LAB_LLM_API_KEY": "rahasia-x", "OPENAI_API_KEY": "rahasia-y",
                                          "LC_ALL": "C", "DOCKER_HOST": "unix:///tmp/d.sock"}):
            with connect(self.client, self.url) as ws:
                ws.send_text(inp("echo K1=[$LAB_LLM_API_KEY] K2=[$OPENAI_API_KEY] I=$LAB_INSTANCE"
                                 " D=$DOCKER_HOST C=$LC_ALL H=${HOME:+ada} P=${PATH:+ada}\n"))
                out = read_until(ws, b"P=ada")
        self.assertIn(b"K1=[] K2=[] I=local D=unix:///tmp/d.sock C=C H=ada", out)

    def test_build_env_keeps_lab_config(self):
        # lab-shell membaca config lagi; tanpa ini lokasi state instance salah untuk LAB_CONFIG custom.
        inst = Instance(LAB, "local")
        with mock.patch.dict(os.environ, {"LAB_CONFIG": "/x/server.yaml"}):
            self.assertEqual(termbridge.build_env(inst)["LAB_CONFIG"], "/x/server.yaml")

    def test_build_env_has_no_server_secrets(self):
        with mock.patch.dict(os.environ, {"LAB_LLM_API_KEY": "rahasia-x"}):
            env = termbridge.build_env(self.inst)
        self.assertNotIn("LAB_LLM_API_KEY", env)
        self.assertEqual(env["LAB_INSTANCE"], "local")
        self.assertEqual(env["TERM"], "xterm-256color")
        self.assertIn("LAB_STATE_DIR", env)

    def test_controlling_tty_and_sigint(self):
        for no_setsid in (False, True):     # setsid util-linux, dan fallback python
            with self.subTest(no_setsid=no_setsid):
                patch = mock.patch.object(termbridge.shutil, "which", lambda n: None) if no_setsid \
                    else mock.patch.object(termbridge.shutil, "which", termbridge.shutil.which)
                with patch, connect(self.client, self.url) as ws:
                    ws.send_text(inp("test -t 0 && echo ISTTY; ps -o tpgid= -p $$ | tr -d ' ' | sed 's/^/TPGID=/'; "
                                     "echo SID=$(ps -o sid= -p $$ | tr -d ' ') PID=$$\n"))
                    out = read_until(ws, b"PID=")
                    self.assertIn(b"ISTTY", out)
                    self.assertNotIn(b"TPGID=-1", out)
                    # Ctrl-C menghentikan perintah di foreground, shell tetap hidup
                    ws.send_text(inp("sleep 30\n"))
                    time.sleep(0.3)
                    ws.send_text(inp("\x03"))
                    ws.send_text(inp("echo SETELAH-$((1+1))\n"))
                    read_until(ws, b"SETELAH-2")

    def test_backpressure_bounds_queue_and_resumes(self):
        # Proses `yes` + klien yang tidak membaca: antrean berhenti di batas, PTY ditahan.
        sizes = []
        real_put = termbridge.asyncio.Queue.put_nowait

        def spy(q, item):
            real_put(q, item)
            sizes.append(q.qsize())

        with mock.patch.object(termbridge.asyncio.Queue, "put_nowait", spy), \
                mock.patch.object(termbridge, "OUT_QUEUE_MAX", 4), \
                mock.patch.object(termbridge, "build_command", lambda i, n: ["yes"]):
            with connect(self.client, self.url) as ws:
                time.sleep(1.0)          # klien tidak membaca; TestClient menampung di sisinya
                # TestClient memiliki antrean tak berbatas di sisi klien, jadi cukup periksa
                # sisi server: tidak ada put melebihi batas.
                self.assertLessEqual(max(sizes), 4)
                n = 0
                for _ in range(20):      # setelah klien membaca, output mengalir lagi
                    n += len(ws.receive_bytes())
                self.assertGreater(n, 0)

    def test_backpressure_holds_pty_when_sender_stalls(self):
        # Pengirim websocket diblok: reader harus dilepas, bukan membaca terus.
        import asyncio
        reads = []
        real_read = os.read

        def counting_read(fd, n):
            data = real_read(fd, n)
            reads.append(len(data))
            return data

        gate = {"open": False}

        async def run():
            class WS:
                path_params = {"lab_id": "x"}

                async def send_bytes(self, b):
                    while not gate["open"]:
                        await asyncio.sleep(0.05)

                async def receive(self):
                    await asyncio.sleep(3600)

            master, proc = termbridge._spawn(["yes"], dict(os.environ))
            loop = asyncio.get_running_loop()
            with mock.patch.object(termbridge, "OUT_QUEUE_MAX", 4), mock.patch.object(termbridge.os, "read", counting_read):
                task = asyncio.create_task(termbridge._pump(WS(), loop, master, proc))
                await asyncio.sleep(0.5)
                n1 = len(reads)
                await asyncio.sleep(0.5)
                self.assertEqual(len(reads), n1)       # berhenti membaca
                self.assertLessEqual(n1, 4 + 2)        # antrean 4 + 1 in-flight
                gate["open"] = True
                await asyncio.sleep(0.5)
                self.assertGreater(len(reads), n1)     # mengalir lagi
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            termbridge._release(loop, master, proc)
            await asyncio.gather(*termbridge._reapers)
            self.assertFalse(alive(proc.pid))

        asyncio.run(run())

    def test_exit_while_reader_paused_still_closes(self):
        # Proses selesai saat reader dilepas (antrean penuh): EOF tetap terdeteksi setelah dikuras.
        with mock.patch.object(termbridge, "OUT_QUEUE_MAX", 2), \
                mock.patch.object(termbridge, "READ_CHUNK", 1024), \
                mock.patch.object(termbridge, "build_command",
                                  lambda i, n: ["bash", "-c", "head -c 100000 /dev/zero; echo TAMAT"]):
            with connect(self.client, self.url) as ws:
                time.sleep(0.5)
                buf = b""
                with self.assertRaises(WebSocketDisconnect) as cm:
                    while True:
                        buf += ws.receive_bytes()
                self.assertEqual(cm.exception.code, 1000)
                self.assertIn(b"TAMAT", buf)

    def test_recheck_closes_with_4401_and_kills(self):
        calls = []

        def resolver(ws, lab_id):
            calls.append(1)
            return self.inst if len(calls) == 1 else None

        termbridge.set_resolver(resolver)
        with mock.patch.object(termbridge, "RECHECK_INTERVAL", 0.3):
            with connect(self.client, self.url) as ws:
                ws.send_text(inp("echo PID=$$=\n"))
                out = b""
                while not re.search(rb"PID=(\d+)=\r", out):
                    out += ws.receive_bytes()
                pid = int(re.search(rb"PID=(\d+)=\r", out).group(1))
                with self.assertRaises(WebSocketDisconnect) as cm:
                    while True:
                        ws.receive_bytes()
                self.assertEqual(cm.exception.code, 4401)
        for _ in range(60):
            if not alive(pid):
                break
            time.sleep(0.1)
        self.assertFalse(alive(pid))
        self.assertEqual(termbridge._active, {})

    def test_recheck_different_instance_closes(self):
        other = Instance(LAB, "orang-lain")
        calls = []
        termbridge.set_resolver(lambda ws, lab_id: self.inst if not calls.append(1) and len(calls) == 1 else other)
        with mock.patch.object(termbridge, "RECHECK_INTERVAL", 0.2):
            with connect(self.client, self.url) as ws:
                with self.assertRaises(WebSocketDisconnect) as cm:
                    while True:
                        ws.receive_bytes()
                self.assertEqual(cm.exception.code, 4401)

    def test_recheck_ok_keeps_terminal(self):
        with mock.patch.object(termbridge, "RECHECK_INTERVAL", 0.2):
            with connect(self.client, self.url) as ws:
                time.sleep(0.7)
                ws.send_text(inp("echo MASIH-HIDUP\n"))
                read_until(ws, b"MASIH-HIDUP")


if __name__ == "__main__":
    unittest.main()
