"""Test login, isolasi instance per user, dan leaderboard mode Server (server.py).

Lewat HTTP sungguhan ke aplikasi ASGI (middleware, cookie, Origin ikut teruji),
dengan config server sementara (LAB_CONFIG), DB akun sementara, dan data_dir
sementara. Tidak ada containerlab: reset.sh di salinan soal diganti script palsu
yang hanya mencatat env instance yang diterimanya.

Klien ASGI kecil di bawah menggantikan fastapi.testclient (butuh httpx, yang
tidak ada di requirements): cukup untuk satu request/WebSocket per panggilan.
"""

import asyncio
import dataclasses
import ipaddress
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
GOLDEN = LABS / "net-001" / "golden"
SCORED = "20261019-234339"     # golden yang sudah dinilai (dipakai sebagai arsip sesi user)
ACTIVE = "20261103-023553"     # golden yang dipakai sebagai sesi live (tanpa evaluation.json)
sys.path.insert(0, str(PLATFORM))

import capacity  # noqa: E402
import config  # noqa: E402
import instance  # noqa: E402
import server  # noqa: E402
from accounts import AccountStore  # noqa: E402
from instance import Instance  # noqa: E402

PASSWORD = "rahasia-123"
HOST = "plab.test"


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers          # [(nama, nilai)] huruf kecil
        self.body = body

    def header(self, name):
        return [v for k, v in self.headers if k == name]

    def json(self):
        return json.loads(self.body)


class Client:
    """Klien ASGI minimal dengan cookie jar sederhana (nama -> nilai)."""

    def __init__(self, ip="10.0.0.5", host=HOST):
        self.cookies = {}
        self.ip = ip
        self.host = host

    def _headers(self, extra):
        headers = {"host": self.host}
        if self.cookies:
            headers["cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        headers.update({k.lower(): v for k, v in (extra or {}).items()})
        return [(k.encode(), v.encode()) for k, v in headers.items()]

    def request(self, method, path, body=None, headers=None):
        data = b"" if body is None else json.dumps(body).encode()
        extra = dict(headers or {})
        if body is not None:
            extra.setdefault("content-type", "application/json")
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
                 "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
                 "root_path": "", "headers": self._headers(extra), "client": (self.ip, 50000),
                 "server": (HOST, 80)}
        out = {"status": None, "headers": [], "body": b""}

        async def run():
            sent = False

            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": data, "more_body": False}
                await asyncio.Event().wait()   # klien tidak pernah memutus duluan

            async def send(message):
                if message["type"] == "http.response.start":
                    out["status"] = message["status"]
                    out["headers"] = [(k.decode().lower(), v.decode()) for k, v in message["headers"]]
                elif message["type"] == "http.response.body":
                    out["body"] += message.get("body", b"")

            await server.app(scope, receive, send)

        asyncio.run(run())
        response = Response(out["status"], out["headers"], out["body"])
        for cookie in response.header("set-cookie"):
            name, _, rest = cookie.partition("=")
            value = rest.split(";", 1)[0].strip('"')
            if "max-age=0" in cookie.lower() or not value:
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = value
        return response

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body, **kw)

    def login(self, username, password=PASSWORD):
        return self.post("/api/auth/login", {"username": username, "password": password})

    def websocket(self, path, headers=None):
        """Buka WebSocket; kembalikan ('close', None) kalau ditolak, ('message', json) kalau diterima."""
        scope = {"type": "websocket", "asgi": {"version": "3.0"}, "scheme": "ws", "path": path,
                 "raw_path": path.encode(), "query_string": b"", "root_path": "",
                 "headers": self._headers(headers), "client": (self.ip, 50000), "server": (HOST, 80),
                 "subprotocols": []}

        async def run():
            incoming = asyncio.Queue()
            await incoming.put({"type": "websocket.connect"})
            first = asyncio.get_running_loop().create_future()

            async def send(message):
                if message["type"] == "websocket.close" and not first.done():
                    first.set_result(("close", None))
                elif message["type"] == "websocket.send" and not first.done():
                    first.set_result(("message", json.loads(message["text"])))

            task = asyncio.create_task(server.app(scope, incoming.get, send))
            try:
                return await asyncio.wait_for(first, 10)
            finally:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

        return asyncio.run(run())


