"""Test kapasitas mode Server (capacity.py) tanpa docker dan containerlab.

Yang diuji: perkiraan RAM (default dari topologi vs resources.mem_mb), penolakan
saat RAM penuh, slot max_deploys dari banyak thread, kebijakan satu lab per user,
kandidat idle dan orphan, pemetaan nama lab docker -> instance, dan destroy()
yang memanggil reset-lab --destroy-only dengan env instance.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PLATFORM = Path(__file__).resolve().parent.parent
LABS = PLATFORM.parent / "labs"
sys.path.insert(0, str(PLATFORM))

import capacity  # noqa: E402
import instance  # noqa: E402
from config import Capacity as CapConfig  # noqa: E402
from instance import Instance  # noqa: E402


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="plab-capacity-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patcher = mock.patch.object(instance, "INSTANCES_DIR", self.tmp / "instances")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.names = set()      # "docker ps": nama lab containerlab yang berjalan

    def cap(self, mem_mb=24000, max_deploys=2, idle_minutes=30):
        return capacity.Capacity(CapConfig(mem_mb, max_deploys, idle_minutes), list_running=lambda: set(self.names))

    def inst(self, lab_id, user):
        return Instance(LABS / lab_id, user)


class TestEstimate(Case):
    def test_override_from_problem(self):
        self.assertEqual(capacity.estimate(self.inst("net-001", "a")), 150)
        self.assertEqual(capacity.estimate(self.inst("net-002", "a")), 900)
        self.assertEqual(capacity.estimate(self.inst("net-003", "a")), 1300)

    def test_default_from_topology(self):
        inst = self.inst("net-003", "a")
        inst.problem = {k: v for k, v in inst.problem.items() if k != "resources"}
        self.assertEqual(capacity.estimate(inst), 3 * 400 + 2 * 30)
        self.assertEqual(capacity.estimate_topology(self.inst("net-001", "a").topology), 5 * 30)
        # Tabel per kind bisa ditimpa; kind tak dikenal = DEFAULT_KIND_MB.
        self.assertEqual(capacity.estimate(inst, {"mikrotik_ros": 1000}), 3 * 1000 + 2 * 30)
        topo = {"topology": {"groups": {"g": {"kind": "srl"}}, "nodes": {"x": {"group": "g"}, "y": {}}}}
        self.assertEqual(capacity.estimate_topology(topo), capacity.DEFAULT_KIND_MB + 30)

    def test_override_is_preferred_even_if_lower(self):
        inst = self.inst("net-002", "a")
        inst.problem = {**inst.problem, "resources": {"mem_mb": 10}}
        self.assertEqual(capacity.estimate(inst), 10)


class TestMapping(Case):
    def test_names_to_instances(self):
        index = capacity.lab_index(LABS)
        self.assertEqual(index["net001"], LABS / "net-001")
        self.assertEqual(capacity.instance_for("net002-alice", index), self.inst("net-002", "alice"))
        self.assertEqual(capacity.instance_for("net003", index), self.inst("net-003", "local"))
        self.assertEqual(capacity.instance_for("net001-user-01", index).user, "user-01")
        for foreign in ("srl01", "net009-a", "net001-BAD", "net001-"):
            self.assertIsNone(capacity.instance_for(foreign, index), foreign)

    def test_running_ignores_foreign_labs(self):
        self.names = {"net001-a", "net002-b", "other-lab"}
        self.assertEqual(self.cap().running(), {self.inst("net-001", "a"), self.inst("net-002", "b")})

    def test_docker_command(self):
        done = subprocess.CompletedProcess([], 0, stdout="net001-a\nnet001-a\nnet002\n", stderr="")
        with mock.patch.object(capacity.subprocess, "run", return_value=done) as run:
            self.assertEqual(capacity.docker_lab_names(), {"net001-a", "net002"})
            self.assertIn("label=containerlab", run.call_args.args[0])
            self.assertNotIn("-a", run.call_args.args[0])
            capacity.docker_lab_names(include_stopped=True)
            self.assertIn("-a", run.call_args.args[0])
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="permission denied")
        with mock.patch.object(capacity.subprocess, "run", return_value=failed):
            self.assertRaises(OSError, capacity.docker_lab_names)


class TestDeployDecision(Case):
    def test_allowed_and_usage(self):
        self.names = {"net002-b"}
        decision = self.cap().check_deploy("a", self.inst("net-003", "a"))
        self.assertTrue(decision)
        self.assertEqual((decision.need_mb, decision.used_mb, decision.destroy), (1300, 900, []))

    def test_memory_full(self):
        self.names = {"net003-b", "net003-c"}               # 2600 MB
        decision = self.cap(mem_mb=3000).check_deploy("a", self.inst("net-002", "a"))
        self.assertFalse(decision)
        self.assertEqual(decision.code, "memory")
        self.assertIn("2600 MB dari 3000 MB", decision.reason)
        self.assertIn("900 MB", decision.reason)
        # Lab kecil masih muat.
        self.assertTrue(self.cap(mem_mb=3000).check_deploy("a", self.inst("net-001", "a")))

    def test_too_big(self):
        decision = self.cap(mem_mb=1000).check_deploy("a", self.inst("net-003", "a"))
        self.assertEqual(decision.code, "too_big")
        self.assertIn("capacity.mem_mb", decision.reason)

    def test_redeploy_does_not_count_itself(self):
        self.names = {"net003-a"}
        self.assertTrue(self.cap(mem_mb=1300).check_deploy("a", self.inst("net-003", "a")))

    def test_one_lab_per_user(self):
        self.names = {"net001-a", "net002-a", "net003-a", "net002-b"}
        decision = self.cap(mem_mb=2500).check_deploy("a", self.inst("net-003", "a"))
        self.assertEqual(decision.destroy, [self.inst("net-001", "a"), self.inst("net-002", "a")])
        # RAM lab yang akan dimatikan tidak dihitung: yang tersisa hanya net002-b (900).
        self.assertTrue(decision)
        self.assertEqual(decision.used_mb, 900)
        free = capacity.Capacity(CapConfig(), list_running=lambda: set(self.names), one_per_user=False)
        self.assertEqual(free.check_deploy("a", self.inst("net-003", "a")).destroy, [])

    def test_owner_must_match(self):
        with self.assertRaises(ValueError):
            self.cap().check_deploy("b", self.inst("net-001", "a"))

    def test_docker_unreachable(self):
        def broken():
            raise OSError("docker mati")
        cap = capacity.Capacity(CapConfig(), list_running=broken)
        decision = cap.check_deploy("a", self.inst("net-001", "a"))
        self.assertEqual(decision.code, "docker")


class TestDeploySlots(Case):
    def test_slots_and_reservation(self):
        cap = self.cap(mem_mb=3000, max_deploys=2)
        a, b, c = self.inst("net-003", "a"), self.inst("net-002", "b"), self.inst("net-001", "c")
        self.assertTrue(cap.try_acquire("a", a))
        # Reservasi a (1300) ikut dihitung walau belum terlihat di docker.
        self.assertEqual(cap.check_deploy("b", b).used_mb, 1300)
        self.assertTrue(cap.try_acquire("b", b))
        busy = cap.try_acquire("c", c)
        self.assertEqual(busy.code, "busy")
        self.assertIn("maks. 2", busy.reason)
        cap.release_deploy(a)
        self.assertTrue(cap.try_acquire("c", c))
        self.assertEqual(cap.usage()["deploying"], 2)

    def test_concurrent_threads(self):
        cap = self.cap(max_deploys=2)
        active, peak, lock = [0], [0], threading.Lock()
        # Pemegang slot menunggu pasangannya sebelum melepas: dua deploy bersamaan pasti
        # terjadi walau mesin lambat (sleep tetap bisa membuat giliran tidak tumpang tindih).
        pair = threading.Barrier(2)
        results = []

        def worker(i):
            inst = self.inst("net-001", f"u{i}")
            decision = cap.try_acquire(inst.user, inst, wait=10)
            results.append(decision.code)
            if not decision:
                return
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            pair.wait(timeout=5)
            with lock:
                active[0] -= 1
            cap.release_deploy(inst)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(15)
        self.assertEqual(results.count("ok"), 8)    # semua antre lalu dapat giliran
        self.assertEqual(peak[0], 2)
        self.assertEqual(cap.deploying, {})

    def test_wait_gives_up(self):
        cap = self.cap(max_deploys=1)
        cap.try_acquire("a", self.inst("net-001", "a"))
        start = time.monotonic()
        self.assertEqual(cap.try_acquire("b", self.inst("net-001", "b"), wait=0.2).code, "busy")
        self.assertLess(time.monotonic() - start, 3)

    def test_context_manager(self):
        cap = self.cap(max_deploys=1)
        a, b = self.inst("net-001", "a"), self.inst("net-001", "b")
        with cap.deploy_slot("a", a) as decision:
            self.assertTrue(decision)
            with self.assertRaises(capacity.CapacityError):
                with cap.deploy_slot("b", b):
                    pass
        self.assertEqual(cap.deploying, {})
        with cap.deploy_slot("b", b):
            pass


class TestCleanup(Case):
    def touch_state(self, inst, age, name="events/sw1.jsonl"):
        path = inst.state_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n")
        when = time.time() - age
        for p in (path, path.parent, inst.state_dir):
            os.utime(p, (when, when))

    def test_idle(self):
        cap = self.cap(idle_minutes=30)
        fresh, old, evaluating, nostate = (self.inst("net-001", "a"), self.inst("net-002", "b"),
                                           self.inst("net-003", "c"), self.inst("net-001", "d"))
        self.touch_state(fresh, 60)
        self.touch_state(old, 3600)
        self.touch_state(evaluating, 3600)
        self.names = {"net001-a", "net002-b", "net003-c", "net001-d", "net001"}
        idle = cap.idle_candidates(busy=lambda i: i == evaluating)
        # local dilewati, lab tanpa .state dianggap idle.
        self.assertEqual(idle, [old, nostate])

    def test_idle_ignores_logs_and_uses_last_seen(self):
        cap = self.cap(idle_minutes=30)
        inst = self.inst("net-002", "b")
        self.touch_state(inst, 3600)
        (inst.state_dir / "watch.log").write_text("baru\n")     # log watcher tidak dihitung
        os.utime(inst.state_dir, (time.time() - 3600,) * 2)
        self.names = {"net002-b"}
        self.assertEqual(cap.idle_candidates(), [inst])
        self.assertEqual(cap.idle_candidates(last_seen=lambda i: time.time() - 10), [])
        # Aktivitas baru di tty/ (rekaman terminal) juga dihitung.
        self.touch_state(inst, 5, "tty/sw1")
        self.assertEqual(cap.idle_candidates(), [])

    def test_idle_skips_deploying(self):
        cap = self.cap()
        inst = self.inst("net-001", "a")
        self.names = {"net001-a"}
        cap.try_acquire("a", inst)
        self.assertEqual(cap.idle_candidates(), [])

    def test_orphans(self):
        self.names = {"net001-a", "net002-gone", "net003", "net001-off"}
        self.assertEqual(self.cap().orphan_candidates({"a", "b"}),
                         [self.inst("net-002", "gone"), self.inst("net-001", "off")])


class TestDestroy(Case):
    def ok(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="==> destroy\n", stderr="")

    def setUp(self):
        super().setUp()
        self.calls = []

    def test_calls_reset_lab_destroy_only(self):
        inst = self.inst("net-002", "a")
        self.assertIsNone(capacity.destroy(inst, runner=self.ok))
        (cmd,), kwargs = self.calls[0]
        self.assertEqual(cmd, [str(PLATFORM / "reset-lab"), "--destroy-only", str(LABS / "net-002")])
        self.assertEqual(kwargs["env"]["LAB_INSTANCE"], "a")
        self.assertEqual(kwargs["env"]["LAB_CLAB_NAME"], "net002-a")

    def test_archives_unevaluated_session(self):
        inst = self.inst("net-001", "a")
        inst.state_dir.mkdir(parents=True)
        (inst.state_dir / "session_id").write_text("20260101-000000\n")
        dest = capacity.destroy(inst, reason="idle", runner=self.ok)
        self.assertEqual(dest, inst.sessions_dir / "20260101-000000")
        self.assertEqual(json.loads((dest / "abandoned.json").read_text())["reason"], "idle")
        # Sesi yang sudah dinilai tidak diarsip ulang.
        (inst.state_dir / "evaluation.json").write_text("{}")
        self.assertIsNone(capacity.destroy(inst, runner=self.ok))

    def test_failure_raises(self):
        def fail(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="sudo: a password is required")
        with self.assertRaisesRegex(capacity.CapacityError, "password"):
            capacity.destroy(self.inst("net-001", "a"), archive=False, runner=fail)

    def test_reset_lab_syntax(self):
        subprocess.run(["bash", "-n", str(PLATFORM / "reset-lab")], check=True)
        self.assertIn("--destroy-only", (PLATFORM / "reset-lab").read_text())


if __name__ == "__main__":
    unittest.main()
