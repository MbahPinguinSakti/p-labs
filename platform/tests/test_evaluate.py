"""Test validasi output LLM di evaluate.py. Jalankan: python3 -m unittest discover -s platform/tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluate import clean_evidence  # noqa: E402

KNOWN = {"E1", "E2", "E3", "E10", "E11"}


class TestCleanEvidence(unittest.TestCase):
    def test_known_kept(self):
        kept, dropped = clean_evidence([{"event": "E1", "note": "x"}], "m", KNOWN)
        self.assertEqual(kept, [{"event": "E1", "note": "x"}])
        self.assertEqual(dropped, [])

    def test_unknown_dropped(self):
        kept, dropped = clean_evidence([{"event": "E99", "note": "x"}], "m", KNOWN)
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 1)

    def test_range_expanded(self):
        # Model kadang menulis rentang; hasil nyata dari Sonnet di golden expert.
        kept, dropped = clean_evidence([{"event": "E2-E3", "note": "a"},
                                        {"event": "E10–E11", "note": "b"}], "m", KNOWN)
        self.assertEqual([e["event"] for e in kept], ["E2", "E3", "E10", "E11"])
        self.assertEqual(dropped, [])

    def test_range_with_unknown_dropped(self):
        kept, dropped = clean_evidence([{"event": "E3-E9", "note": "c"}], "m", KNOWN)
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 1)

    def test_whitespace_trimmed(self):
        kept, _ = clean_evidence([{"event": " E1 ", "note": "d"}], "m", KNOWN)
        self.assertEqual(kept[0]["event"], "E1")


if __name__ == "__main__":
    unittest.main()
