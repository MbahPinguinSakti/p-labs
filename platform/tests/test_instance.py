"""Test instance lab per user (instance.py) tanpa containerlab.

Yang diuji: user `local` = layout lama persis, topologi hasil render untuk user
lain (nama lab, path absolut, bind events ke state instance), nama container,
validasi nama user, pemilihan instance lewat LAB_INSTANCE, Lab/sessions/evaluate
yang mengikuti instance, dan labenv.sh (kontrak env script soal).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

PLATFORM = Path(__file__).resolve().parent.parent
LABS = PLATFORM.parent / "labs"
sys.path.insert(0, str(PLATFORM))

import evaluate  # noqa: E402
import instance  # noqa: E402
import sessions  # noqa: E402
from checkpoints import Lab  # noqa: E402
from instance import Instance, InstanceError  # noqa: E402


class InstanceCase(unittest.TestCase):
    """Direktori instance diarahkan ke folder sementara, LAB_INSTANCE dikosongkan."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="plab-instance-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patcher = mock.patch.object(instance, "INSTANCES_DIR", self.tmp / "instances")
        patcher.start()
        self.addCleanup(patcher.stop)
        # Alokasi subnet management tidak bertanya ke docker/ip di test.
        self.used = []
        subnets = mock.patch.object(instance, "used_subnets", lambda: list(self.used))
        subnets.start()
        self.addCleanup(subnets.stop)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("LAB_INSTANCE", None)


class TestLocal(InstanceCase):
    def test_old_layout(self):
        inst = Instance(LABS / "net-001")
        self.assertEqual(inst.user, "local")
        self.assertEqual(inst.state_dir, LABS / "net-001" / ".state")
        self.assertEqual(inst.sessions_dir, LABS / "net-001" / "sessions")
        self.assertEqual(inst.clab_name, "net001")
        self.assertEqual(inst.topology_file, LABS / "net-001" / "topo-3switch-2host.clab.yaml")
        self.assertEqual(inst.container("sw2"), "clab-net001-sw2")

    def test_render_writes_nothing(self):
        inst = Instance(LABS / "net-002")
        self.assertEqual(inst.render(), inst.topology_file)
        self.assertFalse((self.tmp / "instances").exists())
        self.assertEqual(inst.rendered_topology(), inst.topology)

    def test_default_from_env(self):
        self.assertEqual(Instance.from_env(LABS / "net-001").user, "local")
        os.environ["LAB_INSTANCE"] = "alice"
        self.assertEqual(Instance.from_env(LABS / "net-001").user, "alice")
        self.assertEqual(Lab(LABS / "net-001").instance.user, "alice")

    def test_lab_keeps_old_behavior(self):
        lab = Lab(LABS / "net-001")
        self.assertEqual(lab.state, LABS / "net-001" / ".state")
        self.assertEqual(lab.lab_name, "net001")
        self.assertEqual(lab.container("host-a"), "clab-net001-host-a")


