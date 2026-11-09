"""Antrian deploy mode Server (server.process_queue, DELETE /api/labs/{id}/deploy), tanpa docker.

reset.sh tidak dijalankan: DeployJobs._deploy diganti fungsi yang menunggu Event per user,
jadi deploy "berjalan" selama test menahannya.
"""

import shutil
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from test_auth import ServerCase, Client, server, config, capacity  # noqa: F401  (juga mengatur sys.path)

from instance import Instance  # noqa: E402


def cfg(mem_mb=24000, max_deploys=1):
    return config.Capacity(mem_mb=mem_mb, max_deploys=max_deploys, idle_minutes=30)


class QueueCase(ServerCase):
    support = {"available": True, "mode": "setuid", "reason": None}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        lab2 = cls.labs / "net-002"
        shutil.copytree(cls.labs / "net-001", lab2, ignore=shutil.ignore_patterns(".state", "sessions", "clab-*"))
        problem = lab2 / "problem.yaml"
        problem.write_text(problem.read_text().replace("id: net-001", "id: net-002", 1))
        topo = lab2 / "topo-3switch-2host.clab.yaml"
        topo.write_text(topo.read_text().replace("name: net001", "name: net002", 1))
        cls.alice2 = Instance(lab2, "alice")
        cls.guru = Instance(cls.labs / "net-001", "guru1")

    def setUp(self):
        super().setUp()
        self.reset_state()
        self.gates = {}
        self.deploy_seen = None
        self.clients = {}
        self.cap = server.AUTH.capacity
        self.use(capacity=cfg())
        self.cap = server.AUTH.capacity
        for patcher in (mock.patch.object(server, "deploy_support", return_value=self.support),
                        mock.patch.object(server, "missing_images", return_value=[]),
                        mock.patch.object(server.DEPLOYS, "_deploy", side_effect=self.fake_deploy)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.finish_all)

    # --- deploy palsu yang bisa ditahan
    def gate(self, user):
        return self.gates.setdefault(user, threading.Event())

    def fake_deploy(self, job, directory, env, inst, destroy_first):
        self.deploy_seen = (set(destroy_first), set(server.STOPPING))
        self.gate(inst.user).wait(15)
        job.update(status="done", step="done", finished=time.time())

    def release(self, user):
        self.gate(user).set()

    def finish_all(self):
        for event in self.gates.values():
            event.set()
        for user in ("alice", "bob", "guru1", "admin1"):
            self.gate(user).set()
        for _ in range(200):
            if not self.cap.deploying and not any(j["status"] == "running" for j in server.DEPLOYS.jobs.values()):
                break
            time.sleep(0.05)
        self.reset_state()

    @staticmethod
    def reset_state():
        with server.DEPLOY_GATE:   # thread sisa test sebelumnya bisa masih memproses antrian
            server.DEPLOYS.queue.clear()
            server.DEPLOYS.jobs.clear()
            server.STOPPING.clear()

    def wait_for(self, predicate, what="kondisi"):
        for _ in range(200):
            if predicate():
                return
            time.sleep(0.05)
        self.fail(f"tidak tercapai: {what}")

    # --- HTTP
    def client(self, user):
        if user not in self.clients:
            self.clients[user] = self.logged_in(user)
        return self.clients[user]

    def deploy(self, user, lab="net-001"):
        return self.client(user).post(f"/api/labs/{lab}/deploy")

    def cancel(self, user, lab="net-001"):
        return self.client(user).request("DELETE", f"/api/labs/{lab}/deploy")

    def inst(self, user):
        return Instance(self.labs / "net-001", user)

    def job(self, user):
        return server.DEPLOYS.get(self.inst(user))

    def fill_slot(self):
        """alice men-deploy dan ditahan: slot max_deploys=1 penuh."""
        response = self.deploy("alice")
        self.assertEqual(response.json()["status"], "running", response.body)

    def queue_users(self):
        return [i.user for i in server.DEPLOYS.queue]