class ServerCase(unittest.TestCase):
    """Mode Server dengan soal net-001 (salinan), empat akun, dan data_dir sementara."""

    style = "mandiri"

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="plab-auth-"))
        cls.labs = cls.tmp / "labs"
        lab = cls.labs / "net-001"
        shutil.copytree(LABS / "net-001", lab, ignore=shutil.ignore_patterns(".state", "sessions", "clab-*"))
        # reset.sh palsu: catat instance yang di-deploy, tanpa containerlab.
        (lab / "reset.sh").write_text('#!/usr/bin/env bash\necho "==> deploy"\n'
                                      'echo "$LAB_INSTANCE $LAB_CLAB_NAME" >> "$(dirname "$0")/deployed.log"\n')
        cls.data = cls.tmp / "data"
        cls.config_file = cls.tmp / "server.yaml"
        cls.config_file.write_text(f"mode: server\ndata_dir: {cls.data}\nstyle: {cls.style}\n")
        cls.env = mock.patch.dict(os.environ, {"LAB_CONFIG": str(cls.config_file),
                                               "LAB_DB": str(cls.tmp / "p-lab.db")})
        cls.env.start()
        cls.patches = [mock.patch.object(server, "LABS_DIR", cls.labs),
                       mock.patch.object(instance, "INSTANCES_DIR", None)]
        for patcher in cls.patches:
            patcher.start()
        cls.store = AccountStore()
        cls.store.create_user("admin1", PASSWORD, "admin", "Admin Lab")
        cls.store.create_user("guru1", PASSWORD, "guru", "Bu Guru")
        cls.store.create_user("alice", PASSWORD, "siswa", "Alice A")
        cls.store.create_user("bob", PASSWORD, "siswa", "Bob B")
        # alice: satu sesi yang sudah dinilai di arsipnya. bob: sesi live (belum dinilai).
        cls.alice = Instance(lab, "alice")
        cls.bob = Instance(lab, "bob")
        shutil.copytree(GOLDEN / SCORED, cls.alice.sessions_dir / SCORED)
        shutil.copytree(GOLDEN / ACTIVE, cls.bob.state_dir,
                        ignore=shutil.ignore_patterns("evaluation.*", "expected.yaml", "notes.md"))

    @classmethod
    def tearDownClass(cls):
        server.RUNTIMES.stop_all()
        for patcher in cls.patches:
            patcher.stop()
        cls.env.stop()
        server.configure(config.Config())   # kembali ke mode Pribadi untuk test lain
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        server.configure(config.load(), self.store)   # juga mengosongkan rate limit
        self.no_docker()

    def use(self, **changes):
        """Config server ini dengan kunci tambahan (allowed_hosts, trusted_proxies)."""
        server.configure(dataclasses.replace(config.load(), **changes), self.store)
        self.no_docker()

    def no_docker(self, running=()):
        """Kapasitas tidak membaca docker sungguhan (lab lain yang kebetulan jalan di mesin)."""
        cap = server.AUTH.capacity
        cap.list_running = cap.list_all = lambda: list(running)

    def logged_in(self, username):
        client = Client()
        self.assertEqual(client.login(username).status, 200)
        return client


