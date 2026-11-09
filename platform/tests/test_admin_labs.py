"""Test API admin lab berjalan (admin_labs.py), tanpa docker sungguhan."""

import time
import unittest
from unittest import mock

from test_auth import ServerCase  # noqa: F401  (juga mengatur sys.path)

import capacity  # noqa: E402
import dashboard  # noqa: E402


class AdminLabsCase(ServerCase):
    def setUp(self):
        super().setUp()
        self.stopped = []
        self.jobs = {}
        self.busy = {}
        self.seen = {}
        self.stop_error = None
        old = {k: getattr(dashboard.H, k) for k in ("stop_lab", "deploy_job", "lab_busy", "last_seen")}
        self.addCleanup(dashboard.bind, **old)

        def stop(inst, reason):
            if self.stop_error:
                raise self.stop_error
            self.stopped.append((inst, reason))
            return "20260101-000000"

        dashboard.bind(stop_lab=stop, deploy_job=self.jobs.get, lab_busy=lambda i: self.busy.get(i),
                       last_seen=self.seen.get)
        self.admin = self.logged_in("admin1")

    def by_user(self, body):
        return {lab["username"]: lab for lab in body["labs"]}


class TestAccess(AdminLabsCase):
    def test_unauthenticated(self):
        from test_auth import Client
        self.assertEqual(Client().get("/api/admin/labs").status, 401)

    def test_roles(self):
        for name in ("alice", "guru1"):
            client = self.logged_in(name)
            self.assertEqual(client.get("/api/admin/labs").status, 403)
            self.assertEqual(client.post("/api/admin/labs/bob/net-001/stop").status, 403)

    def test_personal_mode_404(self):
        from test_auth import Client, server, config
        client = Client(host="localhost:8000")
        server.configure(config.Config())
        try:
            self.assertEqual(client.get("/api/admin/labs").status, 404)
        finally:
            server.configure(config.load(), self.store)


class TestList(AdminLabsCase):
    def test_states_and_fields(self):
        self.no_docker(running=["net001-alice", "net001-bob", "net001-ghost"])
        cap = dashboard.H.capacity()
        # carol: reservasi deploy; bob: dihentikan (hanya ada di daftar -a)
        carol = capacity.Instance(self.alice.problem_dir, "carol")
        cap.list_all = lambda: ["net001-alice", "net001-bob", "net001-ghost"]
        cap.list_running = lambda: ["net001-alice", "net001-ghost"]
        with cap.cond:
            cap.deploying[carol] = 700
        self.addCleanup(cap.deploying.clear)
        self.jobs[carol] = {"status": "running", "step": "deploy"}
        self.busy[self.alice] = "evaluate"
        self.seen[self.alice] = time.time() - 10
        body = self.admin.get("/api/admin/labs").json()
        labs = self.by_user(body)
        self.assertEqual([l["username"] for l in body["labs"]], ["alice", "bob", "carol", "ghost"])
        self.assertEqual(labs["alice"]["state"], "running")
        self.assertEqual(labs["alice"]["display_name"], "Alice A")
        self.assertEqual(labs["alice"]["busy"], "evaluate")
        self.assertEqual(labs["alice"]["lab_id"], "net-001")
        self.assertEqual(labs["alice"]["clab_name"], "net001-alice")
        self.assertLess(labs["alice"]["idle_s"], 60)
        self.assertEqual(labs["bob"]["state"], "stopped")
        self.assertEqual(labs["bob"]["session"], (self.bob.state_dir / "session_id").read_text().strip())
        self.assertIsNotNone(labs["bob"]["last_activity"])
        self.assertEqual(labs["carol"]["state"], "deploying")
        self.assertEqual(labs["carol"]["deploy_step"], "deploy")
        self.assertEqual(labs["carol"]["display_name"], "carol")      # akun tidak ada
        self.assertEqual(labs["ghost"]["display_name"], "ghost")
        self.assertIsNone(labs["bob"]["deploy_step"])
        cap_info = body["capacity"]
        self.assertEqual(cap_info["deploying"], 1)
        self.assertEqual(set(cap_info), {"used_mb", "limit_mb", "deploying", "max_deploys", "idle_minutes"})
        self.assertGreater(cap_info["used_mb"], 0)

    def test_local_and_no_activity(self):
        self.no_docker(running=["net001"])
        labs = self.admin.get("/api/admin/labs").json()["labs"]
        self.assertEqual(len(labs), 1)
        self.assertEqual(labs[0]["username"], "local")
        self.assertEqual(labs[0]["display_name"], "local (terminal server)")

    def test_no_activity_gives_nulls(self):
        self.no_docker(running=["net001-alice"])
        with mock.patch.object(capacity, "last_activity", return_value=None):
            lab = self.admin.get("/api/admin/labs").json()["labs"][0]
        self.assertIsNone(lab["last_activity"])
        self.assertIsNone(lab["idle_s"])

    def test_empty(self):
        self.no_docker()
        self.assertEqual(self.admin.get("/api/admin/labs").json()["labs"], [])

    def test_docker_error_503(self):
        def boom():
            raise OSError("docker mati")
        cap = dashboard.H.capacity()
        cap.list_running = cap.list_all = boom
        response = self.admin.get("/api/admin/labs")
        self.assertEqual(response.status, 503)
        self.assertIn("docker mati", response.json()["detail"])


