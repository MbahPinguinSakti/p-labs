"""Test API web UI (server.py) tanpa menjalankan HTTP server.

Fokus utamanya kebocoran: browser tidak boleh menerima ground truth, parameter
soal, nama/bukti checkpoint tersembunyi, atau teks hint yang belum dibuka.
Sesi live dibuat dari salinan golden di direktori sementara (LAB_LABS_DIR), jadi
tidak menyentuh labs/ asli dan tidak butuh docker (running_nodes boleh None).
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
LABS = PLATFORM.parent / "labs"
GOLDEN = LABS / "net-001" / "golden" / "20261103-023553"  # jalan pintas: hint 1 dibuka

TMP = Path(tempfile.mkdtemp(prefix="plab-test-"))
os.environ["LAB_LABS_DIR"] = str(TMP)
sys.path.insert(0, str(PLATFORM))

import server  # noqa: E402


def setUpModule():
    lab = TMP / "net-001"
    shutil.copytree(LABS / "net-001", lab, ignore=shutil.ignore_patterns(".state", "sessions", "clab-*"))
    # Sesi "aktif": golden tanpa evaluation.json.
    shutil.copytree(GOLDEN, lab / ".state", ignore=shutil.ignore_patterns("evaluation.*", "expected.yaml", "notes.md"))


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class TestLiveState(unittest.TestCase):
    def setUp(self):
        self.state = server.live_state("net-001")
        self.text = json.dumps(self.state)

    def test_active_session(self):
        self.assertEqual(self.state["session"], "20261103-023553")
        self.assertFalse(self.state["evaluated"])
        self.assertGreater(self.state["commands"], 0)
        self.assertEqual(self.state["activity"][0]["id"], "E6")  # terbaru di atas

    def test_no_ground_truth(self):
        truth = json.loads((GOLDEN / "ground_truth.json").read_text())
        self.assertNotIn("ground_truth", self.text)
        self.assertNotIn("faulty_switch", self.text)
        self.assertNotIn(truth.get("description", "@@"), self.text)

    def test_hidden_checkpoint(self):
        hidden = [c for c in self.state["checkpoints"] if c["hidden"]]
        self.assertEqual(len(hidden), 1)
        self.assertIsNone(hidden[0]["id"])
        self.assertEqual(hidden[0]["label"], "Checkpoint tersembunyi")
        self.assertNotIn("evidence", hidden[0])
        self.assertNotIn("locate_fault", self.text)
        self.assertEqual(hidden[0]["status"], "hit")  # tetap terlihat bahwa tercapai

    def test_hint_text_only_when_opened(self):
        hints = {h["level"]: h for h in self.state["hints"]}
        self.assertTrue(hints[1]["opened"])
        self.assertIsNotNone(hints[1]["text"])
        self.assertFalse(hints[2]["opened"])
        self.assertIsNone(hints[2]["text"])
        self.assertNotIn("sw2", hints[1]["text"] or "")


class TestHint(unittest.TestCase):
    def test_open_next_level(self):
        events = TMP / "net-001" / ".state" / "events" / "host.jsonl"
        before = events.read_text()
        try:
            opened = server.hint("net-001", server.HintRequest())
            self.assertEqual(opened["level"], 2)
            self.assertTrue(opened["new"])
            again = server.hint("net-001", server.HintRequest(level=2))
            self.assertFalse(again["new"])  # dibuka ulang: tanpa penalti tambahan
            self.assertEqual(events.read_text().count('"type": "hint"'), before.count('"type": "hint"') + 1)
        finally:
            events.write_text(before)


class TestCatalog(unittest.TestCase):
    def test_lab_card(self):
        card = server.labs()[0]
        self.assertEqual(card["id"], "net-001")
        self.assertEqual(card["active_session"], "20261103-023553")
        self.assertEqual(card["checkpoints_total"], 4)  # llm_judge tidak dihitung

    def test_lab_detail_has_design_labels(self):
        detail = server.lab_detail("net-001")
        labels = {(l["a"], l["b"]): l["label"] for l in detail["topology"]["links"]}
        self.assertEqual(labels[("sw1", "sw2")], "trunk · VLAN 10, 20")
        self.assertNotIn("<!-- cli", detail["brief"]["markdown"])
        self.assertNotIn("lab-hint", detail["brief"]["markdown"])
        self.assertEqual(detail["brief"]["ticket_title"], "host-a tidak bisa menjangkau host-b")

    def test_golden_result_reveals_everything(self):
        result = server.session_result("net-001", "20261019-234339")
        self.assertEqual(result["kind"], "golden")
        self.assertIn("locate_fault", result["checkpoint_labels"])
        self.assertNotIn("llm_runs", result["result"])
        self.assertEqual(result["timeline"][0]["id"], "E1")

    def test_leaderboard_ranks_goldens(self):
        board = server.leaderboard()
        golden_points = [e["points"] for e in board if e.get("golden")]
        self.assertEqual(golden_points, sorted(golden_points, reverse=True))
        self.assertEqual(sum(1 for e in board if e["you"]), 1)


class TestUnarmedSession(unittest.TestCase):
    """session_id tanpa ground_truth.json = sisa deploy/inject yang gagal, bukan sesi aktif."""

    def setUp(self):
        self.truth = TMP / "net-001" / ".state" / "ground_truth.json"
        self.aside = self.truth.with_suffix(".bak")
        self.truth.rename(self.aside)

    def tearDown(self):
        self.aside.rename(self.truth)

    def test_not_shown_as_active(self):
        self.assertIsNone(server.live_state("net-001")["session"])

    def test_evaluate_refused(self):
        with self.assertRaises(server.HTTPException) as ctx:
            server.evaluate_session("net-001", server.EvaluateRequest(use_llm=False))
        self.assertEqual(ctx.exception.status_code, 409)


class TestDeploy(unittest.TestCase):
    """DeployJobs menjalankan reset.sh; di sini reset.sh palsu (tanpa containerlab)."""

    def make_lab(self, script):
        lab = Path(tempfile.mkdtemp(prefix="plab-deploy-", dir=TMP))
        reset = lab / "reset.sh"
        reset.write_text("#!/usr/bin/env bash\n" + script)
        reset.chmod(0o755)
        return lab

    def run_job(self, lab):
        job = {"status": "running", "step": None, "started": 0, "error": None, "log": []}
        server.DEPLOYS._run(job, lab)  # sinkron, tanpa thread
        return job

    def test_steps_and_done(self):
        job = self.run_job(self.make_lab('echo "==> destroy"\necho "==> deploy"\necho "\x1b[32mok\x1b[0m"\n'))
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["log"], ["ok"])  # warna ANSI dibuang

    def test_error_shows_tail(self):
        job = self.run_job(self.make_lab('echo "==> deploy"\necho "permission denied" >&2\nexit 1\n'))
        self.assertEqual(job["status"], "error")
        self.assertIn("permission denied", job["error"])

    def test_inject_error_hides_output(self):
        job = self.run_job(self.make_lab('echo "==> inject"\necho "sw2 eth2 vid 20" >&2\nexit 1\n'))
        self.assertEqual(job["status"], "error")
        self.assertNotIn("sw2", job["error"])  # output inject bisa membocorkan lokasi fault

    def test_endpoint_refuses_without_support(self):
        original = server.deploy_support
        server.deploy_support = lambda: {"available": False, "mode": None, "reason": "butuh setup"}
        try:
            with self.assertRaises(server.HTTPException) as ctx:
                server.deploy("net-001")
            self.assertEqual(ctx.exception.status_code, 409)
        finally:
            server.deploy_support = original


@unittest.skipUnless(shutil.which("ttyd"), "ttyd tidak terinstall")
class TestTtydPort(unittest.TestCase):
    """Port ttyd yang sudah dipakai proses lain (mis. service `ttyd` bawaan
    Ubuntu yang menjalankan `login`) tidak boleh dipakai ulang."""

    def run_ttyd(self, *args):
        import socket
        import subprocess
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        proc = subprocess.Popen(["ttyd", "-i", "lo", "-p", str(port), *args],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        for _ in range(50):
            if server.port_open(port):
                break
            time.sleep(0.05)
        return port

    def test_foreign_ttyd_is_not_reused(self):
        port = self.run_ttyd("login")   # seperti service ttyd bawaan Debian/Ubuntu
        self.assertTrue(server.port_open(port))
        self.assertFalse(server.lab_ttyd_on(port, TMP / "net-001"))
        self.assertNotEqual(server.free_port(port), port)

    def test_lab_ttyd_for_same_lab_is_reused(self):
        lab = TMP / "net-001"
        port = self.run_ttyd("-W", "-a", str(server.HERE / "lab-shell"), str(lab))   # seperti platform/serve
        self.assertTrue(server.lab_ttyd_on(port, lab))
        self.assertFalse(server.lab_ttyd_on(port, TMP / "lab-lain"))


if __name__ == "__main__":
    unittest.main()