class TestLogin(ServerCase):
    def test_success_sets_cookie_flags(self):
        client = Client()
        response = client.login("alice")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["user"], {"username": "alice", "display_name": "Alice A", "role": "siswa"})
        cookie = response.header("set-cookie")[0]
        lower = cookie.lower()
        self.assertTrue(cookie.startswith("plab_session="))
        for flag in ("httponly", "samesite=lax", "path=/", f"max-age={self.store.session_ttl}"):
            self.assertIn(flag, lower)
        self.assertNotIn("secure", lower)   # request HTTP biasa
        me = client.get("/api/me").json()
        self.assertEqual((me["mode"], me["style"], me["auth"]), ("server", "mandiri", True))
        self.assertEqual(me["user"]["username"], "alice")
        self.assertIn("deploy", me)
        self.assertIn("llm", me)

    def test_secure_behind_https_proxy(self):
        login = lambda: Client().post("/api/auth/login", {"username": "alice", "password": PASSWORD},  # noqa: E731
                                      headers={"x-forwarded-proto": "https"})
        # Tanpa trusted_proxies header ini dari klien biasa, jadi diabaikan.
        self.assertNotIn("secure", login().header("set-cookie")[0].lower())
        self.use(trusted_proxies=(ipaddress.ip_network("10.0.0.0/24"),))   # Client() = 10.0.0.5
        self.assertIn("secure", login().header("set-cookie")[0].lower())

    def test_wrong_password_and_unknown_user(self):
        for username, password in (("alice", "salah-sekali"), ("tidakada", PASSWORD)):
            response = Client().login(username, password)
            self.assertEqual(response.status, 401)
            self.assertEqual(response.header("set-cookie"), [])

    def test_api_needs_login(self):
        client = Client()
        for path in ("/api/labs", "/api/progress", "/api/leaderboard", "/api/labs/net-001/session", "/api/docs"):
            self.assertEqual(client.get(path).status, 401, path)
        self.assertEqual(client.post("/api/labs/net-001/deploy").status, 401)
        with mock.patch.object(server, "deploy_support") as support:
            me = client.get("/api/me")
        self.assertEqual(me.status, 200)
        self.assertEqual(me.json(), {"mode": "server", "style": "mandiri", "auth": True, "user": None})
        support.assert_not_called()   # subprocess sudo tidak bisa dipicu tanpa login

    def test_forged_cookie_rejected(self):
        client = Client()
        client.cookies["plab_session"] = "token-palsu"
        self.assertEqual(client.get("/api/labs").status, 401)

    def test_logout_ends_session(self):
        client = self.logged_in("alice")
        token = client.cookies["plab_session"]
        self.assertEqual(client.get("/api/labs").status, 200)
        self.assertEqual(client.post("/api/auth/logout").status, 200)
        self.assertNotIn("plab_session", client.cookies)
        client.cookies["plab_session"] = token   # token lama dipakai lagi: sudah mati di DB
        self.assertEqual(client.get("/api/labs").status, 401)

    def test_rate_limit(self):
        client = Client(ip="10.0.0.99")
        for _ in range(server.LoginLimiter.PER_USER):
            self.assertEqual(client.login("bob", "tebakan-salah").status, 401)
        blocked = client.login("bob")   # password benar pun ditolak selama diblokir
        self.assertEqual(blocked.status, 429)
        self.assertTrue(blocked.header("retry-after"))
        self.assertEqual(Client(ip="10.0.0.98").login("bob").status, 200)   # komputer lain tidak ikut terblokir


class TestOrigin(ServerCase):
    def test_foreign_origin_rejected(self):
        client = self.logged_in("alice")
        evil = {"origin": "http://evil.example"}
        self.assertEqual(client.post("/api/labs/net-001/start", headers=evil).status, 403)
        self.assertEqual(client.post("/api/auth/login", {"username": "alice", "password": PASSWORD},
                                     headers=evil).status, 403)
        self.assertEqual(client.get("/api/labs", headers=evil).status, 200)   # GET tidak mengubah state

    def test_same_origin_allowed(self):
        client = Client()
        self.assertEqual(client.post("/api/auth/login", {"username": "alice", "password": PASSWORD},
                                     headers={"origin": f"http://{HOST}"}).status, 200)

    def test_websocket_checks_cookie_and_origin(self):
        self.assertEqual(Client().websocket("/api/labs/net-001/ws")[0], "close")
        bob = self.logged_in("bob")
        self.assertEqual(bob.websocket("/api/labs/net-001/ws", {"origin": "http://evil.example"})[0], "close")
        kind, state = bob.websocket("/api/labs/net-001/ws", {"origin": f"http://{HOST}"})
        self.assertEqual(kind, "message")
        self.assertEqual(state["session"], ACTIVE)

    def test_terminal_resolver(self):
        bob = self.logged_in("bob")

        class FakeSocket:
            def __init__(self, cookies, headers):
                self.cookies, self.headers = cookies, headers

        ok = FakeSocket(dict(bob.cookies), {"host": HOST, "origin": f"http://{HOST}"})
        resolve = lambda ws, lab: asyncio.run(server.terminal_instance(ws, lab))  # noqa: E731
        self.assertEqual(resolve(ok, "net-001"), self.bob)
        self.assertEqual(resolve(ok, "net-001"), self.bob)   # dipanggil ulang (termbridge): hasil sama
        self.assertIsNone(resolve(ok, "tidak-ada"))
        self.assertIsNone(resolve(FakeSocket({}, ok.headers), "net-001"))
        self.assertIsNone(resolve(FakeSocket(bob.cookies, {"host": HOST, "origin": "http://evil.example"}), "net-001"))
        # Cek ulang setelah logout: token divalidasi ke DB tiap panggilan, tidak di-cache.
        self.assertEqual(bob.post("/api/auth/logout").status, 200)
        self.assertIsNone(resolve(ok, "net-001"))

    def test_terminal_resolver_inactive_account(self):
        store = AccountStore()
        store.create_user("carol", PASSWORD, "siswa", "Carol")
        self.addCleanup(store.delete_user, "carol")
        carol = self.logged_in("carol")

        class FakeSocket:
            cookies = dict(carol.cookies)
            headers = {"host": HOST, "origin": f"http://{HOST}"}

        resolve = lambda: asyncio.run(server.terminal_instance(FakeSocket, "net-001"))  # noqa: E731
        self.assertIsNotNone(resolve())
        store.set_active("carol", False)
        self.assertIsNone(resolve())


