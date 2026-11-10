"""platform/version.py: nomor VERSION + commit dibaca langsung dari .git."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import version  # noqa: E402

SHA = "f75e43c0123456789abcdef0123456789abcdef0"


class Repo(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git = self.root / ".git"
        self.git.mkdir()

    def test_loose_branch_ref(self):
        (self.git / "HEAD").write_text("ref: refs/heads/feat/mode-server\n")
        (self.git / "refs/heads/feat").mkdir(parents=True)
        (self.git / "refs/heads/feat/mode-server").write_text(SHA + "\n")
        self.assertEqual(version.git_info(self.root), ("f75e43c", "feat/mode-server"))

    def test_packed_ref(self):
        (self.git / "HEAD").write_text("ref: refs/heads/main\n")
        (self.git / "packed-refs").write_text(f"# pack-refs with: peeled\n{SHA} refs/heads/main\n")
        self.assertEqual(version.git_info(self.root), ("f75e43c", "main"))

    def test_detached_head(self):
        (self.git / "HEAD").write_text(SHA + "\n")
        self.assertEqual(version.git_info(self.root), ("f75e43c", None))

    def test_no_git(self):
        self.git.rmdir()
        self.assertEqual(version.git_info(self.root), (None, None))

    def test_dirty_unknown_when_git_fails(self):
        with mock.patch("subprocess.run", side_effect=OSError("git tidak ada")):
            self.assertIsNone(version.git_dirty(self.root))

    def test_number(self):
        self.assertEqual(version.number(self.root), "0.0.0")
        (self.root / "VERSION").write_text("0.3.0\n")
        self.assertEqual(version.number(self.root), "0.3.0")


class TestDescribe(unittest.TestCase):
    def test_full(self):
        data = {"version": "0.3.0", "commit": "f75e43c", "branch": "main", "dirty": True}
        self.assertEqual(version.describe(data), "0.3.0 (f75e43c, main, ada perubahan lokal)")

    def test_bare(self):
        data = {"version": "0.3.0", "commit": None, "branch": None, "dirty": None}
        self.assertEqual(version.describe(data), "0.3.0")

    def test_this_repo_has_version(self):
        self.assertRegex(version.info()["version"], r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
