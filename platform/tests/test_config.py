"""Test config.py, templates/server.yaml, dan bagian murni migrate-server.
Tanpa root/systemd/docker. Jalankan: python3 -m unittest discover -s platform/tests"""

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLATFORM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM))

import config  # noqa: E402
from config import ConfigError  # noqa: E402

TEMPLATE = PLATFORM / "templates" / "server.yaml"


def load_migrate():
    loader = importlib.machinery.SourceFileLoader("migrate_server", str(PLATFORM / "migrate-server"))
    spec = importlib.util.spec_from_loader("migrate_server", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, text, name="server.yaml"):
        p = self.dir / name
        p.write_text(text)
        return p


class TestLoad(Tmp):
    def test_default_without_file(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LAB_CONFIG", None)
            with mock.patch.object(config, "DEFAULT_PATH", self.dir / "tidak-ada.yaml"):
                c = config.load()
        self.assertEqual((c.mode, c.host, c.port, c.style), ("pribadi", "127.0.0.1", 8000, "mandiri"))
        self.assertEqual(c.data_dir, config.ROOT / "var")
        self.assertFalse(c.is_server)
        self.assertEqual(c.capacity, config.Capacity(24000, 2, 30))

    def test_valid_server(self):
        p = self.write("mode: server\nlisten: 0.0.0.0:9000\ndata_dir: /srv/plab\nstyle: kelas\n"
                       "capacity: {mem_mb: 8000, max_deploys: 3, idle_minutes: 10}\n")
        c = config.load(p)
        self.assertTrue(c.is_server)
        self.assertEqual((c.host, c.port, c.style), ("0.0.0.0", 9000, "kelas"))
        self.assertEqual(c.data_dir, Path("/srv/plab"))
        self.assertEqual(c.capacity.max_deploys, 3)
        self.assertEqual(c.listen, "0.0.0.0:9000")
        self.assertEqual(c.db_path, Path("/srv/plab/p-lab.db"))

    def test_server_defaults(self):
        c = config.load(self.write("mode: server\n"))
        self.assertEqual((c.host, c.port, c.data_dir), ("0.0.0.0", 8000, Path("/var/lib/p-lab")))

    def test_many_errors_at_once(self):
        p = self.write("mode: kantor\nstyle: x\nlisten: 'abc'\ndata_dir: relatif\n"
                       "capacity: {mem_mb: -1, max_deploys: 0, idle_minutes: true, foo: 1}\nbebas: 1\n")
        with self.assertRaises(ConfigError) as cm:
            config.load(p)
        text = "\n".join(cm.exception.problems)
        for needle in ("mode harus", "style harus", "listen", "mem_mb", "max_deploys",
                       "idle_minutes", "kunci tidak dikenal: 'bebas'", "'foo'"):
            self.assertIn(needle, text)
        self.assertGreaterEqual(len(cm.exception.problems), 7)

    def test_relative_data_dir_rejected_in_server_only(self):
        with self.assertRaises(ConfigError) as cm:
            config.load(self.write("mode: server\ndata_dir: var\n"))
        self.assertIn("absolut", cm.exception.problems[0])
        c = config.load(self.write("mode: pribadi\ndata_dir: var2\n", "b.yaml"))
        self.assertEqual(c.data_dir, config.ROOT / "var2")

    def test_pribadi_rejects_non_local_listen(self):
        with self.assertRaises(ConfigError) as cm:
            config.load(self.write("mode: pribadi\nlisten: 0.0.0.0:8000\n"))
        self.assertIn("lokal", cm.exception.problems[0])
        c = config.load(self.write("mode: pribadi\nlisten: localhost:8123\n", "b.yaml"))
        self.assertEqual((c.host, c.port), ("127.0.0.1", 8123))

    def test_bad_enum(self):
        for text in ("mode: Server\n", "mode: 1\n", "style: kelasx\n"):
            with self.assertRaises(ConfigError):
                config.load(self.write(text))

    def test_broken_listen(self):
        for bad in ("8000", "host:", ":8000", "1.2.3:80", "1.2.3.4:0", "1.2.3.4:70000", "a:b",
                    "::1:8000", "[::1]8000", "[zz]:80", "ho st:80", 8000, ""):
            with self.assertRaises(ValueError, msg=repr(bad)):
                config.parse_listen(bad)
        self.assertEqual(config.parse_listen("[::1]:80"), ("::1", 80))
        self.assertEqual(config.parse_listen("sekolah.lan:8080"), ("sekolah.lan", 8080))

    def test_yaml_problems(self):
        for text in ("mode: [server\n", "- a\n- b\n"):
            with self.assertRaises(ConfigError):
                config.load(self.write(text))
        self.assertEqual(config.load(self.write("")).mode, "pribadi")   # file kosong = default

    def test_env_lab_config(self):
        p = self.write("mode: server\nlisten: 0.0.0.0:7777\n")
        with mock.patch.dict(os.environ, {"LAB_CONFIG": str(p)}):
            self.assertEqual(config.load().port, 7777)
        with mock.patch.dict(os.environ, {"LAB_CONFIG": str(self.dir / "hilang.yaml")}):
            with self.assertRaises(ConfigError) as cm:
                config.load()
            self.assertIn("tidak ada", cm.exception.problems[0])

    def test_allowed_hosts_and_trusted_proxies(self):
        c = config.load(self.write("mode: server\nallowed_hosts: [Plab.Sekolah.Local, 192.168.1.10, '[::1]', "
                                   "plab.sekolah.local]\ntrusted_proxies: [127.0.0.1, 10.0.0.5/24, '::1']\n"))
        self.assertEqual(c.allowed_hosts, ("plab.sekolah.local", "192.168.1.10", "::1"))   # tanpa duplikat
        self.assertEqual([str(n) for n in c.trusted_proxies], ["127.0.0.1/32", "10.0.0.0/24", "::1/128"])
        empty = config.load(self.write("mode: server\nallowed_hosts: []\n", "b.yaml"))
        self.assertEqual((empty.allowed_hosts, empty.trusted_proxies), ((), ()))

    def test_bad_allowed_hosts_and_proxies(self):
        p = self.write("mode: server\nallowed_hosts: ['http://plab.lan', 'plab.lan:8000', 1.2.3, 5]\n"
                       "trusted_proxies: [nginx, 10.0.0.0/33]\n")
        with self.assertRaises(ConfigError) as cm:
            config.load(p)
        problems = cm.exception.problems
        self.assertEqual(sum(p.startswith("allowed_hosts") for p in problems), 4)
        self.assertEqual(sum(p.startswith("trusted_proxies") for p in problems), 2)
        for text in ("mode: server\nallowed_hosts: plab.lan\n", "mode: server\ntrusted_proxies: 127.0.0.1\n"):
            with self.assertRaises(ConfigError) as cm:
                config.load(self.write(text, "c.yaml"))
            self.assertIn("daftar", cm.exception.problems[0])

    def test_pribadi_rejects_server_only_keys(self):
        for key in ("allowed_hosts: [plab.lan]", "trusted_proxies: [127.0.0.1]"):
            with self.assertRaises(ConfigError) as cm:
                config.load(self.write(f"mode: pribadi\n{key}\n"))
            self.assertIn("hanya berlaku di mode server", cm.exception.problems[0])

    def test_template_is_valid(self):
        c = config.load(TEMPLATE)
        self.assertEqual((c.allowed_hosts, c.trusted_proxies), ((), ()))   # contoh dikomentari
        self.assertIn("# allowed_hosts:", TEMPLATE.read_text())
        self.assertIn("# trusted_proxies:", TEMPLATE.read_text())
        self.assertTrue(c.is_server)
        self.assertEqual((c.listen, c.style, c.data_dir), ("0.0.0.0:8000", "mandiri", Path("/var/lib/p-lab")))
        self.assertEqual(c.capacity, config.Capacity(24000, 2, 30))

    def test_import_has_no_side_effects(self):
        out = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import config"
                              % str(PLATFORM)], capture_output=True, text=True, cwd=self.dir)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(list(self.dir.iterdir()), [])