class TestInstanceIsolation(ServerCase):
    def test_instances_live_in_data_dir(self):
        self.assertEqual(self.alice.dir, self.data / "instances" / "alice" / "net-001")
        self.assertEqual(self.alice.clab_name, "net001-alice")

    def test_session_is_per_user(self):
        bob = self.logged_in("bob").get("/api/labs/net-001/session").json()
        alice = self.logged_in("alice").get("/api/labs/net-001/session").json()
        self.assertEqual(bob["session"], ACTIVE)
        self.assertIsNone(alice["session"])   # sesi live bob tidak terlihat oleh alice

    def test_cannot_hint_or_evaluate_other_instance(self):
        events = self.bob.state_dir / "events" / "host.jsonl"
        before = events.read_text()
        alice = self.logged_in("alice")
        self.assertEqual(alice.post("/api/labs/net-001/hint", {"level": None}).status, 409)
        self.assertEqual(alice.post("/api/labs/net-001/evaluate", {"use_llm": False}).status, 409)
        self.assertEqual(events.read_text(), before)
        self.assertFalse((self.bob.state_dir / "evaluation.json").exists())

    def test_archive_and_progress_are_per_user(self):
        alice, bob = self.logged_in("alice"), self.logged_in("bob")
        self.assertEqual(len(alice.get("/api/progress").json()["sessions"]), 1)
        self.assertEqual(bob.get("/api/progress").json()["sessions"], [])
        self.assertEqual(alice.get(f"/api/labs/net-001/sessions/{SCORED}").json()["kind"], "sessions")
        # Sesi alice tidak terlihat oleh bob; nama yang sama di golden/ milik soal
        # (jawaban expert) juga tertutup untuk siswa.
        self.assertEqual(bob.get(f"/api/labs/net-001/sessions/{SCORED}").status, 404)
        self.assertEqual(bob.get("/api/labs/net-001/sessions/..").status, 404)

    def test_golden_only_for_staff(self):
        golden = "/api/labs/net-001/sessions/" + ACTIVE
        self.assertEqual(self.logged_in("bob").get(golden).status, 404)
        for username in ("guru1", "admin1"):
            response = self.logged_in(username).get(golden)
            self.assertEqual(response.status, 200, username)
            self.assertEqual(response.json()["kind"], "golden")

    def test_student_provider_ignored(self):
        body = {"use_llm": True, "provider": "mahal", "model": "model-mahal"}
        job = {"session": ACTIVE, "status": "running"}
        with mock.patch.object(server.JOBS, "start", return_value=job) as start:
            for username in ("bob", "guru1"):
                start.reset_mock()
                with mock.patch.object(server, "armed", return_value=True):
                    self.assertEqual(self.logged_in(username).post("/api/labs/net-001/evaluate", body).status, 200)
                self.assertEqual(start.call_args.args[2:], (True, None, None), username)
            start.reset_mock()
            with mock.patch.object(server, "armed", return_value=True):
                self.assertEqual(self.logged_in("admin1").post("/api/labs/net-001/evaluate", body).status, 200)
            self.assertEqual(start.call_args.args[2:], (True, "mahal", "model-mahal"))

    def test_deploy_only_touches_own_instance(self):
        # Watcher palsu milik bob (dan milik alice) yang sedang jalan.
        sleeper = lambda: subprocess.Popen(["sleep", "30"])  # noqa: E731
        bob_proc, alice_proc = sleeper(), sleeper()
        self.addCleanup(lambda: [p.kill() for p in (bob_proc, alice_proc)])
        server.RUNTIMES.procs[self.bob] = (ACTIVE, bob_proc)
        server.RUNTIMES.procs[self.alice] = ("lama", alice_proc)
        log = self.labs / "net-001" / "deployed.log"
        log.unlink(missing_ok=True)
        support = {"available": True, "mode": "setuid", "reason": None}
        with mock.patch.object(server, "deploy_support", return_value=support), \
                mock.patch.object(server, "missing_images", return_value=[]):
            response = self.logged_in("alice").post("/api/labs/net-001/deploy")
            self.assertEqual(response.status, 200, response.body)
            for _ in range(100):
                job = server.DEPLOYS.get(self.alice)
                if job["status"] != "running":
                    break
                time.sleep(0.05)
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(log.read_text().split(), ["alice", "net001-alice"])
        self.assertIsNone(bob_proc.poll())                 # watcher bob tetap hidup
        self.assertIn(self.bob, server.RUNTIMES.procs)
        self.assertIsNotNone(alice_proc.wait(timeout=5))   # watcher alice dihentikan sebelum reset.sh
        self.assertIsNone(server.DEPLOYS.get(self.bob))


