#!/usr/bin/env python3
"""Jembatan terminal: WebSocket <-> PTY yang menjalankan lab-shell.

Pengganti ttyd. Browser (xterm.js, web/src/components/Terminal.tsx) membuka
WebSocket same-origin ke /api/labs/{lab_id}/term/{node}; cookie login ikut
otomatis, jadi tidak ada port tambahan dan tidak ada terminal tanpa auth.

Perekaman tidak diubah di sini: yang dijalankan tetap `lab-shell <problem_dir>
<node>` (script -> .state/tty/, hook bash / ros.py shell -> events). Modul ini
hanya memindahkan byte.

Protokol:
  server -> client   frame binary = output PTY mentah
  client -> server   frame text JSON:
                       {"type": "input", "data": "..."}
                       {"type": "resize", "cols": N, "rows": M}
                     pesan lain diabaikan.
Close code: 1000 proses selesai, 4401 tidak berhak (resolver), 4404 node tidak
valid / tidak berjalan, 4429 terlalu banyak terminal untuk instance ini.

Siapa yang boleh membuka terminal (cookie, Origin, kepemilikan lab) diputuskan
resolver yang didaftarkan server.py lewat set_resolver(). Default: tolak semua,
jadi lupa mendaftarkan tidak membuka terminal ke siapa pun.
"""

import asyncio
import fcntl
import inspect
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import termios
from pathlib import Path

from fastapi import APIRouter, WebSocket

HERE = Path(__file__).resolve().parent
NODE_RX = re.compile(r"^[a-z0-9-]+$")      # sama dengan lab-shell
MAX_PER_INSTANCE = 8     # tab dibuka-tutup tidak boleh menumpuk proses
KILL_GRACE = 2.0         # detik antara SIGHUP dan SIGKILL
READ_CHUNK = 65536
OUT_QUEUE_MAX = 32       # potongan output tertunda per terminal (<= 2 MiB); penuh = PTY ditahan
MAX_INPUT = 1 << 20      # batas satu frame input; paste normal jauh di bawah ini
MAX_PENDING_INPUT = 2 << 20   # total input yang belum tertulis ke PTY; lebihnya dibuang
RECHECK_INTERVAL = 60.0  # detik antar cek ulang login (logout / akun dinonaktifkan)
# Env yang boleh sampai ke shell pemain. Env server (LAB_LLM_API_KEY, kunci provider
# lain, dst.) sengaja tidak ikut: pemain bisa menjalankan `env` di shell itu.
ENV_ALLOW = ("PATH", "HOME", "LANG", "USER", "LOGNAME",
             "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT",   # docker CLI dipakai lab-shell/ros.py
             "LAB_CONFIG")   # lab-shell membaca config lagi untuk lokasi state instance
DEFAULT_SIZE = (80, 24)

router = APIRouter()
_resolver = None
_active = {}             # (user, problem_dir) -> jumlah terminal terbuka


def set_resolver(fn):
    """fn(websocket, lab_id) -> Instance | None, sync atau async. None = tolak (4401)."""
    global _resolver
    _resolver = fn


def build_command(instance, node):
    """Perintah yang dijalankan di PTY. Titik injeksi untuk test."""
    return [str(HERE / "lab-shell"), str(instance.problem_dir), node]


def node_running(instance, node):
    """Node ada di topologi instance dan container-nya berjalan."""
    if not NODE_RX.fullmatch(node):
        return False
    nodes = (instance.topology.get("topology") or {}).get("nodes") or {}
    if node not in nodes:
        return False
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", instance.container(node)],
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.stdout.strip() == "true"


def _set_size(fd, cols, rows):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


# Fallback kalau `setsid` (util-linux) tidak ada: jadikan sesi baru, pasang tty di fd 0, exec.
_SETSID_PY = ("import os,sys,fcntl,termios;os.setsid();"
              "fcntl.ioctl(0,termios.TIOCSCTTY,0);os.execvp(sys.argv[1],sys.argv[1:])")


