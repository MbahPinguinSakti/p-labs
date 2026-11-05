"""Test penilaian deterministik. Jalankan: python3 -m unittest discover -s platform/tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scoring  # noqa: E402

GATE = {"requires": ["diagnose", "locate_fault"], "before": "apply_fix"}
WEIGHTS = {"correctness": 0.3, "efficiency": 0.2, "methodology": 0.4, "safety": 0.1}


def cps(diagnose=None, locate=None, fix=None):
    """Checkpoint dengan ts (None = tidak tercapai)."""
    return [{"id": i, "hit": ts is not None, "ts": ts}
            for i, ts in (("diagnose", diagnose), ("locate_fault", locate), ("apply_fix", fix))]


class TestProcessGate(unittest.TestCase):
    def test_full_process_before_fix(self):
        self.assertEqual(scoring.process_gate(cps(1, 2, 3), GATE)["factor"], 1.0)

    def test_no_process(self):
        gate = scoring.process_gate(cps(fix=3), GATE)
        self.assertEqual(gate["factor"], 0.0)
        self.assertEqual(gate["missing"], ["diagnose", "locate_fault"])

    def test_diagnosis_after_fix_does_not_count(self):
        self.assertEqual(scoring.process_gate(cps(5, 6, 3), GATE)["factor"], 0.0)

    def test_partial(self):
        self.assertEqual(scoring.process_gate(cps(1, None, 3), GATE)["factor"], 0.5)

    def test_no_fix_yet_counts_all_hits(self):
        self.assertEqual(scoring.process_gate(cps(1, 2, None), GATE)["factor"], 1.0)

    def test_disabled(self):
        gate = scoring.process_gate(cps(fix=3), None)
        self.assertEqual(gate["factor"], 1.0)
        self.assertEqual(scoring.credited({"correctness": 100}, gate), {"correctness": 100})

    def test_ranking_expert_trial_cheat(self):
        """Urutan yang diinginkan: expert > jujur-tapi-berantakan > nyontek."""
        def final(checkpoints, dims):
            gate = scoring.process_gate(checkpoints, GATE)
            return scoring.final_score(scoring.credited(dims, gate), WEIGHTS, 0)
        expert = final(cps(1, 2, 3), {"correctness": 100, "efficiency": 100, "methodology": 90, "safety": 100})
        trial = final(cps(1, 2, 3), {"correctness": 50, "efficiency": 0, "methodology": 42, "safety": 50})
        cheat = final(cps(fix=3), {"correctness": 100, "efficiency": 100, "methodology": 10, "safety": 100})
        self.assertGreater(expert, trial)
        self.assertGreater(trial, cheat)


if __name__ == "__main__":
    unittest.main()