class DeployCase(ServerCase):
    support = {"available": True, "mode": "setuid", "reason": None}

    def deploy(self, username):
        with mock.patch.object(server, "deploy_support", return_value=self.support), \
                mock.patch.object(server, "missing_images", return_value=[]):
            return self.logged_in(username).post("/api/labs/net-001/deploy")

    def wait(self, inst):
        for _ in range(100):
            job = server.DEPLOYS.get(inst)
            if job and job["status"] != "running":
                return job
            time.sleep(0.05)
        self.fail("deploy tidak selesai")


class TestCapacityWiring(DeployCase):
    """Kapasitas (capacity.py) tersambung ke deploy dan reaper server."""

    def test_memory_full_rejected(self):
        self.use(capacity=config.Capacity(mem_mb=100, max_deploys=2, idle_minutes=30))
        response = self.deploy("alice")
        self.assertEqual(response.status, 503, response.body)
        self.assertIn("RAM", response.json()["detail"])
        self.assertIsNone(server.DEPLOYS.get(self.alice))

    def test_reservation_released_after_deploy(self):
        response = self.deploy("alice")
        self.assertEqual(response.status, 200, response.body)
        self.assertEqual(self.wait(self.alice)["status"], "done")
        self.assertEqual(server.AUTH.capacity.deploying, {})

    def test_other_lab_of_user_destroyed_first(self):
        other = mock.Mock(problem_dir=Path("/x/net-009"), user="alice")
        decision = capacity.Decision(True, None, "ok", [other], 150, 0, 24000)
        with mock.patch.object(server.AUTH.capacity, "try_acquire", return_value=decision), \
                mock.patch.object(server, "evaluating", return_value=False), \
                mock.patch.object(server.capacity, "destroy") as destroy, \
                mock.patch.object(server.AUTH.capacity, "release_deploy") as release:
            self.assertEqual(self.deploy("alice").status, 200)
            self.assertEqual(self.wait(self.alice)["status"], "done")
        destroy.assert_called_once_with(other, reason="replaced")
        release.assert_called_once_with(self.alice)

    def test_reaper_stops_orphan_lab(self):
        self.store.set_active("bob", False)
        self.addCleanup(self.store.set_active, "bob", True)
        self.no_docker(running=["net001-bob", "net001-alice"])
        with mock.patch.object(server.capacity, "destroy") as destroy, \
                mock.patch.object(server.AUTH.capacity, "idle_candidates", return_value=[]):
            targets = server.reap_labs_once()
        self.assertEqual({i.user: r for i, r in targets.items()}, {"bob": "orphan"})
        destroy.assert_called_once()
        self.assertEqual(destroy.call_args.args[0].user, "bob")