def build_env(instance):
    """Env minimal untuk shell pemain: allowlist + env instance (kontrak labenv.sh)."""
    base = {k: v for k, v in os.environ.items() if k in ENV_ALLOW or k.startswith("LC_")}
    base.setdefault("PATH", os.defpath)
    env = instance.env(base)    # base != None → tidak menyalin os.environ
    env["TERM"] = "xterm-256color"
    return env


def _spawn(argv, env):
    """Proses di PTY baru: sesi sendiri dengan slave sebagai controlling tty.

    Tidak memakai preexec_fn (tidak aman di proses berthread: uvicorn + to_thread bisa
    memegang lock saat fork) dan tidak start_new_session. Anak Popen bukan pemimpin
    grup, jadi program `setsid -c` bisa memanggil setsid() tanpa fork (pid tetap,
    pid = sid = pgid) lalu TIOCSCTTY pada fd 0 (slave) sebelum exec. `script` di
    lab-shell butuh tty kendali yang benar untuk job control dan SIGINT (Ctrl-C).
    """
    if shutil.which("setsid"):
        full = ["setsid", "-c", *argv]
    else:
        full = [sys.executable, "-c", _SETSID_PY, *argv]
    master, slave = os.openpty()
    try:
        _set_size(master, *DEFAULT_SIZE)
        proc = subprocess.Popen(full, stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
    except BaseException:
        os.close(master)
        raise
    finally:
        os.close(slave)   # tinggal proses anak yang memegang slave: EOF/EIO = proses selesai
    os.set_blocking(master, False)
    return master, proc


def _signal_group(proc, sig):
    try:
        os.killpg(proc.pid, sig)     # pid = pgid setelah setsid di anak
    except ProcessLookupError:
        # Grup belum ada: anak belum sempat setsid. Kirim ke prosesnya saja.
        if proc.returncode is None:
            try:
                os.kill(proc.pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
    except PermissionError:
        pass


async def _reap(proc, master):
    """SIGHUP sudah dikirim; SIGKILL ke seluruh grup kalau belum mati setelah KILL_GRACE, lalu panen."""
    try:
        for _ in range(int(KILL_GRACE / 0.05)):
            if proc.poll() is not None:
                break
            await asyncio.sleep(0.05)
        _signal_group(proc, signal.SIGKILL)   # sisa anak di grup yang sama ikut
        await asyncio.get_running_loop().run_in_executor(None, proc.wait)
    finally:
        os.close(master)


_reapers = set()


def _release(loop, master, proc):
    """Bersihkan tanpa await di jalur handler: handler bisa dibatalkan kapan saja
    (server ditutup, klien putus saat cleanup), sehingga bagian yang wajib jalan
    dilakukan sinkron, dan eskalasi SIGKILL berjalan sebagai task terpisah."""
    try:
        loop.remove_reader(master)
    except Exception:
        pass
    if proc.poll() is None:
        _signal_group(proc, signal.SIGHUP)
    task = loop.create_task(_reap(proc, master))
    _reapers.add(task)
    task.add_done_callback(_reapers.discard)


async def _call(fn, *args):
    result = fn(*args)
    return await result if inspect.isawaitable(result) else result


@router.websocket("/api/labs/{lab_id}/term/{node}")
async def terminal(websocket: WebSocket, lab_id: str, node: str):
    await websocket.accept()      # ditolak dengan close code (browser tidak melihat code sebelum accept)
    try:
        instance = await _call(_resolver, websocket, lab_id) if _resolver else None
    except Exception:
        instance = None
    if instance is None:
        await websocket.close(4401)
        return
    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, node_running, instance, node):
        await websocket.close(4404)
        return
    key = (instance.user, str(instance.problem_dir))
    if _active.get(key, 0) >= MAX_PER_INSTANCE:
        await websocket.close(4429)
        return
    _active[key] = _active.get(key, 0) + 1
    master = proc = None
    code = 1000
    try:
        master, proc = _spawn(build_command(instance, node), build_env(instance))
        code = await _pump(websocket, loop, master, proc, instance)
    finally:
        if proc is not None:
            _release(loop, master, proc)
        _active[key] -= 1
        if _active[key] <= 0:
            del _active[key]
    try:
        await websocket.close(code)
    except Exception:
        pass   # sudah tertutup (klien putus)


async def _pump(websocket, loop, master, proc, instance=None):
    """Pindahkan byte dua arah. Mengembalikan close code (1000 selesai, 4401 sesi berakhir)."""
    out = asyncio.Queue(maxsize=OUT_QUEUE_MAX)   # potongan output; None = PTY habis
    reading = False      # reader master terpasang?
    eof = False
    pending = bytearray()   # input belum tertulis ke PTY
    writing = False
    result = [1000]

    def start_reader():
        nonlocal reading
        if not reading and not eof:
            loop.add_reader(master, on_readable)
            reading = True

    def stop_reader():
        nonlocal reading
        if reading:
            loop.remove_reader(master)
            reading = False

    def on_readable():
        # Backpressure: antrean penuh = lepas reader, kernel buffer PTY terisi, lalu
        # proses penulis (mis. `yes`) ikut blok. to_client memasang lagi setelah menguras.
        nonlocal eof
        if out.full():
            stop_reader()
            return
        try:
            data = os.read(master, READ_CHUNK)
        except BlockingIOError:
            return
        except OSError:      # EIO: semua pemegang slave sudah keluar
            data = b""
        if not data:
            eof = True
            stop_reader()
            if out.full():   # tidak ada slot untuk sentinel: to_client yang mengirimnya
                return
            out.put_nowait(None)
            return
        out.put_nowait(data)
        if out.full():
            stop_reader()

    def flush_input():
        nonlocal writing
        while pending:
            try:
                n = os.write(master, pending)
            except BlockingIOError:
                break
            except OSError:
                pending.clear()
                break
            del pending[:n]
        if pending and not writing:
            loop.add_writer(master, flush_input)
            writing = True
        elif not pending and writing:
            loop.remove_writer(master)
            writing = False

    def queue_input(data):
        # Tulis sampai habis: os.write ke PTY non-blocking bisa parsial (paste panjang).
        if len(pending) + len(data) > MAX_PENDING_INPUT:
            return      # kebanjiran (klien/skrip nakal): buang daripada menumpuk memori
        pending.extend(data)
        flush_input()

    start_reader()

    async def to_client():
        nonlocal eof
        while True:
            chunk = await out.get()
            if chunk is None:
                return
            await websocket.send_bytes(chunk)
            if eof and out.empty():
                return
            if not reading and not eof and out.qsize() <= OUT_QUEUE_MAX // 2:
                start_reader()   # sudah terkuras: lanjut baca; EOF/EIO terdeteksi di sini

    async def from_client():
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                return
            text = msg.get("text")
            if text is None or len(text) > MAX_INPUT:
                continue
            try:
                body = json.loads(text)
            except ValueError:
                continue
            if not isinstance(body, dict):
                continue
            if body.get("type") == "input" and isinstance(body.get("data"), str):
                queue_input(body["data"].encode())
            elif body.get("type") == "resize":
                cols, rows = body.get("cols"), body.get("rows")
                if all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 1000 for v in (cols, rows)):
                    try:
                        _set_size(master, cols, rows)
                    except OSError:
                        pass

    async def recheck():
        # Terminal yang sudah terbuka tidak boleh hidup setelah logout / akun dinonaktifkan.
        # Resolver yang sama dengan saat connect; gagal/None/instance lain = putus (fail closed).
        if instance is None or _resolver is None:
            await asyncio.Event().wait()
        ident = (instance.user, str(instance.problem_dir))
        while True:
            await asyncio.sleep(RECHECK_INTERVAL)
            try:
                now = await _call(_resolver, websocket, lab_id_of(websocket))
            except Exception:
                now = None
            if now is None or (now.user, str(now.problem_dir)) != ident:
                result[0] = 4401
                try:
                    await websocket.send_bytes(b"\r\n[sesi berakhir, terminal ditutup]\r\n")
                except Exception:
                    pass
                return

    tasks = [asyncio.create_task(to_client()), asyncio.create_task(from_client()),
             asyncio.create_task(recheck())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for fn in (loop.remove_reader, loop.remove_writer):
            try:
                fn(master)
            except Exception:
                pass
    return result[0]


def lab_id_of(websocket):
    return websocket.path_params.get("lab_id", "")
