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

    def topo(self, fn):
        path = next(self.lab.glob("*.clab.yaml"))
        topo = yaml.safe_load(path.read_text())
        fn(topo)
        path.write_text(yaml.safe_dump(topo, sort_keys=False))
        return lablint.lint(self.lab).errors

    def test_topology_name_without_dash(self):
        errors = self.topo(lambda t: t.update(name="net-099"))
        self.assertTrue(any("tanpa '-'" in e for e in errors), errors)

    def test_topology_name_unique(self):
        shutil.copytree(LABS / "net-001", self.tmp / "net-001")
        name = yaml.safe_load((LABS / "net-001" / "topo-3switch-2host.clab.yaml").read_text())["name"]
        errors = self.topo(lambda t: t.update(name=name))
        self.assertTrue(any("sudah dipakai net-001" in e for e in errors), errors)

    def test_instance_clashing_settings(self):
        def clash(t):
            t["mgmt"] = {"ipv4-subnet": "10.99.0.0/24"}
            node = next(iter(t["topology"]["nodes"]))
            t["topology"]["nodes"][node]["ports"] = ["8080:80"]
        errors = self.topo(clash)
        self.assertTrue(any("'mgmt'" in e for e in errors), errors)
        self.assertTrue(any("'ports'" in e for e in errors), errors)

    def test_clashing_settings_in_groups(self):
        def clash(t):
            t["topology"]["groups"] = {"edge": {"mgmt-ipv4": "172.20.20.50"}}
            node = next(iter(t["topology"]["nodes"]))
            t["topology"]["nodes"][node]["group"] = "edge"
        errors = self.topo(clash)
        self.assertTrue(any("'mgmt-ipv4'" in e for e in errors), errors)

    def test_resources(self):
        self.assertFalse(self.edit(lambda p: p.update(resources={"mem_mb": 500})).errors)
        for bad in ({"mem_mb": 0}, {"mem_mb": "1G"}, {"cpu": 2}, "500"):
            errors = self.edit(lambda p: p.update(resources=bad)).errors
            self.assertTrue(any("resources" in e for e in errors), (bad, errors))

    def test_script_contract(self):
        inject = self.lab / "inject.sh"
        text = inject.read_text()
        inject.write_text(text.replace('"$(ctr ', '"clab-net099-').replace("$LAB_STATE_DIR", ".state"))
        errors = lablint.script_contract_errors(self.lab, yaml.safe_load((self.lab / "problem.yaml").read_text()))
        self.assertTrue(any("clab-" in e for e in errors), errors)
        # Menyebut labenv.sh di komentar saja tidak cukup.
        inject.write_text("#!/usr/bin/env bash\n# source platform/labenv.sh\necho hi\n")
        errors = lablint.script_contract_errors(self.lab, yaml.safe_load((self.lab / "problem.yaml").read_text()))
        self.assertTrue(any("tidak men-source" in e for e in errors), errors)

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
