#!/usr/bin/env python3
"""Instance lab: satu soal (labs/<id>/) yang dideploy untuk satu user.

Soal = definisi (problem.yaml, topologi, script). Instance = lab yang berjalan
milik seorang user: nama lab containerlab, container, dan state sesinya sendiri,
sehingga beberapa user bisa memainkan soal yang sama bersamaan.

  user `local`  layout lama persis (install pribadi, golden, autoplay):
                state di labs/<id>/.state/, nama lab dan file topologi asli.
  user lain     <instances>/<user>/<id>/ berisi .state/, sessions/, dan
                topology.clab.yaml hasil render: `name: <nama>-<user>`, semua
                path relatif jadi absolut, .state/... menunjuk state instance.

Jaringan management: instance non-local mendapat jaringan docker sendiri
(blok `mgmt` hasil render, network `plab-<user>`), sehingga router RouterOS satu
user tidak bisa menjangkau router user lain lewat jaringan management (login
default admin/admin). Subnet-nya dialokasikan sekali per user, disimpan di
<instances>/<user>/mgmt.json, dan dipakai ulang di setiap deploy. Instance
`local` tetap di jaringan default containerlab (clab, 172.20.20.0/24).

<instances> = var/instances/ di mode Pribadi, <data_dir>/instances/ di mode
Server (config.py). Server web, reset-lab, dan script soal membaca config yang
sama (LAB_CONFIG ikut diwariskan lewat env), jadi semuanya sepakat lokasinya.

Instance dipilih dengan env LAB_INSTANCE (default `local`). Sengaja bukan
LAB_USER: itu nama tampilan akun di web UI (server.py), bukan pemilik lab.

  instance.py env <problem_dir> [--render] [--node N]

mencetak baris KEY=nilai (siap di-eval bash) untuk instance dari LAB_INSTANCE:
LAB_INSTANCE, LAB_STATE_DIR, LAB_CLAB_NAME, LAB_TOPO, ditambah LAB_CTR dan
LAB_NODE_KIND kalau --node diberikan. --render menulis topologi instance dulu.
Dipakai reset-lab, lab-shell, serve, dan labenv.sh.
"""

if __name__ == "__main__":
    import _venv  # noqa: E402  (Python venv, lihat _venv.py)
    _venv.ensure()

import copy
import fcntl
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# None = ikut config (instances_dir()). Test boleh menimpanya dengan path tetap.
INSTANCES_DIR = None
LOCAL = "local"
USER_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")   # sama dengan accounts.USERNAME_RE
MARKER = "instance.json"     # di direktori instance: menunjuk balik ke direktori soal
STATE = ".state"

# --- jaringan management per user ---------------------------------------------------
# Pool: 172.20.<n>.0/24, n = 0..255 kecuali 20 (172.20.20.0/24 = jaringan default
# containerlab, dipakai instance local). Alasan memilih 172.20.0.0/16:
#   - bukan 10.x / 192.168.x / 100.64.x yang sering dipakai LAN kampus, Wi-Fi
#     rumahan, dan Tailscale; route ke subnet itu di host bisa memutus akses klien.
#   - docker hanya mengambil /16 utuh dari default-address-pools yang belum
#     bertumpang tindih; begitu jaringan clab (172.20.20.0/24) pernah ada, docker
#     tidak akan memilih 172.20.0.0/16 untuk jaringan otomatisnya.
#   - 172.31.255.x (jaringan internal vrnetlab di dalam container) dan
#     172.17.0.0/16 (docker0) ada di luar pool.
# IPv6 mengikuti pola default containerlab (3fff:172:20:20::/64): 3fff:172:20:<n>::/64.
# Angka desimal n ditulis apa adanya sebagai grup hex: tetap unik, dan "20" tidak
# pernah dipakai, jadi tidak bentrok dengan default. Tanpa ipv6-subnet eksplisit,
# containerlab memberi semua jaringan default IPv6 yang sama -> deploy kedua gagal
# karena pool bertumpang tindih.
# Kapasitas: 255 user punya subnet sekaligus (target mode Server 10-40).
MGMT_FILE = "mgmt.json"
MGMT_LOCK = ".mgmt.lock"
MGMT_POOL = range(256)
MGMT_SKIP = {20}