class TestUserInstance(InstanceCase):
    def render(self, lab_id, user):
        inst = Instance(LABS / lab_id, user)
        path = inst.render()
        return inst, yaml.safe_load(path.read_text())

    def test_layout_and_name(self):
        inst, topo = self.render("net-002", "a")
        base = self.tmp / "instances" / "a" / "net-002"
        self.assertEqual(inst.dir, base)
        self.assertEqual(inst.state_dir, base / ".state")
        self.assertEqual(inst.sessions_dir, base / "sessions")
        self.assertEqual(inst.topology_file, base / "topology.clab.yaml")
        self.assertEqual(topo["name"], "net002-a")
        self.assertEqual(inst.container("r1"), "clab-net002-a-r1")
        # Topologi soal tidak ikut berubah.
        self.assertEqual(Instance(LABS / "net-002").topology["name"], "net002")

    def test_paths_absolute(self):
        inst, topo = self.render("net-002", "a")
        binds = topo["topology"]["defaults"]["binds"]
        self.assertIn(f"{PLATFORM / 'lab-rc.sh'}:/etc/lab/rc:ro", binds)
        self.assertIn(f"{inst.state_dir / 'events'}:/var/log/lab", binds)
        for bind in binds:
            self.assertTrue(os.path.isabs(bind.split(":")[0]), bind)
        r1 = topo["topology"]["nodes"]["r1"]
        self.assertEqual(r1["startup-config"], str(LABS / "net-002" / "config" / "r1.rsc"))
        self.assertTrue(Path(r1["startup-config"]).is_file())
        # Bagian lain tetap: exec, link, kind.
        self.assertEqual(topo["topology"]["links"], Instance(LABS / "net-002").topology["topology"]["links"])

    def test_users_isolated(self):
        a, topo_a = self.render("net-001", "a")
        b, topo_b = self.render("net-001", "b")
        self.assertNotEqual(a.state_dir, b.state_dir)
        self.assertNotEqual(a.container("sw1"), b.container("sw1"))
        self.assertEqual(topo_b["name"], "net001-b")
        events = [x for x in topo_b["topology"]["defaults"]["binds"] if x.endswith(":/var/log/lab")]
        self.assertEqual(events, [f"{b.state_dir / 'events'}:/var/log/lab"])
        self.assertNotIn(str(LABS / "net-001" / ".state"), json.dumps(topo_b))

    def test_marker_and_locate(self):
        inst, _ = self.render("net-001", "a")
        archived = inst.sessions_dir / "20260101-000000"
        archived.mkdir(parents=True)
        found, base = instance.locate(archived)
        self.assertEqual(found, inst)
        self.assertEqual(base, inst.dir)
        found, base = instance.locate(LABS / "net-001" / "golden")
        self.assertEqual((found.user, base), ("local", LABS / "net-001"))

    def test_env_contract(self):
        inst = Instance(LABS / "net-003", "bob")
        env = inst.env({})
        self.assertEqual(env, {"LAB_INSTANCE": "bob", "LAB_PROBLEM_DIR": str(LABS / "net-003"),
                               "LAB_STATE_DIR": str(inst.state_dir),
                               "LAB_CLAB_NAME": "net003-bob", "LAB_TOPO": str(inst.topology_file)})

    def test_lab_and_sessions_follow_instance(self):
        inst = Instance(LABS / "net-001", "a")
        inst.state_dir.mkdir(parents=True)
        (inst.state_dir / "session_id").write_text("20260101-000000\n")
        lab = Lab(inst)
        self.assertEqual(lab.state, inst.state_dir)
        self.assertEqual(lab.session, "20260101-000000")
        self.assertEqual(lab.container("sw2"), "clab-net001-a-sw2")
        dest = sessions.archive(inst)
        self.assertEqual(dest, inst.sessions_dir / "20260101-000000")
        self.assertTrue((dest / "session_id").exists())

    def test_evaluate_resolve(self):
        inst = Instance(LABS / "net-001", "a")
        self.assertEqual(evaluate.resolve(inst), (inst, inst.state_dir, True))
        inst.render()
        archived = inst.sessions_dir / "x"
        archived.mkdir(parents=True)
        self.assertEqual(evaluate.resolve(archived), (inst, archived, False))


