"""Kapasitas mode Server: batas RAM, deploy bersamaan, satu lab per user, lab idle.

Mode Server menjalankan lab 10-40 user di satu mesin. Tanpa batas, satu kelas
yang serentak menekan Deploy di net-003 (3 VM RouterOS per user) menghabiskan RAM
dan OOM killer mematikan lab acak milik siapa saja. Modul ini memegang aturannya;
server.py hanya memanggil.

  config.capacity.mem_mb       anggaran RAM untuk SEMUA lab (perkiraan, MB)
  config.capacity.max_deploys  deploy (reset-lab) yang boleh jalan bersamaan
  config.capacity.idle_minutes lab tanpa aktivitas selama ini dimatikan

Keputusan desain:
- RAM dihitung dari PERKIRAAN per soal (problem.yaml `resources.mem_mb`, atau
  dihitung dari topologi), bukan dari `docker stats`. VM RouterOS baru memakai
  RAM penuh setelah boot (menit), jadi angka nyata saat deploy dimulai terlalu
  kecil dan keputusan jadi terlambat. Perkiraan juga deterministik untuk test.
- Lab yang sedang dideploy ikut dihitung (reservasi) sampai deploy selesai:
  container-nya belum (lengkap) terlihat di docker, tapi RAM-nya pasti dipakai.
- Satu lab berjalan per user: deploy lab baru = lab lain milik user itu
  dimatikan dulu. Pemain hanya bisa mengerjakan satu tiket dalam satu waktu,
  dan tanpa aturan ini satu akun bisa memegang RAM 3 lab.
- Penemuan lab dari docker (label `containerlab=<nama lab>`), bukan dari catatan
  server: lab yang dideploy dari terminal atau sebelum server restart ikut terlihat.
- Fungsi docker dan reset-lab disuntikkan (list_running, runner) supaya test
  berjalan tanpa docker.

Integrasi ke server.py: lihat docs/arsitektur.md (Kapasitas) dan fungsi di bawah.
"""

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from instance import LOCAL, Instance, InstanceError

ROOT = Path(__file__).resolve().parent.parent
LABS = ROOT / "labs"
RESET_LAB = ROOT / "platform" / "reset-lab"

# Perkiraan RAM per node menurut kind containerlab (MB), dipakai kalau problem.yaml
# tidak punya resources.mem_mb. Angka sengaja dibulatkan ke atas:
#   mikrotik_ros  VM CHR 256 MB (vrnetlab launch.py, amd64) + qemu ~60-80 MB
#                 + python/uv launch.py ~40 MB + container  -> ~400 MB
#   linux         netshoot diam ~5-10 MB; shell docker exec pemain menambah
#                 beberapa MB                                -> ~30 MB
# Kind lain belum pernah diukur: 512 MB (konservatif; NOS berbasis VM/container
# besar seperti SR Linux butuh lebih, pasang resources.mem_mb di soalnya).
KIND_MB = {"mikrotik_ros": 400, "linux": 30}
DEFAULT_KIND_MB = 512


class CapacityError(Exception):
    pass


@dataclass
class Decision:
    """Hasil pemeriksaan deploy. bool(decision) = boleh."""
    allowed: bool
    reason: str = None          # kalimat Indonesia siap tampil di web UI
    code: str = "ok"            # ok | memory | too_big | busy | docker
    destroy: list = field(default_factory=list)   # lab lain milik user, dimatikan sebelum deploy
    need_mb: int = 0            # perkiraan RAM lab yang akan dideploy
    used_mb: int = 0            # perkiraan RAM lab lain yang tetap jalan
    limit_mb: int = 0

    def __bool__(self):
        return self.allowed


# --- perkiraan RAM -----------------------------------------------------------------

def estimate_topology(topology, kind_mb=None):
    """Perkiraan RAM (MB) dari topologi containerlab: jumlah per node menurut kind."""
    table = {**KIND_MB, **(kind_mb or {})}
    body = (topology or {}).get("topology") or {}
    defaults, groups = body.get("defaults") or {}, body.get("groups") or {}
    total = 0
    for spec in (body.get("nodes") or {}).values():
        spec = spec or {}
        kind = spec.get("kind") or (groups.get(spec.get("group")) or {}).get("kind") \
            or defaults.get("kind") or "linux"
        total += table.get(kind, DEFAULT_KIND_MB)
    return total