class TestDeployRobust(DeployCase):
    """Temuan review: job macet, reservasi ganda, penilaian terbunuh, deploy macet, WS bocor."""

    def test_unexpected_error_marks_job_failed(self):
        other = mock.Mock(problem_dir=Path("/x/net-009"), user="alice")
        decision = capacity.Decision(True, None, "ok", [other], 150, 0, 24000)
        with mock.patch.object(server.AUTH.capacity, "try_acquire", return_value=decision), \
                mock.patch.object(server, "evaluating", return_value=False), \
                mock.patch.object(server.capacity, "destroy", side_effect=OSError("No space left on device")), \
                mock.patch.object(server.AUTH.capacity, "release_deploy") as release:
            self.assertEqual(self.deploy("alice").status, 200)
            job = self.wait(self.alice)
        self.assertEqual(job["status"], "error")
        self.assertIn("No space left", job["error"])
        self.assertFalse(server.DEPLOYS.busy("alice"))    # user tidak terkunci
        release.assert_called_once_with(self.alice)

    def test_double_request_keeps_single_reservation(self):
        block = threading.Event()
        self.addCleanup(block.set)

        def fake_deploy(job, *_):
            block.wait(10)
            job.update(status="done", step="done", finished=time.time())

        with mock.patch.object(server.DEPLOYS, "_deploy", side_effect=fake_deploy):
            client = self.logged_in("alice")
            with mock.patch.object(server, "deploy_support", return_value=self.support), \
                    mock.patch.object(server, "missing_images", return_value=[]):
                self.assertEqual(client.post("/api/labs/net-001/deploy").status, 200)
                self.assertEqual(client.post("/api/labs/net-001/deploy").status, 200)
            self.assertIn(self.alice, server.AUTH.capacity.deploying)   # masih milik job yang berjalan
            block.set()
            for _ in range(100):
                if not server.AUTH.capacity.deploying:
                    break
                time.sleep(0.05)
        self.assertEqual(server.AUTH.capacity.deploying, {})

    def test_deploy_refused_while_other_lab_is_graded(self):
        other = mock.Mock(problem_dir=Path("/x/net-009"), user="alice")
        decision = capacity.Decision(True, None, "ok", [other], 150, 0, 24000)
        with mock.patch.object(server.AUTH.capacity, "try_acquire", return_value=decision), \
                mock.patch.object(server, "evaluating", side_effect=lambda inst: inst is other), \
                mock.patch.object(server.capacity, "destroy") as destroy, \
                mock.patch.object(server.AUTH.capacity, "release_deploy") as release:
            response = self.deploy("alice")
        self.assertEqual(response.status, 409, response.body)
        self.assertIn("dinilai", response.json()["detail"])
        destroy.assert_not_called()
        release.assert_called_once_with(self.alice)

    def test_hung_deploy_is_killed(self):
        lab = Path(tempfile.mkdtemp(prefix="plab-hang-"))
        self.addCleanup(shutil.rmtree, lab, True)
        script = lab / "reset.sh"
        # Anak proses ikut memegang stdout: kill proses induk saja tidak mengakhiri pembacaan.
        script.write_text("#!/usr/bin/env bash\nsleep 60 &\nwait\n")
        script.chmod(0o755)
        job = {"status": "running", "step": None, "started": time.time(), "error": None, "log": []}
        with mock.patch.object(server, "DEPLOY_TIMEOUT", 0.3):
            started = time.monotonic()
            server.DEPLOYS._deploy(job, lab, None, None, ())
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(job["status"], "error")
        self.assertIn("melewati", job["error"])

    def test_reaper_respects_open_page_and_survives_errors(self):
        self.no_docker(running=["net001-bob", "net001-alice"])
        server.AUTH.capacity.cap = dataclasses.replace(server.AUTH.capacity.cap, idle_minutes=1)
        old = time.time() - 3600
        with mock.patch.object(capacity, "last_activity", return_value=old), \
                mock.patch.object(server, "LAST_SEEN", {self.alice: time.time()}), \
                mock.patch.object(server.capacity, "destroy", side_effect=OSError("boom")) as destroy:
            targets = server.reap_labs_once()     # exception per instance tidak keluar dari putaran
        self.assertEqual({i.user for i in targets}, {"bob"})   # halaman alice masih terbuka
        destroy.assert_called_once()

    def test_ws_handler_ends_on_disconnect(self):
        client = self.logged_in("bob")
        scope = {"type": "websocket", "asgi": {"version": "3.0"}, "scheme": "ws", "path": "/api/labs/net-001/ws",
                 "raw_path": b"/api/labs/net-001/ws", "query_string": b"", "root_path": "",
                 "headers": client._headers(None), "client": (client.ip, 50000), "server": (HOST, 80),
                 "subprotocols": []}

        async def run():
            incoming = asyncio.Queue()
            await incoming.put({"type": "websocket.connect"})
            first = asyncio.Event()

            async def send(message):
                if message["type"] == "websocket.send":
                    first.set()

            task = asyncio.create_task(server.app(scope, incoming.get, send))
            await asyncio.wait_for(first.wait(), 10)
            await incoming.put({"type": "websocket.disconnect", "code": 1001})
            await asyncio.wait_for(task, 5)   # state tidak berubah: handler tetap harus selesai

        asyncio.run(run())