class TestMgmtNetwork(InstanceCase):
    """Jaringan management per user: router user A tidak sejaringan dengan router user B."""

    def mgmt(self, lab_id, user):
        return yaml.safe_load(Instance(LABS / lab_id, user).render().read_text())["mgmt"]

    def test_rendered_block(self):
        mgmt = self.mgmt("net-002", "alice")
        self.assertEqual(mgmt["network"], "plab-alice")
        self.assertEqual(mgmt["ipv4-subnet"], "172.20.0.0/24")
        self.assertEqual(mgmt["ipv6-subnet"], "3fff:172:20:0::/64")
        self.assertIs(mgmt["external-access"], False)
        topo = yaml.safe_load(Instance(LABS / "net-002", "alice").topology_file.read_text())
        self.assertEqual(list(topo)[:2], ["name", "mgmt"])

    def test_unique_per_user_and_stable(self):
        a1 = self.mgmt("net-002", "a")
        b = self.mgmt("net-003", "b")
        a2 = self.mgmt("net-003", "a")          # lab lain milik a: subnet sama
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1["ipv4-subnet"], b["ipv4-subnet"])
        self.assertNotEqual(a1["ipv6-subnet"], b["ipv6-subnet"])
        self.assertNotEqual(a1["network"], b["network"])
        # Tersimpan: tetap sama walau "host" sekarang melihat subnet lain terpakai.
        self.used = [(None, instance.ipaddress.ip_network("172.20.0.0/16"))]
        self.assertEqual(self.mgmt("net-001", "a"), a1)
        saved = json.loads((self.tmp / "instances" / "a" / "mgmt.json").read_text())
        self.assertEqual(saved["ipv4_subnet"], a1["ipv4-subnet"])

    def test_skips_default_and_used(self):
        import ipaddress
        self.used = [("lain", ipaddress.ip_network("172.20.0.0/23")),       # indeks 0 dan 1
                     (None, ipaddress.ip_network("3fff:172:20:2::/64"))]     # indeks 2 (IPv6)
        self.assertEqual(self.mgmt("net-001", "a")["ipv4-subnet"], "172.20.3.0/24")
        # Jaringan docker milik user itu sendiri tidak dianggap bentrok.
        self.used = [("plab-b", ipaddress.ip_network("172.20.0.0/24"))]
        self.assertEqual(self.mgmt("net-001", "b")["ipv4-subnet"], "172.20.0.0/24")
        subnets = set()
        for i in range(25):
            self.used = []
            subnets.add(self.mgmt("net-001", f"u{i}")["ipv4-subnet"])
        self.assertEqual(len(subnets), 25)
        self.assertNotIn("172.20.20.0/24", subnets)   # default containerlab (instance local)

    def test_pool_exhausted(self):
        import ipaddress
        self.used = [(None, ipaddress.ip_network("172.20.0.0/16"))]
        with self.assertRaises(InstanceError):
            Instance(LABS / "net-001", "a").render()

    def test_release(self):
        first = self.mgmt("net-001", "a")
        instance.release_mgmt("a")
        self.mgmt("net-001", "b")                 # b mengambil subnet yang dilepas a
        self.assertEqual(self.mgmt("net-001", "b")["ipv4-subnet"], first["ipv4-subnet"])

    def test_local_unchanged(self):
        inst = Instance(LABS / "net-002")
        self.assertNotIn("mgmt", inst.rendered_topology())
        self.assertFalse((self.tmp / "instances").exists())
        with self.assertRaises(InstanceError):
            instance.allocate_mgmt("local")


class TestValidation(InstanceCase):
    def test_rejects_bad_names(self):
        for user in ["../x", "a/b", "..", "", "A", "a b", "a_b", "x" * 33, "a\n", None, "/etc"]:
            with self.assertRaises(InstanceError, msg=repr(user)):
                Instance(LABS / "net-001", user)

    def test_rejects_bad_env(self):
        os.environ["LAB_INSTANCE"] = "../../etc"
        with self.assertRaises(InstanceError):
            Instance.from_env(LABS / "net-001")

    def test_accepts_valid(self):
        for user in ["a", "user-01", "x" * 32]:
            self.assertEqual(Instance(LABS / "net-001", user).user, user)