def estimate(inst, kind_mb=None):
    """Perkiraan RAM satu instance: resources.mem_mb di problem.yaml, kalau tidak ada dari topologi."""
    mem = (inst.problem.get("resources") or {}).get("mem_mb")
    if isinstance(mem, int) and not isinstance(mem, bool) and mem > 0:
        return mem
    return estimate_topology(inst.topology, kind_mb)


# --- penemuan lab yang berjalan -------------------------------------------------------

def docker_lab_names(include_stopped=False):
    """Nama lab containerlab (label `containerlab`) yang punya container di docker.

    include_stopped: ikut container yang berhenti (tidak memakai RAM, tapi lab-nya
    tetap ada dan perlu di-destroy). OSError kalau docker tidak bisa diakses.
    """
    cmd = ["docker", "ps", "--filter", "label=containerlab", "--format", '{{.Label "containerlab"}}']
    if include_stopped:
        cmd.insert(2, "-a")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired as error:
        raise OSError(f"docker ps tidak menjawab: {error}") from None
    if proc.returncode != 0:
        raise OSError(f"docker ps gagal: {proc.stderr.strip()}")
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def lab_index(labs_root=LABS):
    """{name topologi soal: direktori soal} untuk semua soal di labs_root."""
    index = {}
    for problem_file in sorted(Path(labs_root).glob("*/problem.yaml")):
        try:
            problem = yaml.safe_load(problem_file.read_text()) or {}
            topo = yaml.safe_load((problem_file.parent / problem["lab_topology"]).read_text()) or {}
        except (OSError, KeyError, TypeError, yaml.YAMLError):
            continue
        if topo.get("name"):
            index[str(topo["name"])] = problem_file.parent
    return index


def instance_for(clab_name, index):
    """Nama lab containerlab -> Instance, atau None kalau bukan lab P-lab.

    Instance user bernama `<name>-<user>`; lablint melarang '-' di name topologi,
    jadi '-' pertama selalu pemisah. Tanpa '-' = instance local.
    """
    base, sep, user = clab_name.partition("-")
    if base not in index:
        return None
    try:
        return Instance(index[base], user if sep else LOCAL)
    except InstanceError:
        return None


def last_activity(inst):
    """Waktu (epoch) aktivitas terakhir instance: mtime file terbaru di .state/.

    Dihitung: file langsung di .state/ (session_id, checkpoints.jsonl, hints,
    evaluation.json, ...), events/ (command dan event Winbox), tty/ (rekaman
    terminal). *.log dilewati: log watcher bisa ditulis tanpa ada pemain.
    None kalau .state/ tidak ada.
    """
    state = inst.state_dir
    if not state.is_dir():
        return None
    latest = state.stat().st_mtime
    candidates = list(state.iterdir())
    for sub in ("events", "tty"):
        if (state / sub).is_dir():
            candidates += list((state / sub).iterdir())
    for path in candidates:
        if path.suffix == ".log":
            continue
        try:
            latest = max(latest, path.stat().st_mtime)
        except FileNotFoundError:
            pass
    return latest


# --- kebijakan -------------------------------------------------------------------