class TestMandiriBoard(ServerCase):
    def test_everyone_named(self):
        board = self.logged_in("bob").get("/api/leaderboard").json()
        names = {e["name"] for e in board}
        self.assertEqual(names, {"Admin Lab", "Bu Guru", "Alice A", "Bob B"})
        self.assertEqual(board[0]["username"], "alice")   # satu-satunya yang punya poin
        self.assertGreater(board[0]["points"], 0)
        self.assertEqual([e["username"] for e in board if e["you"]], ["bob"])
        self.assertFalse(any(e.get("golden") for e in board))

    def test_class_progress_only_in_kelas(self):
        self.assertEqual(self.logged_in("guru1").get("/api/class/progress").status, 404)


class TestKelas(ServerCase):
    style = "kelas"

    def test_student_sees_classmates_anonymously(self):
        board = self.logged_in("bob").get("/api/leaderboard").json()
        self.assertEqual(len(board), 2)   # hanya siswa yang diperingkat
        mine = [e for e in board if e["you"]]
        others = [e for e in board if not e["you"]]
        self.assertEqual(mine[0]["name"], "Bob B")
        self.assertTrue(others[0]["anonymous"])
        self.assertNotIn("username", others[0])
        self.assertNotIn("Alice", json.dumps(board))
        self.assertNotIn("alice", json.dumps(board))
        self.assertGreater(others[0]["points"], 0)

    def test_anonymous_order_not_by_username(self):
        # Baris anonim diacak per request sebelum diurutkan poin (sort stabil).
        with mock.patch.object(server.random, "shuffle") as shuffle:
            self.logged_in("bob").get("/api/leaderboard")
            shuffle.assert_called_once()
            shuffle.reset_mock()
            self.logged_in("guru1").get("/api/leaderboard")
            shuffle.assert_not_called()

    def test_teacher_sees_names(self):
        board = self.logged_in("guru1").get("/api/leaderboard").json()
        self.assertEqual({e["username"] for e in board}, {"alice", "bob"})
        self.assertFalse(any(e["you"] for e in board))


class TestHostCheck(ServerCase):
    """allowed_hosts: header Host lain ditolak (DNS rebinding) untuk HTTP dan WebSocket."""

    def setUp(self):
        self.use(allowed_hosts=(HOST, "192.168.1.10"))

    def test_unknown_host_rejected(self):
        evil = Client(host="evil.example:8000")
        self.assertEqual(evil.get("/api/me").status, 400)
        self.assertEqual(evil.get("/").status, 400)   # file SPA juga
        self.assertEqual(evil.post("/api/auth/login", {"username": "alice", "password": PASSWORD},
                                   headers={"origin": "http://evil.example:8000"}).status, 400)

    def test_allowed_hosts_any_port(self):
        for host in (HOST, f"{HOST}:8000", "192.168.1.10:8000", "localhost:8000", "127.0.0.1", "[::1]:8000"):
            client = Client(host=host)
            response = client.post("/api/auth/login", {"username": "alice", "password": PASSWORD},
                                   headers={"origin": f"http://{host}"})
            self.assertEqual(response.status, 200, host)

    def test_websocket_rejects_unknown_host(self):
        bob = self.logged_in("bob")
        bob.host = "evil.example"   # cookie bob ikut, Origin = Host: tetap ditolak
        self.assertEqual(bob.websocket("/api/labs/net-001/ws", {"origin": "http://evil.example"})[0], "close")

    def test_empty_allowed_hosts_warns_once(self):
        self.use(allowed_hosts=())
        server._warned_any_host = False
        with self.assertLogs("p-lab.server", "WARNING") as logs:
            self.assertEqual(Client(host="apa.saja").get("/api/me").status, 200)
            Client(host="lain.lagi").get("/api/me")
        self.assertEqual(sum("allowed_hosts" in line for line in logs.output), 1)