class TestLabenv(InstanceCase):
    """labenv.sh: default layout lama tanpa env, menghormati env dari reset-lab."""

    def run_labenv(self, lab_id, env):
        script = LABS / lab_id / "verify.sh"   # $0 menentukan LAB_DIR
        code = f'source {PLATFORM / "labenv.sh"}; echo "$LAB_STATE_DIR|$LAB_CLAB_NAME|$LAB_TOPO|$(ctr r1)"'
        out = subprocess.run(["bash", "-c", code, str(script)], capture_output=True, text=True,
                             env={"PATH": os.environ["PATH"], **env}, cwd="/", check=True)
        return out.stdout.strip().split("|")

    def test_default_old_layout(self):
        state, name, topo, ctr = self.run_labenv("net-002", {})
        self.assertEqual(state, str(LABS / "net-002" / ".state"))
        self.assertEqual(name, "net002")
        self.assertEqual(topo, str(LABS / "net-002" / "topo-2router.clab.yaml"))
        self.assertEqual(ctr, "clab-net002-r1")

    def test_exported_env_wins(self):
        inst = Instance(LABS / "net-002", "a")
        state, name, topo, ctr = self.run_labenv("net-002", inst.env({}))
        self.assertEqual((state, name, topo), (str(inst.state_dir), "net002-a", str(inst.topology_file)))
        self.assertEqual(ctr, "clab-net002-a-r1")

    def test_env_of_other_lab_is_recomputed(self):
        # Env sisa milik net-001 tidak boleh dipakai script net-002 (ctr dan state harus net-002).
        state, name, topo, ctr = self.run_labenv("net-002", Instance(LABS / "net-001", "a").env({}))
        # Dihitung ulang lewat instance.py di subprocess (folder instance asli, bukan tmp test).
        self.assertEqual((name, ctr), ("net002-a", "clab-net002-a-r1"))
        self.assertTrue(state.endswith("instances/a/net-002/.state"), state)

    def test_labenv_non_local_without_env(self):
        state, name, _, ctr = self.run_labenv("net-002", {"LAB_INSTANCE": "alice"})
        self.assertEqual((name, ctr), ("net002-alice", "clab-net002-alice-r1"))
        self.assertTrue(state.endswith("var/instances/alice/net-002/.state"), state)

    def test_lab_scripts_use_contract(self):
        """Script soal tidak menulis nama container atau .state/ secara langsung."""
        for script in sorted(LABS.glob("*/*.sh")) + sorted((PLATFORM / "templates" / "lab").glob("*.sh")):
            text = script.read_text()
            self.assertNotRegex(text, r"clab-[a-z0-9_$]", script)
            self.assertNotRegex(text, r"[\s\"'/]\.state/", script)


class TestUsernameRules(unittest.TestCase):
    """Username akun = nama instance lab: aturannya harus identik."""

    def test_same_regex(self):
        import accounts
        self.assertEqual(accounts.USERNAME_RE.pattern, instance.USER_RX.pattern.strip("^$"))
        for bad in ("-a", "A", "a b", "a/b", "", "x" * 33):
            self.assertRaises(InstanceError, Instance, LABS / "net-001", bad)
            self.assertRaises(accounts.AccountError, accounts.validate_username, bad)
        for good in ("a", "a-", "1abc", "x" * 32):
            self.assertEqual(accounts.validate_username(good), good)

    def test_local_reserved_for_accounts(self):
        import accounts
        self.assertRaises(accounts.AccountError, accounts.validate_username, "local")


