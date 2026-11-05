"""Regression test: bagian deterministik semua golden transcript harus lolos.

Tidak memanggil LLM dan tidak menulis apa pun ke direktori golden. Golden
ditemukan otomatis di labs/*/golden/*/expected.yaml, jadi golden baru langsung
ikut diuji. Jalankan: python3 -m unittest discover -s platform/tests
"""

import sys
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM))

from evaluate import golden_checks  # noqa: E402

GOLDENS = sorted(p.parent for p in (PLATFORM.parent / "labs").glob("*/golden/*/expected.yaml"))


@unittest.skipUnless(GOLDENS, "tidak ada golden transcript")
class TestGoldenRules(unittest.TestCase):
    def test_all_goldens(self):
        for golden in GOLDENS:
            with self.subTest(golden=f"{golden.parent.parent.name}/{golden.name}"):
                before = {p: p.stat().st_mtime for p in golden.iterdir() if p.is_file()}
                _, _, checks = golden_checks(golden, rules_only=True)
                failed = [message for passed, message in checks if passed is False]
                self.assertEqual(failed, [])
                after = {p: p.stat().st_mtime for p in golden.iterdir() if p.is_file()}
                self.assertEqual(before, after, "mode rules-only tidak boleh menulis ke golden")


if __name__ == "__main__":
    unittest.main()