class TestEnqueue(QueueCase):
    def test_busy_goes_to_queue_with_position(self):
        self.fill_slot()
        response = self.deploy("bob")
        self.assertEqual(response.status, 200, response.body)
        body = response.json()
        self.assertEqual((body["status"], body["position"], body["queue_reason"]), ("queued", 1, "busy"))
        self.assertIsNone(body["step"])
        self.assertIsNone(body["started"])
        self.assertIsNone(body["error"])
        self.assertAlmostEqual(body["queued_at"], time.time(), delta=30)
        self.assertEqual(self.deploy("guru1").json()["position"], 2)
        self.assertEqual(self.job("bob")["position"], 1)
        self.assertEqual(self.queue_users(), ["bob", "guru1"])
        self.assertNotIn(self.inst("bob"), self.cap.deploying)   # antrian tidak memegang reservasi

    def test_memory_goes_to_queue(self):
        need = self.cap.estimate(self.alice)
        self.use(capacity=cfg(mem_mb=need + 10, max_deploys=5))
        self.cap = server.AUTH.capacity
        self.fill_slot()
        body = self.deploy("bob").json()
        self.assertEqual((body["status"], body["queue_reason"], body["position"]), ("queued", "memory", 1))

    def test_too_big_still_rejected(self):
        self.use(capacity=cfg(mem_mb=100, max_deploys=5))
        response = self.deploy("alice")
        self.assertEqual(response.status, 503, response.body)
        self.assertIn("RAM", response.json()["detail"])
        self.assertEqual(server.DEPLOYS.queue, [])
        self.assertIsNone(self.job("alice"))

    def test_docker_error_still_rejected(self):
        def boom():
            raise OSError("socket")
        self.cap.list_running = self.cap.list_all = boom
        response = self.deploy("alice")
        self.assertEqual(response.status, 503, response.body)
        self.assertEqual(server.DEPLOYS.queue, [])

    def test_idempotent(self):
        self.fill_slot()
        first = self.deploy("bob").json()
        second = self.deploy("bob").json()
        self.assertEqual(second["queued_at"], first["queued_at"])
        self.assertEqual(self.queue_users(), ["bob"])

    def test_one_deploy_per_user(self):
        self.fill_slot()
        self.deploy("bob")
        response = self.deploy("bob", "net-002")
        self.assertEqual(response.status, 409, response.body)
        self.assertIn("mengantre", response.json()["detail"])
        # juga untuk user yang deploy-nya sedang berjalan
        other = self.deploy("alice", "net-002")
        self.assertEqual(other.status, 409, other.body)
        self.assertEqual(self.queue_users(), ["bob"])

    def test_one_per_user_check_applies_when_queue_nonempty(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        self.assertEqual(self.deploy("bob", "net-002").status, 409)

    def test_new_deploy_does_not_overtake_queue(self):
        """Slot kosong tapi ada antrian: deploy baru ikut di ekor, kepala (bob) jalan lebih dulu."""
        self.fill_slot()
        self.deploy("bob")
        self.cap.release_deploy(self.alice)   # slot kosong, tapi belum ada yang mempromosikan
        body = self.deploy("guru1").json()
        self.assertEqual(self.job("bob")["status"], "running")
        self.assertEqual((body["status"], body["position"]), ("queued", 1))   # bob sudah jalan; guru1 menunggu


class TestCancel(QueueCase):
    def test_cancel_queued(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        response = self.cancel("bob")
        self.assertEqual((response.status, response.json()), (200, {"ok": True}))
        self.assertIsNone(self.job("bob"))
        self.assertEqual(self.queue_users(), ["guru1"])
        self.assertEqual(self.job("guru1")["position"], 1)
        self.assertEqual(self.cancel("bob").status, 409)

    def test_cancel_without_queue_409(self):
        response = self.cancel("bob")
        self.assertEqual(response.status, 409, response.body)
        self.assertEqual(response.json()["detail"], "Tidak ada antrian deploy untuk lab ini.")

    def test_cancel_running_409_and_keeps_job(self):
        self.fill_slot()
        self.assertEqual(self.cancel("alice").status, 409)
        self.assertEqual(self.job("alice")["status"], "running")

    def test_cancel_head_lets_next_in(self):
        """Kepala yang dibatalkan tidak boleh menahan entri di belakangnya."""
        need = self.cap.estimate(self.alice)
        self.use(capacity=cfg(mem_mb=need * 2, max_deploys=5))
        self.cap = server.AUTH.capacity
        self.fill_slot()
        self.deploy("bob")      # muat (2 x need)
        self.assertEqual(self.job("bob")["status"], "running")
        self.deploy("guru1")    # penuh -> antri
        self.assertEqual(self.job("guru1")["status"], "queued")
        self.release("alice")
        self.wait_for(lambda: self.job("guru1")["status"] != "queued", "guru1 dipromosikan")


class TestPromotion(QueueCase):
    def test_process_queue_promotes_when_slot_frees(self):
        self.fill_slot()
        self.deploy("bob")
        queued = server.DEPLOYS.jobs[self.inst("bob")]
        server.process_queue()
        self.assertEqual(self.job("bob")["status"], "queued")   # masih penuh
        self.cap.release_deploy(self.alice)
        server.process_queue()
        self.assertIs(server.DEPLOYS.jobs[self.inst("bob")], queued)   # dict yang sama
        self.assertEqual(queued["status"], "running")
        self.assertIsNotNone(queued["started"])
        self.assertNotIn("position", self.job("bob"))
        self.assertNotIn("queue_reason", queued)
        self.assertEqual(server.DEPLOYS.queue, [])
        self.assertIn(self.inst("bob"), self.cap.deploying)

    def test_on_finish_triggers_promotion(self):
        self.fill_slot()
        self.deploy("bob")
        self.release("alice")     # alice selesai -> on_finish -> process_queue (tanpa panggilan manual)
        self.release("bob")
        self.wait_for(lambda: (self.job("bob") or {}).get("status") == "done", "bob selesai")
        self.wait_for(lambda: not self.cap.deploying, "reservasi lepas")
        self.assertEqual(server.DEPLOYS.queue, [])

    def test_chain_of_three(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        for user in ("alice", "bob", "guru1"):
            self.release(user)
        self.wait_for(lambda: all((self.job(u) or {}).get("status") == "done" for u in ("alice", "bob", "guru1")),
                      "ketiganya selesai")
        self.wait_for(lambda: not self.cap.deploying and not server.DEPLOYS.queue, "bersih")

    def test_fifo_is_strict(self):
        """Kepala menunggu RAM: entri di belakang yang muat tidak boleh menyalip."""
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        calls = []

        def acquire(user, inst, wait=0):
            calls.append(user)
            if user == "bob":
                return capacity.Decision(False, "penuh", "memory", [], 100, 0, 200)
            self.cap.deploying[inst] = 1
            return capacity.Decision(True, None, "ok", [], 100, 0, 200)

        with mock.patch.object(self.cap, "try_acquire", side_effect=acquire):
            server.process_queue()
        self.assertEqual(calls, ["bob"])
        self.assertEqual(self.queue_users(), ["bob", "guru1"])
        self.assertEqual(self.job("bob")["queue_reason"], "memory")   # alasan kepala diperbarui

    def test_head_error_is_released_and_next_continues(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        self.cap.release_deploy(self.alice)
        self.cap.cap = cfg(mem_mb=100, max_deploys=5)    # bob (kepala): kini too_big
        calls = []
        real = self.cap.try_acquire

        def acquire(user, inst, wait=0):
            calls.append(user)
            if user == "guru1":
                self.cap.cap = cfg()
            return real(user, inst, wait)

        with mock.patch.object(self.cap, "try_acquire", side_effect=acquire):
            server.process_queue()
        bob = self.job("bob")
        self.assertEqual(bob["status"], "error")
        self.assertIn("RAM", bob["error"])
        self.assertNotIn("position", bob)
        self.assertEqual(calls, ["bob", "guru1"])
        self.assertEqual(self.job("guru1")["status"], "running")
        self.assertEqual(server.DEPLOYS.queue, [])
        self.assertNotIn(self.inst("bob"), self.cap.deploying)

    def test_other_lab_being_graded_waits_and_releases_reservation(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        self.cap.release_deploy(self.alice)
        other = mock.Mock(problem_dir=Path("/x/net-009"), user="bob")
        decision = capacity.Decision(True, None, "ok", [other], 150, 0, 24000)
        real = self.cap.try_acquire

        def acquire(user, inst, wait=0):
            if user == "bob":
                self.cap.deploying[inst] = 150   # seperti try_acquire asli: reservasi diambil
                return decision
            return real(user, inst, wait)

        with mock.patch.object(self.cap, "try_acquire", side_effect=acquire), \
                mock.patch.object(server, "evaluating", side_effect=lambda i: i is other), \
                mock.patch.object(server.capacity, "destroy") as destroy:
            server.process_queue()
        # Kondisi sementara: bob tetap kepala antrian (tidak dibuang), guru1 tidak menyalip.
        self.assertEqual(self.job("bob")["status"], "queued")
        self.assertEqual(self.queue_users(), ["bob", "guru1"])
        destroy.assert_not_called()
        self.assertNotIn(self.inst("bob"), self.cap.deploying)    # reservasi bob dilepas
        self.assertEqual(server.STOPPING, set())
        self.assertEqual(self.job("guru1")["status"], "queued")

    def test_destroy_marks_stopping_and_releases_it(self):
        self.fill_slot()
        self.deploy("bob")
        self.cap.release_deploy(self.alice)
        other = mock.Mock(problem_dir=Path("/x/net-009"), user="bob")
        decision = capacity.Decision(True, None, "ok", [other], 150, 0, 24000)

        def acquire(user, inst, wait=0):
            self.cap.deploying[inst] = 150
            return decision

        with mock.patch.object(self.cap, "try_acquire", side_effect=acquire), \
                mock.patch.object(server, "evaluating", return_value=False):
            server.process_queue()
            self.wait_for(lambda: getattr(self, "deploy_seen", None), "deploy bob mulai")
            destroyed, stopping = self.deploy_seen
            self.assertEqual(destroyed, {other})
            self.assertIn(other, stopping)       # ditandai sebelum job jalan
            self.release("bob")
            self.wait_for(lambda: (self.job("bob") or {}).get("status") == "done", "bob selesai")
        self.wait_for(lambda: other not in server.STOPPING, "STOPPING dilepas")

    def test_stopping_target_makes_head_wait(self):
        self.fill_slot()
        self.deploy("bob")
        self.cap.release_deploy(self.alice)
        server.STOPPING.add(self.inst("bob"))
        self.addCleanup(server.STOPPING.discard, self.inst("bob"))
        server.process_queue()
        self.assertEqual(self.job("bob")["status"], "queued")     # menunggu, tidak dibuang
        self.assertNotIn(self.inst("bob"), self.cap.deploying)
        server.STOPPING.discard(self.inst("bob"))
        server.process_queue()
        self.assertEqual(self.job("bob")["status"], "running")    # lanjut setelah selesai dimatikan

    def test_timeout(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        server.DEPLOYS.jobs[self.inst("guru1")]["queued_at"] -= server.QUEUE_TIMEOUT + 1
        server.process_queue()    # guru1 (bukan kepala) pun dibuang
        guru = self.job("guru1")
        self.assertEqual(guru["status"], "error")
        self.assertEqual(guru["error"], "Antrian deploy dibatalkan: menunggu lebih dari 30 menit.")
        self.assertEqual(self.queue_users(), ["bob"])
        server.DEPLOYS.jobs[self.inst("bob")]["queued_at"] -= server.QUEUE_TIMEOUT + 1
        server.process_queue()
        self.assertEqual(self.job("bob")["status"], "error")
        self.assertEqual(server.DEPLOYS.queue, [])

    def test_timeout_value(self):
        self.assertEqual(server.QUEUE_TIMEOUT, 1800)
        self.assertEqual(server.QUEUE_POLL, 10)

    def test_docker_hiccup_keeps_whole_queue(self):
        self.fill_slot()
        for user in ("bob", "guru1", "admin1"):
            self.deploy(user)
        self.cap.release_deploy(self.alice)
        failing = capacity.Decision(False, "Docker tidak bisa diakses", "docker", [], 150, 0, 24000)
        with mock.patch.object(self.cap, "try_acquire", return_value=failing):
            server.process_queue()
        self.assertEqual(self.queue_users(), ["bob", "guru1", "admin1"])
        self.assertTrue(all(self.job(u)["status"] == "queued" for u in ("bob", "guru1", "admin1")))

    def test_too_big_rejected_before_joining_queue(self):
        self.fill_slot()
        self.deploy("bob")
        with mock.patch.object(self.cap, "estimate", return_value=10 ** 7):
            response = self.logged_in("guru1").post("/api/labs/net-001/deploy")
        self.assertEqual(response.status, 503)
        self.assertEqual(self.queue_users(), ["bob"])

    def test_inactive_account_removed(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        self.store.set_active("bob", False)
        self.addCleanup(self.store.set_active, "bob", True)
        server.process_queue()
        bob = self.job("bob")
        self.assertEqual((bob["status"], bob["error"]), ("error", "Akun dinonaktifkan."))
        self.assertEqual(self.queue_users(), ["guru1"])
        self.assertEqual(self.job("guru1")["position"], 1)

    def test_unexpected_error_in_admit_drops_entry(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        self.cap.release_deploy(self.alice)
        real = self.cap.try_acquire

        def acquire(user, inst, wait=0):
            if user == "bob":
                raise RuntimeError("kaboom")
            return real(user, inst, wait)

        with mock.patch.object(self.cap, "try_acquire", side_effect=acquire):
            server.process_queue()
        self.assertIn("kaboom", self.job("bob")["error"])
        self.assertEqual(self.job("guru1")["status"], "running")

    def test_start_failure_releases_reservation(self):
        self.fill_slot()
        self.deploy("bob")
        self.cap.release_deploy(self.alice)
        with mock.patch.object(server.DEPLOYS, "start", side_effect=RuntimeError("thread")):
            server.process_queue()
        self.assertEqual(self.job("bob")["status"], "error")
        self.assertNotIn(self.inst("bob"), self.cap.deploying)
        self.assertEqual(server.STOPPING, set())

    def test_no_reservation_leak(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        self.cancel("guru1")
        self.release("alice")
        self.release("bob")
        self.wait_for(lambda: (self.job("bob") or {}).get("status") == "done", "bob selesai")
        self.wait_for(lambda: self.cap.deploying == {}, "reservasi lepas")
        self.assertEqual(server.STOPPING, set())
        self.assertEqual(server.DEPLOYS.queue, [])


class TestTriggers(QueueCase):
    def test_stop_lab_kicks_queue(self):
        with mock.patch.object(server, "process_queue") as process, \
                mock.patch.object(server.capacity, "destroy", return_value=None):
            server.stop_lab(self.bob)
        process.assert_called_once()
        self.assertFalse(server.DEPLOY_GATE.locked())

    def test_stop_lab_kicks_even_when_destroy_fails(self):
        with mock.patch.object(server, "process_queue") as process, \
                mock.patch.object(server.capacity, "destroy", side_effect=capacity.CapacityError("x")):
            with self.assertRaises(server.HTTPException):
                server.stop_lab(self.bob)
        process.assert_called_once()

    def test_reaper_kicks_queue(self):
        self.store.set_active("bob", False)
        self.addCleanup(self.store.set_active, "bob", True)
        self.no_docker(running=["net001-bob"])
        with mock.patch.object(server, "process_queue") as process, \
                mock.patch.object(server.capacity, "destroy"), \
                mock.patch.object(self.cap, "idle_candidates", return_value=[]):
            server.reap_labs_once()
        process.assert_called_once()

    def test_kick_swallows_errors(self):
        with mock.patch.object(server, "process_queue", side_effect=RuntimeError("x")):
            server.kick_queue()    # tidak melempar

    def test_process_queue_not_called_under_gate(self):
        """Pemicu on_finish berjalan setelah gate dilepas (Lock tidak reentrant)."""
        held = []
        with mock.patch.object(server, "process_queue", side_effect=lambda: held.append(server.DEPLOY_GATE.locked())):
            self.deploy("alice")
            self.release("alice")
            self.wait_for(lambda: held, "pemicu on_finish")
        self.assertEqual(held, [False])

    def test_lifespan_polls_queue(self):
        import asyncio
        calls = []

        async def run():
            with mock.patch.object(server, "QUEUE_POLL", 0.01), \
                    mock.patch.object(server, "process_queue", side_effect=lambda: calls.append(1)):
                task = asyncio.create_task(server.promote_queue())
                await asyncio.sleep(0.2)
                task.cancel()

        asyncio.run(run())
        self.assertGreaterEqual(len(calls), 2)


class TestVisibility(QueueCase):
    def test_busy_counts_queued(self):
        self.fill_slot()
        self.deploy("bob")
        self.assertTrue(server.DEPLOYS.busy("bob"))
        self.assertFalse(server.DEPLOYS.busy("bob", exclude=self.inst("bob")))

    def test_live_state_keeps_session_while_queued(self):
        self.fill_slot()
        self.deploy("bob")
        state = self.client("bob").get("/api/labs/net-001/session").json()
        self.assertEqual(state["deploy"]["status"], "queued")
        self.assertEqual(state["deploy"]["position"], 1)
        self.assertIsNotNone(state["session"])    # sesi bob (aktif) tidak disembunyikan

    def test_admin_sees_queue(self):
        self.fill_slot()
        self.deploy("bob")
        self.deploy("guru1")
        body = self.client("admin1").get("/api/admin/labs").json()
        self.assertEqual([(q["username"], q["position"], q["reason"]) for q in body["queue"]],
                         [("bob", 1, "busy"), ("guru1", 2, "busy")])
        first = body["queue"][0]
        self.assertEqual((first["display_name"], first["lab_id"], first["title"]),
                         ("Bob B", "net-001", "VLAN Trunk Misconfiguration"))
        self.assertAlmostEqual(first["queued_at"], time.time(), delta=30)

    def test_admin_queue_empty(self):
        self.assertEqual(self.client("admin1").get("/api/admin/labs").json()["queue"], [])


class TestPersonalMode(unittest.TestCase):
    """Mode Pribadi tidak punya antrian: deploy langsung berjalan, process_queue tidak melakukan apa-apa."""

    def test_no_queue(self):
        from test_auth import ServerCase as Base
        Base.setUpClass.__func__(Base)
        try:
            server.configure(config.Config())
            server.DEPLOYS.jobs.clear()
            server.DEPLOYS.queue.clear()
            self.assertIsNone(server.AUTH.capacity)
            server.process_queue()
            client = Client(host="localhost:8000")
            with mock.patch.object(server, "deploy_support", return_value=QueueCase.support), \
                    mock.patch.object(server, "missing_images", return_value=[]), \
                    mock.patch.object(server.DEPLOYS, "_deploy", side_effect=lambda job, *a: job.update(
                        status="done", step="done", finished=time.time())):
                response = client.post("/api/labs/net-001/deploy")
                self.assertEqual(response.status, 200, response.body)
                self.assertNotIn(response.json()["status"], ("queued",))
            self.assertEqual(server.DEPLOYS.queue, [])
            self.assertEqual(client.request("DELETE", "/api/labs/net-001/deploy").status, 409)
        finally:
            Base.tearDownClass.__func__(Base)


if __name__ == "__main__":
    unittest.main()