class TestProxy(ServerCase):
    """X-Forwarded-For hanya dipercaya dari trusted_proxies (batas login gagal)."""

    PROXY = "10.0.0.77"

    def fail(self, xff):
        return Client(ip=self.PROXY).post("/api/auth/login", {"username": "bob", "password": "tebakan-salah"},
                                          headers={"x-forwarded-for": xff})

    def login_from(self, xff):
        return Client(ip=self.PROXY).post("/api/auth/login", {"username": "bob", "password": PASSWORD},
                                          headers={"x-forwarded-for": xff})

    def test_xff_ignored_without_trusted_proxies(self):
        for i in range(server.LoginLimiter.PER_USER):
            self.assertEqual(self.fail(f"1.1.1.{i}").status, 401)
        # Header palsu tidak menolong: kunci tetap IP koneksi.
        self.assertEqual(self.login_from("9.9.9.9").status, 429)

    def test_xff_from_trusted_proxy(self):
        self.use(trusted_proxies=(ipaddress.ip_network(self.PROXY),))
        for _ in range(server.LoginLimiter.PER_USER):
            self.assertEqual(self.fail("1.2.3.4").status, 401)
        self.assertEqual(self.login_from("1.2.3.4").status, 429)
        # Klien menambah entri palsu di kiri: yang dipakai tetap entri tak tepercaya paling kanan.
        self.assertEqual(self.login_from("5.6.7.8, 1.2.3.4").status, 429)
        self.assertEqual(self.login_from("5.6.7.8").status, 200)   # klien lain di belakang proxy

    def test_chain_of_trusted_proxies(self):
        self.use(trusted_proxies=(ipaddress.ip_network("10.0.0.0/24"),))
        for _ in range(server.LoginLimiter.PER_USER):
            self.fail("1.2.3.4, 10.0.0.9")
        self.assertEqual(self.login_from("1.2.3.4").status, 429)


class TestPribadi(unittest.TestCase):
    """Tanpa config server: tanpa login, instance `local`, perilaku lama."""

    def setUp(self):
        server.configure(config.Config())
        patcher = mock.patch.object(server, "LABS_DIR", LABS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dns_rebinding_rejected(self):
        # Situs jahat me-rebind evil.example ke 127.0.0.1: Origin = Host = evil.example.
        evil = Client(host="evil.example:8000")
        same = {"origin": "http://evil.example:8000"}
        self.assertEqual(evil.get("/api/labs").status, 400)
        self.assertEqual(evil.post("/api/labs/net-001/start", headers=same).status, 400)
        self.assertEqual(evil.post("/api/labs/net-001/hint", {"level": None}, headers=same).status, 400)
        self.assertEqual(evil.post("/api/labs/net-001/evaluate", {"use_llm": False}, headers=same).status, 400)
        self.assertEqual(evil.websocket("/api/labs/net-001/ws", same)[0], "close")

    def test_terminal_resolver_checks_host(self):
        class FakeSocket:
            def __init__(self, host):
                self.cookies, self.headers = {}, {"host": host, "origin": f"http://{host}"}

        resolve = lambda host: asyncio.run(server.terminal_instance(FakeSocket(host), "net-001"))  # noqa: E731
        self.assertIsNone(resolve("evil.example:8000"))
        self.assertIsNone(resolve("192.168.1.10:8000"))   # IP LAN pun tidak: pribadi hanya loopback
        for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000"):
            self.assertEqual(resolve(host).user, "local", host)

    def test_loopback_hosts_allowed(self):
        for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000", "localhost:5173", "localhost"):
            self.assertEqual(Client(host=host).get("/api/me").status, 200, host)
        self.assertEqual(Client(host="localhost.evil.example").get("/api/me").status, 400)
        self.assertEqual(Client(host="").get("/api/me").status, 400)

    def test_cross_origin_between_loopback_names_rejected(self):
        client = Client(host="localhost:8000")
        self.assertEqual(client.post("/api/labs/net-001/start", headers={"origin": "http://127.0.0.1:9999"}).status,
                         403)

    def test_no_login_needed(self):
        client = Client(host="localhost:8000")
        me = client.get("/api/me").json()
        self.assertEqual((me["mode"], me["auth"]), ("pribadi", False))
        self.assertEqual(me["user"]["username"], "local")
        self.assertEqual(me["user"]["display_name"], server.USER)
        self.assertEqual(client.get("/api/labs").status, 200)
        self.assertEqual(client.post("/api/auth/login", {"username": "x", "password": "y"}).status, 404)
        self.assertEqual(client.get("/api/class/progress").status, 404)

    def test_foreign_origin_still_rejected(self):
        # Pribadi tanpa cookie: Origin satu-satunya pelindung dari situs lain yang POST ke localhost.
        self.assertEqual(Client(host="localhost:8000").post("/api/labs/net-001/start",
                                                            headers={"origin": "http://evil.example"}).status, 403)

    def test_instance_local(self):
        self.assertEqual(server.instance(LABS / "net-001", server.local_user()).state_dir,
                         (LABS / "net-001" / ".state").resolve())


if __name__ == "__main__":
    unittest.main()