class InstanceError(ValueError):
    pass


_config_cache = {}


def instances_dir():
    """Induk direktori instance non-local: var/instances (pribadi) atau data_dir/instances (server)."""
    if INSTANCES_DIR is not None:
        return Path(INSTANCES_DIR)
    import config   # import lambat: CLI `instance.py env` tetap ringan untuk install pribadi
    path = config.config_path()
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        key = (str(path), None)
    # Server membuat Instance berkali-kali per request; config hanya dibaca ulang kalau filenya berubah.
    if key not in _config_cache:
        cfg = config.load()
        _config_cache.clear()
        _config_cache[key] = cfg.data_dir / "instances" if cfg.is_server else ROOT / "var" / "instances"
    return _config_cache[key]


def mgmt_subnets(index):
    return f"172.20.{index}.0/24", f"3fff:172:20:{index}::/64"


def mgmt_network_name(user):
    return f"plab-{user}"


def used_subnets():
    """Subnet IPv4/IPv6 yang sudah dipakai di host: jaringan docker + route kernel.

    Best effort (docker/ip tidak ada = dianggap kosong). Kembalikan list
    (nama_jaringan_docker_atau_None, ip_network). Fungsi modul supaya test bisa mem-patch.
    """
    found = []
    try:
        ids = subprocess.run(["docker", "network", "ls", "-q"], capture_output=True, text=True,
                             timeout=10).stdout.split()
        if ids:
            out = subprocess.run(["docker", "network", "inspect", "-f",
                                  "{{.Name}}{{range .IPAM.Config}} {{.Subnet}}{{end}}", *ids],
                                 capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                name, *subnets = line.split()
                for subnet in subnets:
                    try:
                        found.append((name, ipaddress.ip_network(subnet, strict=False)))
                    except ValueError:
                        pass
    except (OSError, subprocess.TimeoutExpired):
        pass
    for family in ("-4", "-6"):
        try:
            out = subprocess.run(["ip", family, "route", "show"], capture_output=True, text=True,
                                 timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in out.splitlines():
            dest = line.split()[0] if line.split() else ""
            if dest == "default":
                continue
            try:
                found.append((None, ipaddress.ip_network(dest, strict=False)))
            except ValueError:
                pass
    return found


def _read_mgmt(path):
    try:
        data = json.loads(path.read_text())
        index = int(data["index"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return index if index in MGMT_POOL and index not in MGMT_SKIP else None


def allocate_mgmt(user):
    """Blok `mgmt` containerlab untuk user non-local; alokasikan subnet kalau belum ada.

    Stabil: indeks tersimpan di <instances>/<user>/mgmt.json dan dipakai ulang.
    Bebas tabrakan: dipilih di bawah file lock (dua deploy paralel = dua proses
    reset-lab), melewati indeks milik user lain dan subnet yang sudah dipakai di host.
    """
    if user == LOCAL:
        raise InstanceError("Instance local memakai jaringan management default containerlab.")
    root = instances_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / user / MGMT_FILE
    with open(root / MGMT_LOCK, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index = _read_mgmt(path)
        if index is None:
            taken = {i for p in root.glob(f"*/{MGMT_FILE}") if p != path and (i := _read_mgmt(p)) is not None}
            # Jaringan milik user ini sendiri (mis. mgmt.json terhapus) tidak dihitung bentrok.
            busy = [net for name, net in used_subnets() if name != mgmt_network_name(user)]
            for candidate in MGMT_POOL:
                if candidate in MGMT_SKIP or candidate in taken:
                    continue
                nets = [ipaddress.ip_network(s) for s in mgmt_subnets(candidate)]
                if not any(n.version == b.version and n.overlaps(b) for n in nets for b in busy):
                    index = candidate
                    break
            else:
                raise InstanceError("Pool subnet management (172.20.0.0/16) habis: hapus mgmt.json "
                                    f"milik akun yang sudah tidak ada di {root}.")
            path.parent.mkdir(parents=True, exist_ok=True)
            v4, v6 = mgmt_subnets(index)
            path.write_text(json.dumps({"index": index, "ipv4_subnet": v4, "ipv6_subnet": v6}) + "\n")
    v4, v6 = mgmt_subnets(index)
    # external-access false: containerlab tidak memasang aturan ACCEPT "-o <bridge>" di
    # chain DOCKER-USER. Aturan itu mengizinkan paket dari interface mana pun (termasuk
    # bridge user lain) masuk ke bridge ini, sehingga isolasi antar-jaringan docker
    # tidak berlaku. Host tetap bisa menjangkau node (host ada di bridge itu sendiri).
    return {"network": mgmt_network_name(user), "ipv4-subnet": v4, "ipv6-subnet": v6,
            "external-access": False}


def release_mgmt(user):
    """Lepas subnet user (akun dihapus). Jaringan docker-nya hilang saat destroy --cleanup."""
    try:
        (instances_dir() / user / MGMT_FILE).unlink()
    except FileNotFoundError:
        pass


def env_user():
    return os.environ.get("LAB_INSTANCE") or LOCAL


class Instance:
    def __init__(self, problem_dir, user=LOCAL):
        if not isinstance(user, str) or not USER_RX.fullmatch(user):
            raise InstanceError(f"Nama instance tidak valid: {user!r} (huruf kecil, angka, '-', maks. 32)")
        self.problem_dir = Path(problem_dir).resolve()
        self.user = user
        problem_file = self.problem_dir / "problem.yaml"
        if not problem_file.is_file():
            raise InstanceError(f"Tidak ada problem.yaml di {self.problem_dir}")
        self.problem = yaml.safe_load(problem_file.read_text())
        self.source_topology = self.problem_dir / self.problem["lab_topology"]
        self.topology = yaml.safe_load(self.source_topology.read_text())
        self.base_name = self.topology["name"]

        if self.is_local:
            self.dir = self.problem_dir
            self.clab_name = self.base_name
            self.topology_file = self.source_topology
        else:
            self.dir = instances_dir() / user / self.problem_dir.name
            self.clab_name = f"{self.base_name}-{user}"
            self.topology_file = self.dir / "topology.clab.yaml"
        self.state_dir = self.dir / STATE
        self.sessions_dir = self.dir / "sessions"

    @classmethod
    def from_env(cls, problem_dir):
        """Instance pilihan LAB_INSTANCE (default local). Untuk CLI dan script soal."""
        return cls(problem_dir, env_user())

    @classmethod
    def coerce(cls, value):
        """Instance apa adanya, atau path direktori soal → Instance.from_env."""
        return value if isinstance(value, cls) else cls.from_env(value)

    @property
    def is_local(self):
        return self.user == LOCAL

    def container(self, node):
        return f"clab-{self.clab_name}-{node}"

    def env(self, base=None):
        """Env untuk script soal dan tool CLI (kontrak di labenv.sh). base: env yang ditimpa."""
        env = dict(os.environ if base is None else base)
        env.update(LAB_INSTANCE=self.user, LAB_PROBLEM_DIR=str(self.problem_dir), LAB_STATE_DIR=str(self.state_dir),
                   LAB_CLAB_NAME=self.clab_name, LAB_TOPO=str(self.topology_file))
        return env

    # --- render topologi -------------------------------------------------------------

    def _path(self, value):
        """Path relatif di topologi soal → absolut. .state/... → state instance."""
        if not isinstance(value, str) or not value or "\n" in value or os.path.isabs(value) \
                or "://" in value or value.startswith("~"):
            return value
        parts = Path(value).parts
        if parts and parts[0] == STATE:
            return str(self.state_dir.joinpath(*parts[1:]))
        return str((self.problem_dir / value).resolve())

    def _bind(self, bind):
        if not isinstance(bind, str):
            return bind
        src, sep, rest = bind.partition(":")
        return self._path(src) + sep + rest if sep else bind

    def _fix_node(self, spec):
        if not isinstance(spec, dict):
            return spec
        spec = dict(spec)
        if isinstance(spec.get("binds"), list):
            spec["binds"] = [self._bind(b) for b in spec["binds"]]
        for key in ("startup-config", "license"):
            if key in spec:
                spec[key] = self._path(spec[key])
        if isinstance(spec.get("env-files"), list):
            spec["env-files"] = [self._path(p) for p in spec["env-files"]]
        return spec

    def rendered_topology(self):
        """Topologi containerlab untuk instance ini (dict)."""
        topo = copy.deepcopy(self.topology)
        if self.is_local:
            return topo
        # mgmt tepat setelah name supaya mudah dibaca di file hasil render.
        rest = {k: v for k, v in topo.items() if k not in ("name", "mgmt")}
        topo = {"name": self.clab_name, "mgmt": allocate_mgmt(self.user), **rest}
        body = topo.get("topology") or {}
        if "defaults" in body:
            body["defaults"] = self._fix_node(body["defaults"])
        for section in ("kinds", "groups", "nodes"):
            if isinstance(body.get(section), dict):
                body[section] = {k: self._fix_node(v) for k, v in body[section].items()}
        return topo

    def render(self):
        """Siapkan direktori instance + topologi hasil render. local: tidak menulis apa pun."""
        if self.is_local:
            return self.topology_file
        self.dir.mkdir(parents=True, exist_ok=True)
        header = (f"# Dibuat otomatis oleh platform/instance.py dari {self.source_topology}\n"
                  f"# untuk instance '{self.user}'. Jangan diedit: ditimpa setiap reset.\n")
        self.topology_file.write_text(header + yaml.safe_dump(self.rendered_topology(), sort_keys=False))
        self.ensure_marker()
        return self.topology_file

    def ensure_marker(self):
        """Tulis instance.json (dipakai locate() untuk arsip sesi) kalau belum ada.

        render() selalu menulisnya; dipanggil juga oleh server untuk direktori
        instance yang dibuat tanpa reset (mis. arsip hasil salinan migrate-server).
        """
        if self.is_local:
            return
        marker = self.dir / MARKER
        if not marker.is_file():
            self.dir.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({"problem_dir": str(self.problem_dir), "user": self.user}) + "\n")

    def __eq__(self, other):
        return isinstance(other, Instance) and (self.problem_dir, self.user) == (other.problem_dir, other.user)

    def __hash__(self):
        return hash((self.problem_dir, self.user))

    def __repr__(self):
        return f"Instance({str(self.problem_dir)!r}, {self.user!r})"


def locate(path):
    """Instance pemilik sebuah path (direktori soal, .state/, atau arsip sessions/<sesi>/).

    Kembalikan (instance, base) dengan base = direktori soal / direktori instance
    yang memuat path, atau (None, None) kalau tidak ditemukan.
    """
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if (parent / "problem.yaml").is_file():
            return Instance(parent, LOCAL), parent
        marker = parent / MARKER
        if marker.is_file():
            data = json.loads(marker.read_text())
            return Instance(data["problem_dir"], data["user"]), parent
    return None, None


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    env_parser = sub.add_parser("env", help="cetak env instance (KEY=nilai) untuk bash")
    env_parser.add_argument("problem_dir")
    env_parser.add_argument("--render", action="store_true", help="tulis topologi instance dulu")
    env_parser.add_argument("--node", help="tambahkan LAB_CTR dan LAB_NODE_KIND untuk node ini")
    args = parser.parse_args(argv)
    from config import ConfigError
    try:
        inst = Instance.from_env(args.problem_dir)
        if args.render:
            inst.render()
    except (InstanceError, ConfigError, OSError, KeyError) as error:
        sys.exit(str(error))
    values = inst.env({})
    if args.node:
        import ros
        values["LAB_CTR"] = inst.container(args.node)
        values["LAB_NODE_KIND"] = ros.node_kind(inst.topology, args.node)
    for key, value in values.items():
        print(f"{key}={shlex.quote(value)}")


if __name__ == "__main__":
    main(sys.argv[1:])
