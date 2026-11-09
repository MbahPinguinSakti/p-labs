"""Test API admin akun (admin_accounts.py), lewat HTTP seperti test_auth.py."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import accounts  # noqa: E402
import config  # noqa: E402
import dashboard  # noqa: E402
import server  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from test_auth import PASSWORD, Client, ServerCase  # noqa: E402

USERS = "/api/admin/users"


class AdminCase(ServerCase):
    def setUp(self):
        super().setUp()
        self.stopped = []
        self.fail_for = set()
        original = dashboard.H.stop_lab

        def fake_stop(inst, reason):
            if (inst.problem_dir.name, inst.user) in self.fail_for:
                raise HTTPException(409, "sibuk")
            self.stopped.append((inst.problem_dir.name, inst.user, reason))
            return None

        dashboard.bind(stop_lab=fake_stop)
        self.addCleanup(dashboard.bind, stop_lab=original)
        self.created = []

    def tearDown(self):
        # Kembalikan keadaan akun bersama (ServerCase memakai satu DB per kelas).
        for name in self.created:
            try:
                self.store.delete_user(name)
            except accounts.AccountError:
                pass
        for name, role in (("admin1", "admin"), ("guru1", "guru"), ("alice", "siswa"), ("bob", "siswa")):
            self.store.set_active(name, True)
            self.store.set_role(name, role)
        self.store.set_display_name("alice", "Alice A")
        self.store.set_password("alice", PASSWORD)

    def make(self, username, **extra):
        self.created.append(username)
        return {"username": username, **extra}

    def admin(self):
        return self.logged_in("admin1")

    def patch(self, client, username, body):
        return client.request("PATCH", f"{USERS}/{username}", body)


class TestAccess(AdminCase):
    def test_roles_and_anonymous(self):
        calls = [("GET", USERS, None), ("POST", USERS, {"username": "x1"}),
                 ("POST", USERS + "/import", {"csv": "username\nx1\n"}),
                 ("PATCH", USERS + "/alice", {"display_name": "X"}),
                 ("POST", USERS + "/alice/password", {})]
        for method, path, body in calls:
            self.assertEqual(Client().request(method, path, body).status, 401, path)
            for who in ("alice", "guru1"):
                self.assertEqual(self.logged_in(who).request(method, path, body).status, 403, (who, path))

    def test_pribadi_is_404(self):
        server.configure(config.Config())
        try:
            self.assertEqual(Client(host="localhost:8000").get(USERS).status, 404)
        finally:
            server.configure(config.load(), self.store)
            self.no_docker()


class TestList(AdminCase):
    def test_list_shape_and_last_seen(self):
        admin = self.admin()
        users = admin.get(USERS).json()["users"]
        self.assertEqual([u["username"] for u in users], ["admin1", "alice", "bob", "guru1"])
        alice = users[1]
        self.assertEqual(set(alice), {"username", "display_name", "role", "active", "created_at", "last_seen"})
        self.assertEqual((alice["display_name"], alice["role"], alice["active"]), ("Alice A", "siswa", True))
        self.assertNotIn("pw_hash", admin.get(USERS).body.decode())
        self.assertIsNotNone(users[0]["last_seen"])   # admin1 baru login
        self.logged_in("alice")
        users = {u["username"]: u for u in admin.get(USERS).json()["users"]}
        self.assertIsNotNone(users["alice"]["last_seen"])


class TestCreate(AdminCase):
    def test_random_password(self):
        admin = self.admin()
        r = admin.post(USERS, self.make("baru1", display_name="Siswa Baru"))
        self.assertEqual(r.status, 201)
        data = r.json()
        self.assertEqual(data["user"]["username"], "baru1")
        self.assertEqual((data["user"]["role"], data["user"]["active"], data["user"]["last_seen"]),
                         ("siswa", True, None))
        self.assertTrue(data["password"])
        self.assertEqual(Client().login("baru1", data["password"]).status, 200)

    def test_given_password_not_echoed(self):
        admin = self.admin()
        r = admin.post(USERS, self.make("baru2", role="guru", password="password-pilihan"))
        self.assertEqual(r.status, 201)
        self.assertIsNone(r.json()["password"])
        self.assertEqual(r.json()["user"]["role"], "guru")
        self.assertEqual(Client().login("baru2", "password-pilihan").status, 200)

    def test_duplicate_and_invalid(self):
        admin = self.admin()
        self.assertEqual(admin.post(USERS, {"username": "alice"}).status, 409)
        self.assertEqual(admin.post(USERS, {"username": "Bad Name"}).status, 400)
        self.assertEqual(admin.post(USERS, {"username": "local"}).status, 400)
        self.assertEqual(admin.post(USERS, self.make("baru3", role="dewa")).status, 400)
        self.assertEqual(admin.post(USERS, self.make("baru3", password="pendek")).status, 400)
        self.assertEqual(admin.post(USERS, self.make("baru3", role="siswa")).status, 201)


class TestImport(AdminCase):
    def test_import_with_errors(self):
        admin = self.admin()
        for n in ("imp1", "imp2"):
            self.created.append(n)
        csv = ("username,display_name,role,password\n"
               "imp1,Imp Satu,siswa,\n"
               "imp2,Imp Dua,guru,password-dua\n"
               "alice,Dobel,siswa,\n"
               "../x,Buruk,siswa,\n")
        r = admin.post(USERS + "/import", {"csv": csv})
        self.assertEqual(r.status, 200)
        data = r.json()
        self.assertEqual([c["username"] for c in data["created"]], ["imp1", "imp2"])
        self.assertTrue(data["created"][0]["password"])
        self.assertIsNone(data["created"][1]["password"])
        self.assertEqual([e["line"] for e in data["errors"]], [4, 5])
        self.assertIn("sudah dipakai", data["errors"][0]["message"])

    def test_default_role_and_bad_header(self):
        admin = self.admin()
        self.created.append("imp3")
        r = admin.post(USERS + "/import", {"csv": "username\nimp3\n", "default_role": "guru"})
        self.assertEqual(r.status, 200)
        self.assertEqual(self.store.get_user("imp3")["role"], "guru")
        self.assertEqual(admin.post(USERS + "/import", {"csv": "nama\nx\n"}).status, 400)
        self.assertEqual(admin.post(USERS + "/import", {"csv": "username\nx\n", "default_role": "dewa"}).status, 400)

    def test_too_large(self):
        r = self.admin().post(USERS + "/import", {"csv": "username\n" + "a" * (256 * 1024)})
        self.assertEqual(r.status, 413)


class TestPatch(AdminCase):
    def test_name_role_active(self):
        admin = self.admin()
        r = self.patch(admin, "alice", {"display_name": "  Alice Baru "})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.json()["user"]["display_name"], "Alice Baru")
        self.assertEqual(r.json()["stopped_labs"], [])
        r = self.patch(admin, "alice", {"role": "guru"})
        self.assertEqual(r.json()["user"]["role"], "guru")
        r = self.patch(admin, "alice", {"active": False})
        self.assertFalse(r.json()["user"]["active"])
        r = self.patch(admin, "alice", {"active": True})
        self.assertTrue(r.json()["user"]["active"])

    def test_validation_and_not_found(self):
        admin = self.admin()
        self.assertEqual(self.patch(admin, "alice", {"role": "dewa"}).status, 400)
        self.assertEqual(self.patch(admin, "alice", {"display_name": "  "}).status, 400)
        self.assertEqual(self.patch(admin, "hantu", {"active": False}).status, 404)
        self.assertEqual(self.patch(admin, "Bad..Name", {"active": False}).status, 404)
        self.assertEqual(admin.post(USERS + "/hantu/password", {}).status, 404)

    def test_self_restrictions(self):
        admin = self.admin()
        self.assertEqual(self.patch(admin, "admin1", {"role": "guru"}).status, 409)
        self.assertEqual(self.patch(admin, "admin1", {"active": False}).status, 409)
        r = self.patch(admin, "admin1", {"display_name": "Admin Baru"})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.json()["user"]["display_name"], "Admin Baru")
        self.store.set_display_name("admin1", "Admin Lab")

    def test_last_admin_is_409(self):
        # Lewat HTTP aktor selalu admin aktif, jadi "admin terakhir" hanya tercapai kalau
        # target = aktor (ditolak lebih dulu) atau balapan. Uji pemetaan errornya dengan store palsu.
        admin = self.admin()
        self.store.create_user("admin2", PASSWORD, "admin")
        self.created.append("admin2")
        error = accounts.AccountError("Tidak bisa menurunkan role: ini admin aktif terakhir.")
        with mock.patch.object(self.store, "set_role", side_effect=error):
            r = self.patch(admin, "admin2", {"role": "guru"})
        self.assertEqual(r.status, 409)
        self.assertIn("admin aktif terakhir", r.json()["detail"])
        with mock.patch.object(self.store, "set_active", side_effect=error):
            self.assertEqual(self.patch(admin, "admin2", {"active": False}).status, 409)
        # Tanpa palsu: dengan dua admin aktif, menurunkan admin2 boleh.
        self.assertEqual(self.patch(admin, "admin2", {"role": "guru"}).status, 200)

    def test_deactivate_stops_only_that_users_labs(self):
        self.no_docker(running=["net001-alice", "net001-bob"])
        admin = self.admin()
        alice = self.logged_in("alice")
        self.assertEqual(alice.get("/api/me").status, 200)
        r = self.patch(admin, "alice", {"active": False})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.json()["stopped_labs"], ["net-001"])
        self.assertEqual(self.stopped, [("net-001", "alice", "orphan")])
        self.assertEqual(alice.get("/api/labs").status, 401)   # cookie lama mati seketika
        self.assertIsNone(self.store.login("alice", PASSWORD))

    def test_stop_failure_is_skipped(self):
        self.no_docker(running=["net001-alice"])
        self.fail_for.add(("net-001", "alice"))
        r = self.patch(self.admin(), "alice", {"active": False})
        self.assertEqual(r.status, 200)
        self.assertFalse(r.json()["user"]["active"])
        self.assertEqual(r.json()["stopped_labs"], [])

    def test_reactivate_does_not_stop_labs(self):
        self.store.set_active("alice", False)
        self.no_docker(running=["net001-alice"])
        r = self.patch(self.admin(), "alice", {"active": True})
        self.assertEqual(r.json()["stopped_labs"], [])
        self.assertEqual(self.stopped, [])


class TestPassword(AdminCase):
    def test_random_reset_logs_out(self):
        admin = self.admin()
        alice = self.logged_in("alice")
        r = admin.post(USERS + "/alice/password", {})
        self.assertEqual(r.status, 200)
        new = r.json()["password"]
        self.assertTrue(new)
        self.assertEqual(Client().login("alice", PASSWORD).status, 401)
        self.assertEqual(Client().login("alice", new).status, 200)
        self.assertEqual(alice.get("/api/labs").status, 401)

    def test_given_and_invalid(self):
        admin = self.admin()
        r = admin.post(USERS + "/alice/password", {"password": "pilihan-baru-1"})
        self.assertEqual(r.status, 200)
        self.assertIsNone(r.json()["password"])
        self.assertEqual(Client().login("alice", "pilihan-baru-1").status, 200)
        self.assertEqual(admin.post(USERS + "/alice/password", {"password": "pendek"}).status, 400)

    def test_password_never_logged(self):
        with self.assertNoLogs("p-lab.admin_accounts", level="DEBUG"):
            r = self.admin().post(USERS + "/bob/password", {})
        self.assertEqual(r.status, 200)


class TestReviewFixes(AdminCase):
    def test_self_password_reset_refused(self):
        admin = self.admin()
        r = admin.post(USERS + "/admin1/password", {})
        self.assertEqual(r.status, 409)
        self.assertIn("p-lab-admin", r.json()["detail"])
        self.assertEqual(admin.get(USERS).status, 200)   # sesi admin tidak ikut hilang

    def test_long_name_rejected_before_any_change(self):
        admin = self.admin()
        r = self.patch(admin, "alice", {"role": "guru", "display_name": "x" * 101})
        self.assertEqual(r.status, 400)
        self.assertEqual(self.store.get_user("alice")["role"], "siswa")
        r = admin.post(USERS, self.make("panjang", display_name="y" * 500))
        self.assertEqual(r.status, 400)
        self.assertIsNone(self.store.get_user("panjang"))

    def test_import_bom_and_semicolon(self):
        admin = self.admin()
        for name, text in (("bom1", "\ufeffusername,display_name\nbom1,Bom Satu\n"),
                           ("semi1", "username;display_name;role\nsemi1;Semi Satu;guru\n")):
            self.created.append(name)
            r = admin.post(USERS + "/import", {"csv": text})
            self.assertEqual(r.status, 200, r.body)
            self.assertEqual([c["username"] for c in r.json()["created"]], [name])
        self.assertEqual(self.store.get_user("semi1")["role"], "guru")
        self.assertEqual(self.store.get_user("semi1")["display_name"], "Semi Satu")

    def test_busy_lab_reported_as_skipped(self):
        self.no_docker(running=["net001-alice"])
        self.fail_for.add(("net-001", "alice"))
        r = self.patch(self.admin(), "alice", {"active": False})
        self.assertEqual(r.json()["skipped_labs"], ["net-001"])


if __name__ == "__main__":
    unittest.main()
