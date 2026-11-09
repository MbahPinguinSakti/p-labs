"""Test install-service.sh --system dan p-lab-admin (hak akses mode Server).
Tanpa root/systemd: systemctl diganti skrip palsu. Jalankan: python3 -m unittest discover"""

import importlib.machinery
import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
ROOT = PLATFORM.parent
sys.path.insert(0, str(PLATFORM))

import config  # noqa: E402


def load_admin():
    loader = importlib.machinery.SourceFileLoader("p_lab_admin", str(PLATFORM / "p-lab-admin"))
    spec = importlib.util.spec_from_loader("p_lab_admin", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def write_config(directory, data_dir):
    path = Path(directory) / "server.yaml"
    path.write_text(f"mode: server\nlisten: 127.0.0.1:8123\ndata_dir: {data_dir}\n")
    return path


@unittest.skipUnless((ROOT / ".venv/bin/python").exists(), "butuh .venv")
class InstallServiceSystem(unittest.TestCase):
    def test_hanya_tulis_unit_tanpa_enable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bindir, units = tmp / "bin", tmp / "units"
            bindir.mkdir()
            log = tmp / "systemctl.log"
            fake = bindir / "systemctl"
            fake.write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            conf = write_config(tmp, tmp / "data")
            env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "P_LAB_UNIT_DIR": str(units),
                   "LAB_CONFIG": str(conf)}
            r = subprocess.run([str(PLATFORM / "install-service.sh"), "--system"], env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            unit = (units / "p-lab.service").read_text()
            self.assertIn("--host 127.0.0.1 --port 8123", unit)
            self.assertIn(f'ExecStart="{ROOT}/platform/web"', unit)
            self.assertIn(f'Environment="LAB_CONFIG={conf}"', unit)
            calls = log.read_text() if log.exists() else ""
            self.assertNotIn("enable", calls)
            self.assertNotIn("start", calls)


class AdminServerPrivilege(unittest.TestCase):
    def setUp(self):
        self.admin = load_admin()
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        self.data.mkdir()
        self.cfg = config.load(write_config(self.tmp.name, self.data))

    def tearDown(self):
        self.tmp.cleanup()

    def test_pemilik_lanjut(self):
        self.assertIsNone(self.admin.server_privilege(self.cfg, os.geteuid()))

    def test_root_pindah_ke_pemilik(self):
        if os.geteuid() == 0:
            self.skipTest("data_dir milik root ditolak, bukan dipindah")
        uid, gid, name = self.admin.server_privilege(self.cfg, 0)
        self.assertEqual(uid, os.geteuid())

    def test_user_lain_ditolak_dengan_petunjuk_sudo(self):
        with self.assertRaises(self.admin.Refused) as cm:
            self.admin.server_privilege(self.cfg, os.geteuid() + 12345)
        self.assertIn("sudo platform/p-lab-admin", str(cm.exception))

    def test_data_dir_belum_ada(self):
        cfg = config.load(write_config(self.tmp.name, Path(self.tmp.name) / "tidak-ada"))
        with self.assertRaises(self.admin.Refused):
            self.admin.server_privilege(cfg, os.geteuid())


@unittest.skipUnless((ROOT / ".venv/bin/python").exists(), "butuh .venv")
class AdminCli(unittest.TestCase):
    def run_admin(self, conf, *args):
        env = {**os.environ, "LAB_CONFIG": str(conf)}
        env.pop("LAB_DB", None)
        return subprocess.run([str(PLATFORM / "p-lab-admin"), *args], env=env, capture_output=True, text=True)

    def test_db_tidak_bisa_dibuka_pesan_jelas(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            (data / "p-lab.db").mkdir(parents=True)   # DB berupa folder: sqlite tidak bisa membukanya
            r = self.run_admin(write_config(tmp, data), "list")
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn("Error:", r.stderr)

    @unittest.skipIf(os.geteuid() == 0, "root dijalankan ulang sebagai pemilik, bukan ditolak")
    def test_data_dir_milik_root_ditolak_user_biasa(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.run_admin(write_config(tmp, "/usr"), "list")   # /usr milik root
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn("Traceback", r.stderr)
            self.assertFalse(Path("/usr/p-lab.db").exists())

    def test_normal_jalan(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            r = self.run_admin(write_config(tmp, data), "list")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(stat.S_IMODE((data / "p-lab.db").stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
