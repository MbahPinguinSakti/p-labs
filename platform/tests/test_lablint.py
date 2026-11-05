"""Test lablint (validator lab) dan newlab (scaffold dari template)."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PLATFORM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM))

import lablint  # noqa: E402
import newlab  # noqa: E402

LABS = PLATFORM.parent / "labs"


class TestLint(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="plab-lint-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.lab = newlab.create("net-099", 'Lab "uji"', self.tmp)

    def edit(self, fn):
        path = self.lab / "problem.yaml"
        problem = yaml.safe_load(path.read_text())
        fn(problem)
        path.write_text(yaml.safe_dump(problem, sort_keys=False))
        return lablint.lint(self.lab)

    def test_existing_lab_is_clean(self):
        self.assertEqual(lablint.lint(LABS / "net-001").errors, [])

    def test_scaffold_is_clean_and_filled(self):
        report = lablint.lint(self.lab)
        self.assertEqual(report.errors, [])
        for path in self.lab.rglob("*"):
            if path.is_file():
                self.assertNotIn("__ID__", path.read_text(), path)
        topo = yaml.safe_load((self.lab / "topology.clab.yaml").read_text())
        self.assertEqual(topo["name"], "net099")
        self.assertIn("{{.State.Running}}", (self.lab / "verify.sh").read_text())  # format docker tetap

    def test_duplicate_id_refused(self):
        with self.assertRaises(ValueError):
            newlab.create("net-099", "lagi", self.tmp)

    def test_undefined_parameter(self):
        report = self.edit(lambda p: p["hints"].append({"level": 3, "penalty": 1, "text": "cek {{vlan}}"}))
        self.assertTrue(any("{{vlan}}" in e for e in report.errors))

    def test_bad_regex_and_weights(self):
        def broken(p):
            p["checkpoints"][0]["pattern"] = "^(bridge"
            p["scoring"]["weights"]["safety"] = 0.5
        errors = " | ".join(self.edit(broken).errors)
        self.assertIn("regex tidak valid", errors)
        self.assertIn("berjumlah", errors)

    def test_unknown_node_and_link(self):
        def broken(p):
            p["checkpoints"][3]["any_of"][0]["node"] = "host-z"
            p["design"]["links"]["host-a:eth9 sw1:eth1"] = "x"
        errors = " | ".join(self.edit(broken).errors)
        self.assertIn("host-z", errors)
        self.assertIn("design.links", errors)

    def test_missing_recording_bind(self):
        path = self.lab / "topology.clab.yaml"
        path.write_text(path.read_text().replace("      - .state/events:/var/log/lab\n", ""))
        self.assertTrue(any("events" in e for e in lablint.lint(self.lab).errors))


if __name__ == "__main__":
    unittest.main()
