"""Alamat Winbox di state sesi (server.gui_access): port publish mode Server vs IP internal."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ros  # noqa: E402
import server  # noqa: E402
from instance import InstanceError  # noqa: E402


def fake_lab(ports=None, error=None):
    def winbox_ports():
        if error:
            raise error
        return ports or {}
    inst = SimpleNamespace(winbox_ports=winbox_ports, clab_name="net002-alice")
    return SimpleNamespace(kinds={"r1": ros.ROS_KIND, "r2": ros.ROS_KIND, "host-a": "linux"}, instance=inst)


class TestGuiAccess(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(server, "_cached_ip", lambda lab, node: f"172.20.3.{node[-1]}")
        patcher.start()
        self.addCleanup(patcher.stop)

    def mode(self, is_server):
        patcher = mock.patch.object(server, "settings", lambda: SimpleNamespace(is_server=is_server))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_server_published_ports_use_browser_host(self):
        self.mode(True)
        rows = server.gui_access(fake_lab({"r1": 28024, "r2": 28025}), ["r1", "r2", "host-a"], "plab.sekolah")
        self.assertEqual([(r["node"], r["host"], r["port"], r.get("published")) for r in rows],
                         [("r1", "plab.sekolah", 28024, True), ("r2", "plab.sekolah", 28025, True)])

    def test_server_without_winbox_ports_falls_back_to_internal_ip(self):
        self.mode(True)
        rows = server.gui_access(fake_lab({}), ["r1"], "plab.sekolah")
        self.assertEqual((rows[0]["host"], rows[0]["port"], rows[0].get("published")), ("172.20.3.1", 8291, None))

    def test_pribadi_never_publishes(self):
        self.mode(False)
        rows = server.gui_access(fake_lab({"r1": 28024}), ["r1"], "localhost")
        self.assertEqual((rows[0]["host"], rows[0]["port"]), ("172.20.3.1", 8291))

    def test_port_error_does_not_break_state(self):
        self.mode(True)
        rows = server.gui_access(fake_lab(error=InstanceError("lebih dari 8 router")), ["r1"], "plab.sekolah")
        self.assertEqual(rows[0]["port"], 8291)


if __name__ == "__main__":
    unittest.main()
