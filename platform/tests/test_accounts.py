"""Test modul akun. Jalankan: python3 -m unittest discover -s platform/tests"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import accounts  # noqa: E402
from accounts import AccountError, AccountStore  # noqa: E402

CLI = Path(__file__).resolve().parent.parent / "p-lab-admin"


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "sub" / "p-lab.db"
        self.clock = Clock()
        self.store = AccountStore(self.db, clock=self.clock)


class TestPassword(unittest.TestCase):
    def test_hash_and_verify(self):
        h = accounts.hash_password("rahasia123")
        self.assertTrue(h.startswith("scrypt$"))
        self.assertTrue(accounts.verify_password("rahasia123", h))
        self.assertFalse(accounts.verify_password("salah12345", h))

    def test_salt_differs(self):
        self.assertNotEqual(accounts.hash_password("sama-saja-1"), accounts.hash_password("sama-saja-1"))

    def test_garbage_hash_is_rejected(self):
        self.assertFalse(accounts.verify_password("x", "bukan-hash"))

    def test_params_stored_in_hash(self):
        # hash dengan parameter lain tetap bisa diverifikasi
        import base64
        salt = b"0" * 16
        d = accounts._scrypt("pw-panjang-1", salt, 2 ** 10, 8, 1)
        b = lambda x: base64.b64encode(x).decode()
        self.assertTrue(accounts.verify_password("pw-panjang-1", f"scrypt$1024$8$1${b(salt)}${b(d)}"))

    def test_policy(self):
        with self.assertRaises(AccountError) as ctx:
            accounts.check_password_policy("pendek")
        self.assertIn("minimal 8", str(ctx.exception))


class TestUsers(Base):
    def test_create_and_get(self):
        u = self.store.create_user("budi-1", "password1", "siswa", "Budi")
        self.assertEqual(self.store.get_user("budi-1"), u)
        self.assertEqual(self.store.get_user(u["id"])["display_name"], "Budi")
        self.assertNotIn("pw_hash", u)
        self.assertIsNone(self.store.get_user("tidak-ada"))

    def test_display_name_defaults_to_username(self):
        self.assertEqual(self.store.create_user("ani", "password1")["display_name"], "ani")

    def test_duplicate(self):
        self.store.create_user("ani", "password1")
        with self.assertRaises(AccountError):
            self.store.create_user("ani", "password2")

    def test_bad_usernames(self):
        for bad in ("../x", "Budi", "", "a" * 33, "a b", "a/b", "x\n", "é", None):
            with self.assertRaises(AccountError, msg=repr(bad)):
                self.store.create_user(bad, "password1")
        self.store.create_user("a" * 32, "password1")

    def test_bad_role(self):
        with self.assertRaises(AccountError):
            self.store.create_user("ani", "password1", "root")

    def test_last_admin_protected(self):
        self.store.create_user("boss", "password1", "admin")
        with self.assertRaises(AccountError):
            self.store.set_role("boss", "guru")
        with self.assertRaises(AccountError):
            self.store.set_active("boss", False)
        with self.assertRaises(AccountError):
            self.store.delete_user("boss")
        self.store.create_user("boss2", "password1", "admin")
        self.assertEqual(self.store.set_role("boss", "guru")["role"], "guru")
        self.assertEqual(self.store.count_admins(), 1)

    def test_list_filter(self):
        self.store.create_user("g1", "password1", "guru")
        self.store.create_user("s1", "password1")
        self.assertEqual([u["username"] for u in self.store.list_users("guru")], ["g1"])
        self.assertEqual(len(self.store.list_users()), 2)

    def test_delete_removes_sessions(self):
        self.store.create_user("s1", "password1")
        token = self.store.login("s1", "password1")
        self.store.delete_user("s1")
        self.assertIsNone(self.store.user_for_token(token))


class TestSessions(Base):
    def setUp(self):
        super().setUp()
        self.store.create_user("s1", "password1", "siswa", "Satu")

    def test_login_flow(self):
        token = self.store.login("s1", "password1")
        self.assertTrue(token)
        self.assertEqual(self.store.user_for_token(token)["username"], "s1")
        self.store.logout(token)
        self.assertIsNone(self.store.user_for_token(token))

    def test_wrong_password_and_unknown_user(self):
        self.assertIsNone(self.store.login("s1", "salahsalah"))
        self.assertIsNone(self.store.login("hantu", "password1"))
        self.assertIsNone(self.store.login("s1", None))

    def test_inactive_rejected(self):
        self.store.create_user("a", "password1", "admin")
        self.store.set_active("s1", False)
        self.assertIsNone(self.store.login("s1", "password1"))
        self.store.set_active("s1", True)
        self.assertTrue(self.store.login("s1", "password1"))

    def test_deactivate_kills_sessions(self):
        self.store.create_user("a", "password1", "admin")
        token = self.store.login("s1", "password1")
        self.store.set_active("s1", False)
        self.assertIsNone(self.store.user_for_token(token))

    def test_expiry_with_clock(self):
        token = self.store.login("s1", "password1")
        self.clock.t += accounts.SESSION_TTL - 1
        self.assertIsNotNone(self.store.user_for_token(token))
        self.clock.t += 1
        self.assertIsNone(self.store.user_for_token(token))

    def test_purge_expired(self):
        self.store.login("s1", "password1")
        self.clock.t += accounts.SESSION_TTL + 1
        fresh = self.store.login("s1", "password1")
        self.assertEqual(self.store.purge_expired(), 1)
        self.assertIsNotNone(self.store.user_for_token(fresh))

    def test_token_stored_as_hash(self):
        token = self.store.login("s1", "password1")
        with self.store._connect() as db:
            hashes = [r[0] for r in db.execute("SELECT token_hash FROM login_sessions")]
        self.assertEqual(len(hashes), 1)
        self.assertNotEqual(hashes[0], token)
        self.assertEqual(hashes[0], accounts._token_hash(token))
        self.assertNotIn(token.encode(), self.db.read_bytes())

    def test_last_seen_updates(self):
        token = self.store.login("s1", "password1")
        self.clock.t += 60
        self.store.user_for_token(token)
        with self.store._connect() as db:
            self.assertEqual(db.execute("SELECT last_seen FROM login_sessions").fetchone()[0], self.clock.t)

    def test_logout_all_and_password_reset(self):
        t1, t2 = self.store.login("s1", "password1"), self.store.login("s1", "password1")
        self.assertNotEqual(t1, t2)
        self.store.logout_all("s1")
        self.assertIsNone(self.store.user_for_token(t1))
        t3 = self.store.login("s1", "password1")
        self.store.set_password("s1", "passwordbaru")
        self.assertIsNone(self.store.user_for_token(t3))
        self.assertIsNone(self.store.login("s1", "password1"))
        self.assertTrue(self.store.login("s1", "passwordbaru"))

    def test_garbage_tokens(self):
        for t in (None, "", "abc", 123):
            self.assertIsNone(self.store.user_for_token(t))


class TestImport(Base):
    def test_success_and_random_password(self):
        csv_text = ("username,display_name,role,password\n"
                    "ani,Ani Wijaya,siswa,password123\n"
                    "bu-guru,Bu Guru,guru,\n")
        result = self.store.import_csv(io.StringIO(csv_text))
        self.assertEqual(result.errors, [])
        self.assertEqual([u for u, _ in result.created], ["ani", "bu-guru"])
        self.assertIsNone(result.created[0][1])
        generated = result.created[1][1]
        self.assertGreaterEqual(len(generated), 8)
        self.assertTrue(self.store.login("bu-guru", generated))
        self.assertTrue(self.store.login("ani", "password123"))
        self.assertEqual(self.store.get_user("ani")["display_name"], "Ani Wijaya")

    def test_bad_rows_reported_others_kept(self):
        csv_text = ("username,display_name,role,password\n"
                    "ok-1,Ok,siswa,password123\n"
                    "../x,Jahat,siswa,password123\n"
                    "ok-1,Dobel,siswa,password123\n"
                    "ok-2,Role,kepala,password123\n"
                    "ok-3,Pendek,siswa,abc\n"
                    "ok-4,Baik,,password123\n")
        result = self.store.import_csv(io.StringIO(csv_text))
        self.assertEqual([u for u, _ in result.created], ["ok-1", "ok-4"])
        self.assertEqual([line for line, _ in result.errors], [3, 4, 5, 6])
        self.assertEqual(self.store.get_user("ok-4")["role"], "siswa")

    def test_missing_header(self):
        with self.assertRaises(AccountError):
            self.store.import_csv(io.StringIO("nama,kelas\nani,x\n"))

    def test_from_path_with_bom(self):
        path = Path(self.tmp.name) / "u.csv"
        path.write_bytes("﻿username,display_name,role,password\nani,Ani,siswa,password123\n".encode())
        self.assertEqual(len(self.store.import_csv(path).created), 1)
        with self.assertRaises(AccountError):
            self.store.import_csv(Path(self.tmp.name) / "tidak-ada.csv")


class TestPersistence(Base):
    def test_reopen_and_env_path(self):
        self.store.create_user("ani", "password1")
        os.environ["LAB_DB"] = str(self.db)
        self.addCleanup(os.environ.pop, "LAB_DB", None)
        again = AccountStore()
        self.assertEqual(again.get_user("ani")["username"], "ani")
        with again._connect() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], accounts.SCHEMA_VERSION)


class TestCLI(Base):
    def run_cli(self, *args, stdin=None):
        env = {**os.environ, "LAB_DB": str(self.db)}
        return subprocess.run([sys.executable, str(CLI), *args], input=stdin, env=env,
                              capture_output=True, text=True)

    def test_create_list_role_deactivate(self):
        r = self.run_cli("create-user", "boss", "--role", "admin", "--password-stdin", stdin="password1\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_cli("create-user", "ani", "--name", "Ani", "--password-stdin", stdin="password1\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Setiap langkah terlihat: akun, role, nama, dan database yang ditulis.
        self.assertIn('Akun dibuat: ani (siswa, nama "Ani")', r.stdout)
        self.assertIn(f"Database : {self.db}", r.stdout)
        out = self.run_cli("list").stdout
        self.assertIn("boss", out)
        self.assertIn("2 akun", out)
        self.assertEqual(self.run_cli("set-role", "ani", "guru").returncode, 0)
        self.assertEqual(self.run_cli("deactivate", "ani").returncode, 0)
        self.assertFalse(AccountStore(self.db).get_user("ani")["active"])
        self.assertEqual(self.run_cli("activate", "ani").returncode, 0)
        r = self.run_cli("reset-password", "ani", "--password-stdin", stdin="baru-12345\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(AccountStore(self.db).login("ani", "baru-12345"))

    def test_errors_exit_nonzero(self):
        r = self.run_cli("create-user", "Bad", "--password-stdin", stdin="password1\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Username", r.stderr)
        r = self.run_cli("create-user", "ani", "--password-stdin", stdin="pendek\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotEqual(self.run_cli("deactivate", "hantu").returncode, 0)

    def test_import_csv(self):
        path = Path(self.tmp.name) / "u.csv"
        path.write_text("username,display_name,role,password\nani,Ani,siswa,\n../x,J,siswa,\n")
        r = self.run_cli("import-csv", str(path))
        self.assertEqual(r.returncode, 1)
        self.assertIn("1 akun dibuat, 1 baris gagal", r.stdout)
        self.assertIn("password:", r.stdout)
        self.assertIn("baris 3", r.stderr)


class TestDisplayNameAndLastSeen(Base):
    def test_set_display_name(self):
        self.store.create_user("ani", "password1", "siswa", "Ani")
        self.assertEqual(self.store.set_display_name("ani", "  Ani Baru ")["display_name"], "Ani Baru")
        self.assertEqual(self.store.get_user("ani")["display_name"], "Ani Baru")
        for bad in ("", "   ", "x" * 101, None):
            with self.assertRaises(AccountError):
                self.store.set_display_name("ani", bad)
        with self.assertRaises(AccountError):
            self.store.set_display_name("hantu", "X")

    def test_last_seen_map(self):
        self.store.create_user("ani", "password1")
        self.store.create_user("budi", "password1")
        self.assertEqual(self.store.last_seen_map(), {})
        self.store.login("ani", "password1")
        self.clock.t += 50
        token = self.store.login("ani", "password1")
        self.clock.t += 10
        self.store.user_for_token(token)
        self.assertEqual(self.store.last_seen_map(), {"ani": self.clock.t})
        self.clock.t += self.store.session_ttl + 1   # semua sesi kedaluwarsa
        self.assertEqual(self.store.last_seen_map(), {})


if __name__ == "__main__":
    unittest.main()