class Capacity:
    """Penjaga kapasitas. Thread-safe: DeployJobs menjalankan deploy di thread.

    config       config.Config atau config.Capacity (mem_mb, max_deploys, idle_minutes)
    list_running callable -> nama lab dengan container berjalan (default: docker)
    list_all     callable -> nama lab termasuk yang container-nya berhenti
                 (default: docker; kalau list_running disuntikkan, ikut list_running)
    labs_root    direktori soal (untuk memetakan nama lab -> soal)
    """

    def __init__(self, config, list_running=None, list_all=None, labs_root=LABS, kind_mb=None,
                 one_per_user=True):
        self.cap = getattr(config, "capacity", config)
        self.list_running = list_running or docker_lab_names
        self.list_all = list_all or (list_running if list_running else (lambda: docker_lab_names(True)))
        self.labs_root = Path(labs_root)
        self.kind_mb = kind_mb
        self.one_per_user = one_per_user
        self.cond = threading.Condition()
        self.deploying = {}      # Instance -> perkiraan MB (reservasi sampai release_deploy)

    # --- dasar
    def estimate(self, inst):
        return estimate(inst, self.kind_mb)

    def _instances(self, names):
        index = lab_index(self.labs_root)
        found = {instance_for(name, index) for name in names}
        found.discard(None)
        return found

    def running(self):
        """Instance P-lab dengan container berjalan (memakai RAM)."""
        return self._instances(self.list_running())

    def existing(self):
        """Instance P-lab yang masih punya container (berjalan atau berhenti)."""
        return self._instances(self.list_all())

    def usage(self):
        """Perkiraan RAM terpakai: lab berjalan + lab yang sedang dideploy."""
        with self.cond:
            insts = self.running() | set(self.deploying)
            return {"used_mb": sum(self.estimate(i) for i in insts), "limit_mb": self.cap.mem_mb,
                    "deploying": len(self.deploying), "max_deploys": self.cap.max_deploys,
                    "labs": sorted(f"{i.problem_dir.name}:{i.user}" for i in insts)}

    # --- deploy
    def _decide(self, inst):
        """Keputusan tanpa reservasi. Dipanggil dengan self.cond dipegang."""
        need = self.estimate(inst)
        limit = self.cap.mem_mb
        name = inst.problem.get("id", inst.problem_dir.name)
        try:
            running, existing = self.running(), self.existing()
        except OSError as error:
            return Decision(False, f"Docker tidak bisa diakses, lab tidak bisa dideploy: {error}",
                            "docker", need_mb=need, limit_mb=limit)
        destroy = sorted((i for i in existing if i.user == inst.user and i != inst),
                         key=lambda i: i.problem_dir.name) if self.one_per_user else []
        if need > limit:
            return Decision(False, f"Lab {name} butuh perkiraan {need} MB RAM, melebihi batas server "
                                   f"({limit} MB). Minta admin menaikkan capacity.mem_mb.",
                            "too_big", destroy, need, 0, limit)
        if inst not in self.deploying and len(self.deploying) >= self.cap.max_deploys:
            return Decision(False, f"Sedang ada {len(self.deploying)} deploy berjalan (maks. "
                                   f"{self.cap.max_deploys} bersamaan). Coba lagi sebentar lagi.",
                            "busy", destroy, need, 0, limit)
        # Lab yang akan dimatikan (lab lain user ini) dan lab ini sendiri (redeploy) tidak dihitung.
        others = (running | set(self.deploying)) - set(destroy) - {inst}
        used = sum(self.estimate(i) for i in others)
        if used + need > limit:
            return Decision(False, f"Kapasitas RAM server penuh: {len(others)} lab berjalan memakai perkiraan "
                                   f"{used} MB dari {limit} MB, lab {name} butuh ±{need} MB. Coba lagi setelah "
                                   "ada lab yang selesai, atau hubungi admin.",
                            "memory", destroy, need, used, limit)
        return Decision(True, None, "ok", destroy, need, used, limit)

    def check_deploy(self, user, inst):
        """Boleh men-deploy `inst` sekarang? Tanpa reservasi (untuk pratinjau di UI).

        user = pemilik (nama instance); harus sama dengan inst.user.
        decision.destroy = lab lain milik user yang harus dimatikan sebelum deploy.
        """
        self._check_owner(user, inst)
        with self.cond:
            return self._decide(inst)

    def try_acquire(self, user, inst, wait=0):
        """Periksa dan reservasi slot deploy + RAM secara atomik.

        Kalau decision.allowed, slot dipegang sampai release_deploy(inst) (wajib,
        di finally). wait > 0: tunggu slot max_deploys kosong sampai sekian detik
        (antre); penolakan RAM/ukuran tidak ditunggu karena bisa berjam-jam.
        """
        self._check_owner(user, inst)
        deadline = time.monotonic() + wait
        with self.cond:
            while True:
                decision = self._decide(inst)
                remaining = deadline - time.monotonic()
                if decision.code != "busy" or remaining <= 0:
                    break
                self.cond.wait(min(remaining, 5))   # dibangunkan release_deploy; 5 s = cek ulang docker
            if decision:
                self.deploying[inst] = decision.need_mb
            return decision

    def release_deploy(self, inst):
        with self.cond:
            self.deploying.pop(inst, None)
            self.cond.notify_all()

    def deploy_slot(self, user, inst, wait=0):
        """Context manager: `with cap.deploy_slot(user, inst) as decision:`.

        CapacityError (pesan = decision.reason) kalau ditolak; slot dilepas saat keluar.
        """
        capacity = self

        class _Slot:
            def __enter__(self_):
                self_.decision = capacity.try_acquire(user, inst, wait)
                if not self_.decision:
                    raise CapacityError(self_.decision.reason)
                return self_.decision

            def __exit__(self_, *exc):
                capacity.release_deploy(inst)
                return False

        return _Slot()

    @staticmethod
    def _check_owner(user, inst):
        if user != inst.user:
            raise ValueError(f"instance {inst!r} bukan milik {user!r}")

    # --- pembersihan
    def idle_candidates(self, now=None, busy=None, last_seen=None, include_local=False):
        """Instance yang tidak ada aktivitas selama idle_minutes.

        busy(inst) -> bool: True = jangan disentuh (mis. evaluasi berjalan).
        last_seen(inst) -> epoch|None: aktivitas di luar .state/ (mis. WebSocket
        live terakhir terbuka), diambil yang terbaru.
        Lab yang sedang dideploy dan instance local (milik admin) dilewati.
        """
        now = time.time() if now is None else now
        limit = self.cap.idle_minutes * 60
        with self.cond:
            deploying = set(self.deploying)
        idle = []
        for inst in sorted(self.existing(), key=lambda i: (i.user, i.problem_dir.name)):
            if inst in deploying or (inst.is_local and not include_local) or (busy and busy(inst)):
                continue
            seen = [t for t in (last_activity(inst), last_seen(inst) if last_seen else None) if t]
            if now - max(seen, default=0) >= limit:
                idle.append(inst)
        return idle

    def orphan_candidates(self, active_usernames):
        """Instance milik akun yang sudah nonaktif/terhapus (tidak ada di active_usernames)."""
        active = set(active_usernames)
        return sorted((i for i in self.existing() if not i.is_local and i.user not in active),
                      key=lambda i: (i.user, i.problem_dir.name))


