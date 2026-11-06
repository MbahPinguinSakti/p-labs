"""Test perekaman perubahan RouterOS dari luar terminal (guiwatch.py) tanpa router.

Yang diuji: terjemahan selisih `/export terse` menjadi command, kecocokannya
dengan aturan NOS routeros dan checkpoint net-002, deteksi command tulis dari
terminal, serta pembebasan process gate kalau fix dibuat lewat GUI.
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

PLATFORM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM))

import guiwatch  # noqa: E402
import scoring  # noqa: E402
from transcript import NosRules  # noqa: E402

# Potongan `/export terse` r2 net-002 (RouterOS 7).
BASE = """\
# 2026-11-06 08:24:55 by RouterOS 7.20.4
# software id =
/interface ethernet set [ find default-name=ether1 ] disable-running-check=no
/ip address add address=172.31.255.30/30 interface=ether1 network=172.31.255.28
/ip address add address=10.0.12.2/30 comment="link r1-r2" interface=ether2 network=10.0.12.0
/ip address add address=10.20.0.1/25 comment=LAN-B interface=ether3 network=10.20.0.0
/ip route add comment="LAN-A lewat r1" disabled=no distance=1 dst-address=10.10.0.0/24 gateway=10.0.12.1
/system identity set name=r2
"""


def lines(text):
    return guiwatch.parse_export(text)


def diff(old, new):
    return guiwatch.diff_commands(lines(old), lines(new))


class TestDiff(unittest.TestCase):
    def test_no_change(self):
        self.assertEqual(diff(BASE, BASE), [])

    def test_edit_address(self):
        fixed = BASE.replace("10.20.0.1/25", "10.20.0.1/24")
        self.assertEqual(diff(BASE, fixed), ["/ip address set [find interface=ether3] address=10.20.0.1/24"])

    def test_add_and_remove(self):
        added = BASE + '/ip route add dst-address=10.20.0.128/25 gateway=ether3\n'
        self.assertEqual(diff(BASE, added), ["/ip route add dst-address=10.20.0.128/25 gateway=ether3"])
        self.assertEqual(diff(added, BASE), ["/ip route remove [find dst-address=10.20.0.128/25]"])

    def test_quoted_values_stay_intact(self):
        renamed = BASE.replace('comment="LAN-A lewat r1"', 'comment="LAN-A via r1"')
        self.assertEqual(diff(BASE, renamed), ['/ip route set [find dst-address=10.10.0.0/24] comment="LAN-A via r1"'])

    def test_interface_set_uses_name(self):
        mtu = BASE + "/interface ethernet set [ find default-name=ether3 ] mtu=1400\n"
        self.assertEqual(diff(BASE, mtu), ["/interface ethernet set ether3 mtu=1400"])
        self.assertEqual(diff(mtu, BASE), ["/interface ethernet set ether3 mtu=(default)"])

    def test_singleton_set(self):
        self.assertEqual(diff(BASE, BASE.replace("name=r2", "name=core")), ["/system identity set name=core"])

    def test_disable_entry(self):
        off = BASE.replace("comment=LAN-B interface=ether3", "comment=LAN-B disabled=yes interface=ether3")
        self.assertEqual(diff(BASE, off), ["/ip address set [find interface=ether3] disabled=yes"])


class TestFitsScoring(unittest.TestCase):
    """Command hasil terjemahan harus dikenali aturan yang sama dengan command terminal."""

    rules = NosRules("routeros", PLATFORM)

    def test_nos_keys(self):
        fixed = diff(BASE, BASE.replace("10.20.0.1/25", "10.20.0.1/24"))[0]
        self.assertEqual(self.rules.changes(fixed), ["ip address ether3"])
        route = diff(BASE, BASE + "/ip route add dst-address=10.20.0.128/25 gateway=ether3\n")[0]
        self.assertEqual(self.rules.changes(route), ["route"])
        mtu = diff(BASE, BASE + "/interface ethernet set [ find default-name=ether3 ] mtu=1400\n")[0]
        self.assertEqual(self.rules.changes(mtu), ["interface ether3"])

    def test_net002_safety_rule(self):
        import re
        import yaml
        problem = yaml.safe_load((PLATFORM.parent / "labs" / "net-002" / "problem.yaml").read_text())
        rule = next(r for r in problem["scoring"]["safety"] if r["id"] == "route_patch")
        route = diff(BASE, BASE + "/ip route add dst-address=10.20.0.128/25 gateway=ether3\n")[0]
        self.assertTrue(any(re.search(rule["key"], k) for k in self.rules.changes(route)))


class TestTerminalWrote(unittest.TestCase):
    def watcher(self, events):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "r2.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        lab = SimpleNamespace(events_dir=tmp, session="s1", dir=tmp)
        return guiwatch.RouterWatch(lab, "r2")

    def test_detects_recent_write(self):
        now = time.time()
        w = self.watcher([{"ts": now, "session": "s1", "type": "command",
                           "data": "/ip address set [find interface=ether3] address=10.20.0.1/24"}])
        self.assertTrue(w.terminal_wrote(now - 5))

    def test_ignores_reads_old_and_gui_events(self):
        now = time.time()
        w = self.watcher([
            {"ts": now - 60, "session": "s1", "type": "command", "data": "/ip address set numbers=0 disabled=no"},
            {"ts": now, "session": "s1", "type": "command", "data": "/ip address print"},
            {"ts": now, "session": "s1", "type": "command", "data": "/ip route add dst-address=1.1.1.1", "source": "winbox"},
            {"ts": now, "session": "lama", "type": "command", "data": "/ip route add dst-address=1.1.1.1"},
        ])
        self.assertFalse(w.terminal_wrote(now - 5))

    def test_login_baseline_then_gui_login(self):
        w = self.watcher([])
        old = "2026-11-06 08:26:41 system,info,account user admin logged in from 172.31.255.29 via winbox"
        w.check_logins(old)
        self.assertIsNone(w.via)   # login sebelum watcher jalan diabaikan
        ssh = "2026-11-06 08:27:00 system,info,account user admin logged in from 172.31.255.29 via ssh"
        w.check_logins(old + "\n" + ssh)
        self.assertIsNone(w.via)   # ssh = ros.py/state_check
        new = "2026-11-06 08:28:00 system,info,account user admin logged in from 172.31.255.29 via winbox"
        w.check_logins(old + "\n" + ssh + "\n" + new)
        self.assertEqual(w.via, "winbox")
        event = json.loads((w.events_file).read_text().splitlines()[-1])
        self.assertEqual((event["type"], event["via"], event["session"]), ("gui_login", "winbox", "s1"))


class TestGateWaiver(unittest.TestCase):
    def test_waive_keeps_missing(self):
        gate = scoring.process_gate([{"id": "diagnose", "hit": False, "ts": None},
                                     {"id": "apply_fix", "hit": True, "ts": 5}],
                                    {"requires": ["diagnose"], "before": "apply_fix"})
        waived = scoring.waive_gate(gate, "fix lewat winbox")
        self.assertEqual((gate["factor"], waived["factor"]), (0.0, 1.0))
        self.assertEqual(waived["missing"], ["diagnose"])
        self.assertEqual(waived["waived"], "fix lewat winbox")


class TestEvaluateGuiSession(unittest.TestCase):
    """Sesi net-002 sintetis (format golden) dinilai tanpa LLM."""

    def session(self, fix_source, diagnose=False):
        import shutil
        import evaluate
        lab = Path(tempfile.mkdtemp()) / "net-002"
        src = PLATFORM.parent / "labs" / "net-002"
        lab.mkdir()
        for name in ("problem.yaml", "topo-2router.clab.yaml", "brief.md"):
            shutil.copy(src / name, lab / name)
        state = lab / "golden" / "s1"
        (state / "events").mkdir(parents=True)
        (state / "session_id").write_text("s1\n")
        (state / "ground_truth.json").write_text(json.dumps({"problem": "net-002", "router": "r2", "port": "ether3", "prefix": 25}))
        (state / "verify.json").write_text(json.dumps({"correctness": 100, "issues": [], "ping_ok": True}))
        fix = {"ts": 20.0, "session": "s1", "node": "r2", "type": "command", "exit": 0,
               "data": "/ip address set [find interface=ether3] address=10.20.0.1/24"}
        if fix_source:
            fix["source"] = fix_source
        events = [{"ts": 10.0, "session": "s1", "node": "r2", "type": "gui_login", "via": "winbox"}, fix]
        if diagnose:
            events.insert(0, {"ts": 5.0, "session": "s1", "node": "r2", "type": "command", "exit": 0, "data": "/ip address print"})
        (state / "events" / "r2.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        (state / "checkpoints.jsonl").write_text(json.dumps(
            {"session": "s1", "id": "apply_fix", "type": "state_check", "ts": 20.0, "node": "r2", "evidence": "x"}) + "\n")
        session = evaluate.Session(state, live_verify=False)
        return session, evaluate.deterministic_scores(session)

    def test_fix_via_winbox_waives_gate(self):
        session, rb = self.session("winbox")
        self.assertEqual(rb["gui"]["via"], ["winbox"])
        self.assertEqual(rb["gui"]["fix_event"], "E1")
        self.assertEqual(rb["process_gate"]["factor"], 1.0)
        self.assertIn("winbox", rb["process_gate"]["waived"])
        self.assertEqual(session.timeline[0]["state_change"], ["ip address ether3"])

    def test_fix_from_terminal_keeps_gate(self):
        # Login Winbox saja tidak membebaskan gate kalau fix-nya diketik di terminal.
        _, rb = self.session(None)
        self.assertTrue(rb["gui"]["used"])
        self.assertIsNone(rb["gui"]["fix_event"])
        self.assertLess(rb["process_gate"]["factor"], 1.0)
        self.assertNotIn("waived", rb["process_gate"])

    def test_prompt_mentions_gui(self):
        import evaluate
        session, rb = self.session("winbox", diagnose=True)
        prompt = evaluate.build_prompt(session, rb)
        self.assertIn("## Pemain memakai GUI (winbox)", prompt)
        self.assertIn("r2 [WINBOX] exit=0 $ /ip address set", prompt)


if __name__ == "__main__":
    unittest.main()