class TestStop(AdminLabsCase):
    def test_stop_calls_hook(self):
        self.no_docker(running=["net001-alice"])
        response = self.admin.post("/api/admin/labs/alice/net-001/stop")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json(), {"ok": True, "archived": "20260101-000000"})
        self.assertEqual(self.stopped, [(self.alice, "manual")])

    def test_stop_stopped_container_allowed(self):
        cap = dashboard.H.capacity()
        cap.list_running = lambda: []
        cap.list_all = lambda: ["net001-alice"]
        self.assertEqual(self.admin.post("/api/admin/labs/alice/net-001/stop").status, 200)

    def test_not_running_404(self):
        self.no_docker(running=["net001-bob"])
        response = self.admin.post("/api/admin/labs/alice/net-001/stop")
        self.assertEqual(response.status, 404)
        self.assertEqual(response.json()["detail"], "Lab tidak berjalan.")
        self.assertEqual(self.stopped, [])

    def test_bad_username_or_lab_404(self):
        self.no_docker(running=["net001-alice"])
        self.assertEqual(self.admin.post("/api/admin/labs/Bad_Name/net-001/stop").status, 404)
        self.assertEqual(self.admin.post("/api/admin/labs/alice/net-999/stop").status, 404)
        self.assertEqual(self.stopped, [])

    def test_local_stop(self):
        self.no_docker(running=["net001"])
        self.assertEqual(self.admin.post("/api/admin/labs/local/net-001/stop").status, 200)
        self.assertEqual(self.stopped[0][0].user, "local")

    def test_busy_passthrough(self):
        from fastapi import HTTPException
        self.no_docker(running=["net001-alice"])
        self.stop_error = HTTPException(409, "Lab sedang di-deploy.")
        response = self.admin.post("/api/admin/labs/alice/net-001/stop")
        self.assertEqual(response.status, 409)
        self.assertEqual(response.json()["detail"], "Lab sedang di-deploy.")

    def test_docker_error_503(self):
        def boom():
            raise OSError("docker mati")
        cap = dashboard.H.capacity()
        cap.list_running = cap.list_all = boom
        self.assertEqual(self.admin.post("/api/admin/labs/alice/net-001/stop").status, 503)

    def test_real_wiring_destroys_with_manual_reason(self):
        from test_auth import server
        self.no_docker(running=["net001-alice"])
        dashboard.bind(stop_lab=server.stop_lab, lab_busy=server.lab_busy)
        with mock.patch.object(server.capacity, "destroy", return_value=None) as destroy:
            response = self.admin.post("/api/admin/labs/alice/net-001/stop")
        self.assertEqual(response.status, 200)
        self.assertIsNone(response.json()["archived"])
        destroy.assert_called_once_with(self.alice, reason="manual")


class TestRealHooks(ServerCase):
    """Hook asli dari server.py (bind di server.py), tanpa palsu: wiring dan tanda STOPPING."""

    def setUp(self):
        super().setUp()
        from test_auth import server
        self.server = server
        self.admin = self.logged_in("admin1")
        self.no_docker(running=["net001-alice"])
        self.addCleanup(server.DEPLOYS.jobs.pop, self.alice, None)
        self.addCleanup(server.STOPPING.clear)

    def test_running_deploy_shows_and_blocks_stop(self):
        self.server.DEPLOYS.jobs[self.alice] = {"status": "running", "step": "verify", "started": time.time(),
                                                "error": None, "log": []}
        lab = self.admin.get("/api/admin/labs").json()["labs"][0]
        self.assertEqual((lab["state"], lab["deploy_step"], lab["busy"]), ("deploying", "verify", "deploy"))
        with mock.patch.object(capacity, "destroy") as destroy:
            r = self.admin.post("/api/admin/labs/alice/net-001/stop")
        self.assertEqual(r.status, 409)
        destroy.assert_not_called()

    def test_stopping_blocks_second_stop_and_owner_actions(self):
        server = self.server
        inside = {}

        def slow_destroy(inst, reason):
            # Selama destroy: stop kedua, deploy, dan mulai sesi pemilik ditolak.
            inside["stop"] = self.admin.post("/api/admin/labs/alice/net-001/stop").status
            alice = self.logged_in("alice")
            for action in ("deploy", "start"):
                response = alice.post(f"/api/labs/net-001/{action}")
                inside[action] = (response.status, response.json()["detail"])
            inside["busy"] = server.lab_busy(inst)
            return None

        with mock.patch.object(capacity, "destroy", side_effect=slow_destroy), \
                mock.patch.object(server, "deploy_support", return_value={"available": True, "reason": None}):
            r = self.admin.post("/api/admin/labs/alice/net-001/stop")
        self.assertEqual(r.status, 200)
        self.assertEqual(inside, {"stop": 409, "deploy": (409, "Lab sedang dimatikan."),
                                  "start": (409, "Lab sedang dimatikan."), "busy": "stop"})
        self.assertNotIn(self.alice, server.STOPPING)   # tanda dilepas setelah selesai

    def test_reaper_skips_lab_being_stopped(self):
        server = self.server
        server.STOPPING.add(self.alice)
        self.store.set_active("alice", False)
        self.addCleanup(self.store.set_active, "alice", True)
        with mock.patch.object(capacity, "destroy") as destroy:
            server.reap_labs_once()
        destroy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
