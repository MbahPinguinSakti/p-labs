"""Test dukungan MikroTik RouterOS tanpa router sungguhan.

Yang diuji: normalisasi command CLI (konteks menu), deteksi error, aturan NOS
routeros (termasuk include linux-bridge), nama interface, format event shell,
dan kedua lab RouterOS (lint, checkpoint, topologi di web).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
LABS = PLATFORM.parent / "labs"
sys.path.insert(0, str(PLATFORM))

import lablint  # noqa: E402
import ros  # noqa: E402
from checkpoints import Lab  # noqa: E402
from transcript import NosRules  # noqa: E402

ROS_LABS = ["net-002", "net-003"]


class TestResolve(unittest.TestCase):
    def check(self, context, line, expected_context, expected_command):
        self.assertEqual(ros.resolve(context, line), (expected_context, expected_command))

    def test_absolute(self):
        self.check([], "/ip address print", [], "/ip address print")
        self.check(["routing"], "/ip route print detail", ["routing"], "/ip route print detail")

    def test_menu_navigation(self):
        self.check([], "/ip address", ["ip", "address"], None)
        self.check(["ip", "address"], "..", ["ip"], None)
        self.check(["ip"], "/", [], None)
        self.check(["routing"], "ospf neighbor", ["routing", "ospf", "neighbor"], None)

    def test_relative_command(self):
        self.check(["ip", "address"], "print", ["ip", "address"], "/ip address print")
        self.check(["routing", "ospf"], "neighbor print", ["routing", "ospf"], "/routing ospf neighbor print")
        self.check(["ip", "address"], "set [find interface=ether3] address=10.20.0.1/24",
                   ["ip", "address"], "/ip address set [find interface=ether3] address=10.20.0.1/24")

    def test_interactive_commands_are_bounded(self):
        self.check([], "/ping 10.0.0.1", [], "/ping 10.0.0.1 count=4")
        self.check([], "ping 10.0.0.1 count=2", [], "/ping 10.0.0.1 count=2")
        self.check(["interface"], "monitor-traffic ether2", ["interface"], "/interface monitor-traffic ether2 once")

    def test_scripting_passthrough(self):
        line = ":put [/ip address get [find interface=ether3] address]"
        self.check(["ip"], line, ["ip"], line)


class TestErrors(unittest.TestCase):
    def test_failed(self):
        self.assertTrue(ros.failed("syntax error (line 1 column 5)"))
        self.assertTrue(ros.failed("bad command name pritn (line 1 column 13)"))
        self.assertTrue(ros.failed("failure: already have such address"))
        self.assertTrue(ros.failed("expected end of command (line 1 column 18)"))
        self.assertFalse(ros.failed("Flags: D - DYNAMIC\n 0   10.10.0.1/24  10.10.0.0  ether2"))


class TestNos(unittest.TestCase):
    rules = NosRules("routeros", PLATFORM)

    def test_routeros_changes(self):
        cases = {
            "/ip address set [find interface=ether3] address=10.20.0.1/24": ["ip address ether3"],
            "/ip address remove 2": ["ip address"],
            "/ip route add dst-address=10.20.0.130/32 gateway=ether3": ["route"],
            "/interface ethernet set ether3 mtu=1500": ["interface ether3"],
            "/interface disable ether3": ["interface ether3"],
            "/routing ospf interface-template disable 0": ["ospf interface-template"],
        }
        for command, keys in cases.items():
            self.assertEqual(self.rules.changes(command), keys, command)

    def test_reads_are_not_changes(self):
        for command in ["/ip address print", "/routing ospf neighbor print", "/interface print",
                        "/ping 10.0.0.1 count=4", ":put [/interface get ether3 mtu]"]:
            self.assertEqual(self.rules.changes(command), [], command)

    def test_includes_linux_rules(self):
        self.assertEqual(self.rules.changes("ip addr add 10.20.0.100/24 dev eth1"), ["addr eth1"])


class TestLabs(unittest.TestCase):
    def test_lint_clean(self):
        for lab_id in ROS_LABS:
            self.assertEqual(lablint.lint(LABS / lab_id).errors, [], lab_id)

    def test_node_kinds(self):
        lab = Lab(LABS / "net-003")
        self.assertEqual(lab.kinds["r2"], ros.ROS_KIND)
        self.assertEqual(lab.kinds["host-a"], "linux")
        self.assertTrue(ros.is_ros(LABS / "net-003", "r3"))

    def test_interface_names(self):
        self.assertEqual(ros.display_interface(ros.ROS_KIND, "eth1"), "ether2")
        self.assertEqual(ros.display_interface("linux", "eth1"), "eth1")

    def test_web_topology_uses_routeros_names(self):
        import os
        os.environ.setdefault("LAB_LABS_DIR", str(LABS))
        import server
        topo = server.topology(LABS / "net-002", {"lab_topology": "topo-2router.clab.yaml",
                                                  "design": {"links": {}}})
        link = next(l for l in topo["links"] if l["a"] == "r1" and l["b"] == "r2")
        self.assertEqual((link["a_if"], link["b_if"]), ("ether3", "ether2"))
        roles = {n["id"]: n["role"] for n in topo["nodes"]}
        self.assertEqual(roles["r1"], "router")

    def test_checkpoint_patterns(self):
        """Command RouterOS yang tercatat (bentuk lengkap) cocok dengan checkpoint yang dimaksud."""
        import re
        for lab_id, diagnose, not_diagnose in [
            ("net-002", ["/ip address print", "/ip route print", "ip route"], ["ip route add default via 10.0.0.1"]),
            ("net-003", ["/routing ospf neighbor print", "/ip route print"], ["/routing ospf instance set 0"]),
        ]:
            lab = Lab(LABS / lab_id)
            pattern = next(cp for cp in lab.checkpoints if cp["id"] == "diagnose")["pattern"]
            for command in diagnose:
                self.assertTrue(re.search(pattern, command), (lab_id, command))
            for command in not_diagnose:
                self.assertFalse(re.search(pattern, command), (lab_id, command))


class TestShellEvent(unittest.TestCase):
    def test_event_format_matches_lab_rc(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / "events").mkdir()
            ros.log_event(state, "20261106-120000", "r2", "/ip address print", 0, "0 10.20.0.1/25 ether3\n")
            event = json.loads((state / "events" / "r2.jsonl").read_text())
            self.assertEqual({k: event[k] for k in ("session", "node", "type", "data", "exit")},
                             {"session": "20261106-120000", "node": "r2", "type": "command",
                              "data": "/ip address print", "exit": 0})
            self.assertEqual(event["output"], "0 10.20.0.1/25 ether3")


if __name__ == "__main__":
    unittest.main()