class TestMigrateIzin(Tmp):
    def setUp(self):
        super().setUp()
        self.m = load_migrate()

    def test_db_tidak_terbaca_jadi_warn_bukan_belum_ada_admin(self):
        db = self.dir / "p-lab.db"
        db.write_text("")
        db.chmod(0)
        if os.access(db, os.R_OK):
            self.skipTest("root bisa membaca semuanya")
        cfg = config.from_dict({"mode": "server", "data_dir": str(self.dir)})
        level, text = self.m.check_admin(cfg, "admin")
        self.assertEqual(level, self.m.WARN)
        self.assertIn("sudo", text)

    def test_containerlab_setuid_harus_milik_root(self):
        clab = self.dir / "containerlab"
        clab.write_text("")
        clab.chmod(0o4755)
        if os.geteuid() == 0:
            self.skipTest("file buatan root")
        self.assertEqual(self.m.check_containerlab(str(clab))[0], self.m.FAIL)


class TestMigrate(Tmp):
    def setUp(self):
        super().setUp()
        self.m = load_migrate()
        self.repo = self.dir / "repo"
        for lab, nos in (("net-001", None), ("net-002", "routeros")):
            d = self.repo / "labs" / lab
            (d / "sessions" / "20260101-000000").mkdir(parents=True)
            (d / "sessions" / "20260101-000000" / "a.txt").write_text(lab)
            (d / "problem.yaml").write_text(f"nos: {nos}\n" if nos else "id: x\n")
            (d / "t.clab.yaml").write_text(f"name: {lab.replace('-', '')}\n")
        self.data = self.dir / "data"

    def test_plan_and_copy_sessions(self):
        plan = self.m.plan_session_copy(self.repo, self.data, "admin")
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0][1], self.data / "instances/admin/net-001/sessions/20260101-000000")
        self.assertEqual(self.m.copy_sessions(plan), 2)
        self.assertEqual((plan[1][1] / "a.txt").read_text(), "net-002")
        self.assertTrue(plan[1][0].exists())                       # asli tidak dihapus
        self.assertEqual(self.m.plan_session_copy(self.repo, self.data, "admin"), [])   # idempoten

    def test_ensure_admin_creates_once(self):
        db = self.data / "p-lab.db"
        self.assertEqual(self.m.admin_usernames_ro(db), [])
        self.assertFalse(db.exists())                              # pembacaan tidak membuat DB
        name, pw = self.m.ensure_admin(db, "kepala")
        self.assertEqual(name, "kepala")
        self.assertGreaterEqual(len(pw), 8)
        self.assertEqual(self.m.admin_usernames_ro(db), ["kepala"])
        name2, pw2 = self.m.ensure_admin(db, "lain")
        self.assertEqual((name2, pw2), ("kepala", None))

    def test_routeros_and_names(self):
        self.assertEqual(self.m.routeros_labs(self.repo), ["net-002"])
        self.assertEqual(self.m.lab_clab_names(self.repo), {"net001", "net002"})

    def test_running_containers(self):
        names = ["clab-net001-host-a", "clab-net001-host-a-budi", "clab-lain-x", "web"]
        self.assertEqual(self.m.running_lab_containers(names, {"net001"}),
                         ["clab-net001-host-a", "clab-net001-host-a-budi"])
        self.assertEqual(self.m.check_containers(["clab-net001-a"], {"net001"})[0], "fail")
        self.assertEqual(self.m.check_containers([], {"net001"})[0], "ok")
        self.assertEqual(self.m.check_containers(None, {"net001"})[0], "warn")

    def test_memory_and_kvm(self):
        cfg = config.from_dict({"mode": "server", "capacity": {"mem_mb": 9000}})
        self.assertEqual(self.m.check_memory(cfg, 8000)[0], "fail")
        self.assertEqual(self.m.check_memory(cfg, 9500)[0], "warn")
        self.assertEqual(self.m.check_memory(cfg, 32000)[0], "ok")
        self.assertEqual(self.m.check_kvm(["net-002"], self.dir / "nokvm")[0], "fail")
        self.assertEqual(self.m.check_kvm([], self.dir / "nokvm")[0], "warn")
        self.assertEqual(self.m.check_kvm(["net-002"], self.dir)[0], "ok")

    def test_port(self):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            port = s.getsockname()[1]
            self.assertEqual(self.m.check_port("127.0.0.1", port)[0], "fail")
            self.assertEqual(self.m.check_port("127.0.0.1", port, own_service_active=True)[0], "warn")
        self.assertEqual(self.m.check_port("127.0.0.1", port)[0], "ok")

    def test_run_checks_pribadi_config_fails(self):
        cfg = config.from_dict({})
        res = self.m.run_checks(cfg, repo=self.repo, own_service_active=False, container_names=[])
        self.assertEqual(res[0][0], "fail")

    def test_confirmation(self):
        args = mock.Mock(yes_i_understand=False)
        stdin = mock.Mock(isatty=lambda: True)
        with mock.patch("builtins.input", return_value="server"):
            self.assertTrue(self.m.confirmed(args, stdin))
        with mock.patch("builtins.input", return_value="ya"):
            self.assertFalse(self.m.confirmed(args, stdin))
        self.assertFalse(self.m.confirmed(args, mock.Mock(isatty=lambda: False)))
        self.assertTrue(self.m.confirmed(mock.Mock(yes_i_understand=True), stdin))

    def test_note_mentions_rollback(self):
        cfg = config.from_dict({"mode": "server"}, path=Path("/etc/p-lab/server.yaml"))
        note = self.m.render_note(cfg, "admin", True, 3, repo=self.repo, when="2026-01-01 10:00")
        self.assertIn("--revert-pribadi", note)
        self.assertIn("/var/lib/p-lab", note)

    def test_revert_moves_config_keeps_data(self):
        conf = self.write("mode: server\ndata_dir: %s\n" % self.data)
        self.data.mkdir()
        (self.data / "p-lab.db").write_text("x")
        args = mock.Mock(config=str(conf))
        self.assertEqual(self.m.cmd_revert(args), 0)
        self.assertFalse(conf.exists())
        self.assertEqual(len(list(self.dir.glob("server.yaml.bak-pribadi-*"))), 1)
        self.assertTrue((self.data / "p-lab.db").exists())


if __name__ == "__main__":
    unittest.main()