class TestWinbox(InstanceCase):
    """Port Winbox per user: rumus base + indeks*8 + slot, sama di render dan winbox_ports()."""

    def setUp(self):
        super().setUp()
        self.base = 28000
        patcher = mock.patch.object(instance, "winbox_base", lambda: self.base)
        patcher.start()
        self.addCleanup(patcher.stop)

    def nodes(self, lab_id, user):
        inst = Instance(LABS / lab_id, user)
        topo = yaml.safe_load(inst.render().read_text())
        return inst, topo["topology"]["nodes"]

    def ports(self, nodes):
        return {n: s["ports"] for n, s in nodes.items() if "ports" in s}

    def test_render_ros_only_with_formula(self):
        inst, nodes = self.nodes("net-003", "alice")
        index = instance._read_mgmt(self.tmp / "instances" / "alice" / "mgmt.json")
        ros_nodes = sorted(n for n, s in nodes.items() if s.get("kind", "linux") == "mikrotik_ros"
                           or (n in inst.topology["topology"]["nodes"]
                               and inst.topology["topology"]["nodes"][n].get("kind") == "mikrotik_ros"))
        self.assertGreaterEqual(len(ros_nodes), 2)
        want = {n: [f"{28000 + index * 8 + i}:8291"] for i, n in enumerate(ros_nodes)}
        self.assertEqual(self.ports(nodes), want)          # node linux tidak punya ports
        self.assertEqual(len({p[0] for p in want.values()}), len(ros_nodes))
        self.assertEqual(inst.winbox_ports(), {n: int(p[0].split(":")[0]) for n, p in want.items()})

    def test_panel_follows_rendered_topology_not_live_config(self):
        # Config diubah saat lab berjalan: container masih mem-publish port lama sampai deploy ulang.
        inst, _ = self.nodes("net-003", "alice")
        before = inst.winbox_ports()
        self.base = 30000
        self.assertEqual(inst.winbox_ports(), before)
        self.base = 0
        self.assertEqual(inst.winbox_ports(), before)
        inst.render()                                      # deploy ulang = render ulang
        self.assertEqual(inst.winbox_ports(), {})

    def test_winbox_ports_before_render_is_empty(self):
        self.assertEqual(Instance(LABS / "net-003", "alice").winbox_ports(), {})
        self.assertFalse((self.tmp / "instances" / "alice" / "mgmt.json").exists())

    def test_local_and_disabled(self):
        self.assertEqual(Instance(LABS / "net-003").winbox_ports(), {})
        self.assertNotIn("ports", str(Instance(LABS / "net-003").rendered_topology()))
        self.base = 0
        inst, nodes = self.nodes("net-003", "alice")
        self.assertEqual(self.ports(nodes), {})
        self.assertEqual(inst.winbox_ports(), {})

    def test_two_users_do_not_collide(self):
        a, _ = self.nodes("net-003", "alice")
        b, _ = self.nodes("net-003", "bob")
        pa, pb = a.winbox_ports(), b.winbox_ports()
        self.assertTrue(pa and pb)
        self.assertFalse(set(pa.values()) & set(pb.values()))

    def test_more_than_eight_routers(self):
        src = self.tmp / "lab"
        src.mkdir()
        nodes = {f"r{i}": {"kind": "mikrotik_ros", "image": "x"} for i in range(9)}
        (src / "problem.yaml").write_text("lab_topology: t.clab.yaml\n")
        (src / "t.clab.yaml").write_text(yaml.safe_dump({"name": "t", "topology": {"nodes": nodes}}))
        with self.assertRaises(InstanceError):
            Instance(src, "alice").render()

    def test_existing_ports_kept_and_defaults_kind(self):
        src = self.tmp / "lab"
        src.mkdir()
        (src / "problem.yaml").write_text("lab_topology: t.clab.yaml\n")
        topo = {"name": "t", "topology": {"defaults": {"kind": "mikrotik_ros"},
                                          "nodes": {"b": {"ports": ["9999:80"]}, "a": None}}}
        (src / "t.clab.yaml").write_text(yaml.safe_dump(topo))
        inst = Instance(src, "alice")
        nodes = yaml.safe_load(inst.render().read_text())["topology"]["nodes"]
        index = instance._read_mgmt(self.tmp / "instances" / "alice" / "mgmt.json")
        self.assertEqual(nodes["a"]["ports"], [f"{28000 + index * 8}:8291"])
        self.assertEqual(nodes["b"]["ports"], ["9999:80", f"{28000 + index * 8 + 1}:8291"])


class TestWinboxBase(unittest.TestCase):
    def test_reads_config_and_failsafe(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "server.yaml"
            with mock.patch.dict(os.environ, {"LAB_CONFIG": str(cfg)}):
                self.assertEqual(instance.winbox_base(), 0)          # file hilang = 0
                cfg.write_text("mode: server\ndata_dir: /srv/x\nwinbox_ports: 30000\n")
                self.assertEqual(instance.winbox_base(), 30000)
                cfg.write_text("mode: server\nwinbox_ports: 5\n")
                self.assertEqual(instance.winbox_base(), 0)          # config rusak = 0


if __name__ == "__main__":
    unittest.main()