# --- mematikan lab -----------------------------------------------------------------

def archive_abandoned(inst, reason):
    """Arsipkan sesi yang belum dinilai sebelum lab dimatikan; kembalikan path arsip atau None.

    Arsip ditaruh di sessions/<session_id>/ seperti sesi yang dinilai, plus
    abandoned.json. Riwayat di web UI hanya menampilkan arsip ber-evaluation.json,
    jadi arsip ini tidak muncul sebagai sesi bernilai, tapi transkripnya tidak
    hilang (pemain atau admin masih bisa melihat apa yang sudah dikerjakan).
    """
    import sessions   # import lambat: sessions -> instance; capacity tetap ringan untuk test
    state = inst.state_dir
    if not (state / "session_id").is_file() or (state / "evaluation.json").exists():
        return None   # tidak ada sesi, atau sudah dinilai (EvalJobs sudah mengarsipkan)
    dest = sessions.archive(inst)
    (dest / "abandoned.json").write_text(json.dumps({"reason": reason, "ts": time.time()}) + "\n")
    return dest


def destroy(inst, reason="manual", archive=True, runner=subprocess.run, timeout=300):
    """Matikan satu instance: arsip sesi yang belum dinilai, lalu reset-lab --destroy-only.

    reason: replaced (user men-deploy lab lain) | idle | orphan | manual.
    Pemanggil (server) menghentikan watcher instance dulu (RUNTIMES.stop).
    CapacityError kalau containerlab gagal.
    """
    archived = archive_abandoned(inst, reason) if archive else None
    try:
        proc = runner([str(RESET_LAB), "--destroy-only", str(inst.problem_dir)], cwd=str(inst.problem_dir),
                      stdin=subprocess.DEVNULL, capture_output=True, text=True, env=inst.env(), timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CapacityError(f"Gagal mematikan {inst.clab_name}: {error}") from None
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-5:])
        raise CapacityError(f"Gagal mematikan {inst.clab_name}: {tail}")
    return archived


__all__ = ["Capacity", "CapacityError", "Decision", "KIND_MB", "DEFAULT_KIND_MB",
           "archive_abandoned", "destroy", "docker_lab_names", "estimate", "estimate_topology",
           "instance_for", "lab_index", "last_activity"]
