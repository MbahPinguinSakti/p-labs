#!/usr/bin/env python3
"""Web UI P-lab (Fase 3): API + WebSocket + file statis hasil build web/.

  python3 platform/server.py [--port 8000] [--host 127.0.0.1]
  lalu buka http://localhost:8000

Dua mode (config.py):
  Pribadi  satu orang, 127.0.0.1, tanpa login; semua lab memakai instance `local`
           (layout lama labs/<id>/.state).
  Server   10-40 orang di LAN, wajib login (accounts.py, cookie plab_session).
           Tiap user memainkan instance-nya sendiri (instance.py), username = nama
           instance, jadi lab, state, dan arsip sesi user A tidak tersentuh user B.

Server ini:
  - membaca katalog soal dari labs/*/problem.yaml,
  - menjalankan checkpoint watcher per instance untuk sesi aktif; terminal web
    dilayani termbridge.py (WebSocket, router terpisah),
  - mendorong state sesi (checkpoint, aktivitas, hint) lewat WebSocket,
  - membuka hint (hints.py), memulai sesi baru (sessions.rearm), dan menilai
    sesi (evaluate.py) lalu mengarsipkannya ke sessions/ milik instance.

Yang dikirim ke browser sengaja dibatasi: ground truth, parameter soal, definisi
checkpoint, dan teks hint yang belum dibuka tidak pernah keluar dari server.
"""

import argparse
import asyncio
import contextlib
import getpass
import ipaddress
import json
import logging
import math
import os
import random
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import config as configmod  # noqa: E402
import capacity  # noqa: E402
import evaluate  # noqa: E402
import ros  # noqa: E402
import sessions  # noqa: E402
from accounts import AccountStore  # noqa: E402
from checkpoints import Lab  # noqa: E402
from instance import Instance  # noqa: E402
from hints import HintError, hint_list, open_hint, used_levels  # noqa: E402
from llm import LLMError, list_providers  # noqa: E402
from transcript import NosRules, build_timeline, load_events  # noqa: E402

LABS_DIR = Path(os.environ.get("LAB_LABS_DIR", ROOT / "labs"))
WEB_DIST = ROOT / "web" / "dist"
# Nama tampilan di mode Pribadi (tanpa akun). Bukan nama instance: itu selalu `local`.
USER = os.environ.get("LAB_USER") or getpass.getuser()
log = logging.getLogger("p-lab.server")


# --- katalog soal -----------------------------------------------------------------

def lab_dir(lab_id):
    for path in sorted(LABS_DIR.glob("*/problem.yaml")):
        problem = yaml.safe_load(path.read_text())
        if problem.get("id") == lab_id:
            return path.parent
    raise HTTPException(404, f"Lab {lab_id} tidak ada")


def all_lab_dirs():
    return [path.parent for path in sorted(LABS_DIR.glob("*/problem.yaml"))]


def instance(directory, user):
    """Instance milik `user` (dict dari current_user) untuk soal di `directory`.

    Satu-satunya tempat server memilih instance: selalu dari user yang login
    (pribadi: `local`), tidak pernah dari env proses (Instance.from_env).
    """
    return Instance(directory, user["username"])


def user_lab(lab_id, user):
    return Lab(instance(lab_dir(lab_id), user))


def archive_root(inst, kind):
    """sessions/ = arsip milik instance; golden/ = milik soal."""
    return inst.sessions_dir if kind == "sessions" else inst.problem_dir / kind


def session_start(session_id):
    try:
        return datetime.strptime(session_id, "%Y%m%d-%H%M%S").timestamp()
    except (TypeError, ValueError):
        return None


def node_role(name, spec):
    role = (spec or {}).get("labels", {}).get("role") if isinstance(spec, dict) else None
    if role:
        return role
    if name.startswith("fw"):
        return "firewall"
    if name.startswith("sw"):
        return "switch"
    if name[:1] == "r" and name[1:2].isdigit():
        return "router"
    return "host"


def topology(directory, problem):
    topo = yaml.safe_load((directory / problem["lab_topology"]).read_text())
    nodes = topo["topology"]["nodes"]
    labels = (problem.get("design") or {}).get("links", {})
    kinds = {name: ros.node_kind(topo, name) for name in nodes}
    links = []
    for link in topo["topology"].get("links", []):
        a, b = link["endpoints"]
        label = labels.get(f"{a} {b}") or labels.get(f"{b} {a}")
        (an, ai), (bn, bi) = a.split(":"), b.split(":")
        # Nama interface seperti di dalam perangkat (RouterOS: eth1 container = ether2).
        links.append({"a": an, "a_if": ros.display_interface(kinds[an], ai),
                      "b": bn, "b_if": ros.display_interface(kinds[bn], bi), "label": label})
    return {"nodes": [{"id": name, "role": node_role(name, spec), "kind": kinds[name]}
                      for name, spec in nodes.items()],
            "links": links}


def lab_images(directory, problem):
    topo = yaml.safe_load((directory / problem["lab_topology"]).read_text())["topology"]
    specs = [topo.get("defaults") or {}, *(topo.get("kinds") or {}).values(), *(topo.get("nodes") or {}).values()]
    return sorted({spec["image"] for spec in specs if spec and spec.get("image")})


def missing_images(directory, problem):
    """Image container lab yang belum ada di docker lokal (None = docker tidak bisa diakses)."""
    missing = []
    for image in lab_images(directory, problem):
        try:
            proc = subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            missing.append(image)
    return missing


def image_hint(image):
    """Cara mendapatkan image: RouterOS dibangun lokal, sisanya diunduh saat deploy."""
    if image.startswith("vrnetlab/mikrotik_routeros:"):
        return f"platform/build-routeros-image.sh {image.split(':', 1)[1]}"
    return None


def brief_parts(directory, problem):
    """Brief untuk web: bagian sebelum penanda `<!-- cli` (sisanya instruksi terminal)."""
    text = (directory / problem.get("brief", "brief.md")).read_text()
    text = text.split("<!-- cli", 1)[0].strip()
    lines = text.splitlines()
    title = problem["title"]
    if lines and lines[0].startswith("# "):
        heading = lines[0][2:]
        title = heading.split(":", 1)[1].strip() if ":" in heading else heading
        lines = lines[1:]
    return {"ticket_title": title, "markdown": "\n".join(lines).strip()}


def duration(events):
    """Detik dari event pertama sampai command/hint terakhir (shell_open/close sesudahnya diabaikan)."""
    acts = [e for e in events if e.get("type") in ("command", "hint")]
    return round(acts[-1]["ts"] - events[0]["ts"]) if acts else 0


def archived_evaluations(inst, kind="sessions"):
    results = []
    for path in sorted(archive_root(inst, kind).glob("*/evaluation.json")):
        data = json.loads(path.read_text())
        events = load_events(path.parent / "events", data["session"])
        commands = [e for e in events if e.get("type") == "command"]
        llm = data.get("llm") or {}
        entry = {
            "session": data["session"], "kind": kind,
            "date": session_start(data["session"]),
            "duration_s": duration(events), "commands": len(commands),
            "final_score": data.get("final_score"), "scores": data.get("scores"),
            "band": (llm.get("methodology") or {}).get("band"),
        }
        if kind == "golden":
            expected = path.parent / "expected.yaml"
            entry["label"] = (yaml.safe_load(expected.read_text()) or {}).get("label") if expected.exists() else None
        results.append(entry)
    return results


def lab_card(directory, user):
    problem = yaml.safe_load((directory / "problem.yaml").read_text())
    inst = instance(directory, user)
    history = archived_evaluations(inst)
    scored = [h for h in history if h["final_score"] is not None]
    best = max((h["final_score"] for h in scored), default=None)
    lab = Lab(inst)
    active = lab.session is not None and not evaluated(lab)
    checkpoints = [cp for cp in lab.checkpoints if cp["type"] != "llm_judge"]
    hits = lab.load_hits() if active else {}
    events = load_events(lab.events_dir, lab.session) if active else []
    return {
        "id": problem["id"], "title": problem["title"], "category": problem.get("category"),
        "difficulty": problem.get("difficulty"), "nos": problem.get("nos"),
        "duration_min": (problem.get("expert_baseline") or {}).get("typical_duration_min"),
        "summary": (problem.get("ui") or {}).get("summary"),
        "ticket": (problem.get("ui") or {}).get("ticket"),
        "sessions": len(history), "best_score": best,
        "active_session": lab.session if active else None,
        "active_started": events[0]["ts"] if events else None,
        "checkpoints_total": len(checkpoints),
        "checkpoints_hit": sum(1 for cp in checkpoints if cp["id"] in hits),
    }


def evaluated(lab):
    path = lab.state / "evaluation.json"
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text()).get("session") == lab.session
    except json.JSONDecodeError:
        return False


# --- runtime: checkpoint watcher per instance -------------------------------------

class Runtimes:
    """Checkpoint watcher untuk sesi aktif, satu per instance.

    Kuncinya instance (soal + user), bukan global: deploy atau pindah lab oleh
    user A tidak boleh menghentikan watcher user B. Satu user hanya punya satu
    watcher hidup (pindah lab = watcher lab lama berhenti), sama seperti dulu
    saat Runtime masih tunggal, supaya proses tidak menumpuk.
    Terminal web bukan urusan kelas ini lagi (termbridge.py, tanpa proses ttyd).
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.procs = {}  # Instance -> (session, Popen watcher)

    def ensure(self, inst, session):
        with self.lock:
            entry = self.procs.get(inst)
            if entry and entry[0] == session and entry[1].poll() is None:
                return self.status(inst)
            for other in [i for i in self.procs if i.user == inst.user]:
                self._stop_locked(other)
            # Watcher membaca session_id saat start, jadi harus diulang per sesi.
            # env instance: LAB_INSTANCE dkk., jadi watcher membaca state instance ini.
            with (inst.state_dir / "watch.log").open("a") as log_file:
                proc = subprocess.Popen(
                    [sys.executable, str(HERE / "checkpoints.py"), "watch", str(inst.problem_dir)],
                    stdout=log_file, stderr=subprocess.STDOUT, env=inst.env())
            self.procs[inst] = (session, proc)
            return self.status(inst)

    def _stop_locked(self, inst):
        _session, proc = self.procs.pop(inst, (None, None))
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    def stop(self, inst):
        with self.lock:
            self._stop_locked(inst)

    def stop_all(self):
        with self.lock:
            for inst in list(self.procs):
                self._stop_locked(inst)

    def status(self, inst):
        entry = self.procs.get(inst)
        return {"watcher": bool(entry and entry[1].poll() is None)}


RUNTIMES = Runtimes()


def running_nodes(lab, nodes):
    names = [lab.container(n) for n in nodes]
    try:
        proc = subprocess.run(["docker", "inspect", "-f", "{{.Name}} {{.State.Running}}", *names],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None  # docker tidak bisa diakses
    up = {line.split()[0].lstrip("/") for line in proc.stdout.splitlines() if line.endswith(" true")}
    return [n for n in nodes if lab.container(n) in up]


# (instance, sesi, node) -> IP management. Dibatasi: entri sesi lama untuk node
# yang sama dibuang saat sesi baru masuk, dan total entri maks. MGMT_IP_MAX (LRU),
# supaya server yang jalan berminggu-minggu tidak menumpuk entri tiap deploy.
_mgmt_ip = OrderedDict()
_mgmt_lock = threading.Lock()
MGMT_IP_MAX = 256


def _cached_ip(lab, node):
    key = (lab.instance, lab.session, node)
    with _mgmt_lock:
        if key in _mgmt_ip:
            _mgmt_ip.move_to_end(key)
            return _mgmt_ip[key]
    ip = ros.container_ip(lab.container(node))   # di luar lock: docker bisa lambat
    with _mgmt_lock:
        for old in [k for k in _mgmt_ip if k[0] == key[0] and k[2] == node and k[1] != key[1]]:
            del _mgmt_ip[old]
        _mgmt_ip[key] = ip
        while len(_mgmt_ip) > MGMT_IP_MAX:
            _mgmt_ip.popitem(last=False)
    return ip


def gui_access(lab, running):
    """Alamat Winbox router RouterOS yang sedang jalan. Perubahan dari Winbox ikut
    dinilai lewat guiwatch.py. IP management berubah tiap deploy: cache per sesi."""
    rows = []
    for node in running or []:
        if lab.kinds.get(node) != ros.ROS_KIND:
            continue
        try:
            host = _cached_ip(lab, node)
        except (ConnectionError, OSError, subprocess.TimeoutExpired):
            continue
        rows.append({"node": node, "host": host, "port": 8291,
                     "user": ros.USERNAME, "password": ros.PASSWORD})
    return rows


# --- penilaian (background) --------------------------------------------------------

class EvalJobs:
    def __init__(self):
        self.jobs = {}  # Instance -> state (per user: dua user boleh menilai soal yang sama)
        self.lock = threading.Lock()

    def get(self, inst, session):
        job = self.jobs.get(inst)
        return job if job and job["session"] == session else None

    def start(self, inst, session, use_llm, provider=None, model=None):
        with self.lock:
            job = self.get(inst, session)
            if job and job["status"] == "running":
                return job
            job = {"session": session, "status": "running", "phase": "verify", "started": time.time(),
                   "use_llm": use_llm, "error": None}
            self.jobs[inst] = job
        threading.Thread(target=self._run, args=(job, inst, use_llm, provider, model), daemon=True).start()
        return job

    def _run(self, job, inst, use_llm, provider, model):
        try:
            session = evaluate.Session(inst)  # menjalankan verify.sh
            job["phase"] = "llm" if use_llm else "rules"
            result = evaluate.evaluate(session, provider, dry_run=not use_llm, model=model)
            evaluate.write_outputs(session, result)
            job["phase"] = "archive"
            sessions.archive(inst)
            job.update(status="done", phase="done", final_score=result.get("final_score"))
        except (evaluate.EvaluatorError, LLMError, sessions.SessionError) as error:
            job.update(status="error", error=str(error))
        except Exception as error:  # noqa: BLE001 - tampilkan ke UI, jangan matikan thread diam-diam
            job.update(status="error", error=f"{type(error).__name__}: {error}")
        job["finished"] = time.time()


JOBS = EvalJobs()


# --- deploy lab (reset.sh) dari web -------------------------------------------------

def deploy_support():
    """Bisakah server menjalankan containerlab tanpa password?

    Server tidak punya terminal untuk prompt sudo, jadi hanya dua jalur:
    containerlab sudo-less (setuid + grup clab_admins, platform/setup-sudoless.sh)
    atau sudoers NOPASSWD untuk containerlab.
    """
    clab = shutil.which("containerlab")
    if not clab:
        return {"available": False, "mode": None, "reason": "containerlab tidak terinstall."}
    st = os.stat(clab)
    if st.st_mode & stat.S_ISUID and st.st_uid == 0:
        if os.access(clab, os.X_OK):
            return {"available": True, "mode": "setuid", "reason": None}
        return {"available": False, "mode": None,
                "reason": "containerlab sudah setuid, tapi proses server belum masuk grup clab_admins. "
                          "Logout lalu login lagi, kemudian restart server."}
    try:
        sudo = subprocess.run(["sudo", "-n", "-l", clab, "deploy"], capture_output=True, timeout=5)
        if sudo.returncode == 0:
            return {"available": True, "mode": "sudo", "reason": None}
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"available": False, "mode": None,
            "reason": "containerlab masih butuh password sudo. Setup sekali: sudo platform/setup-sudoless.sh"}


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
DEPLOY_STEPS = ["destroy", "deploy", "verify", "inject"]
DEPLOY_TIMEOUT = 1200   # detik; lab RouterOS butuh menit untuk boot (deploy.ready_timeout)


class DeployJobs:
    """reset.sh di background, per instance; log disimpan di memori.

    reset.sh mendapat env instance (LAB_INSTANCE, LAB_CLAB_NAME, ...), jadi yang
    di-destroy/deploy hanya lab containerlab `<nama>-<user>` milik user itu.
    Satu user hanya boleh men-deploy satu lab dalam satu waktu (busy()).
    """

    def __init__(self):
        self.jobs = {}  # Instance -> state
        self.lock = threading.Lock()

    def get(self, inst):
        job = self.jobs.get(inst)
        return {k: v for k, v in job.items() if k != "log"} if job else None

    def busy(self, user, exclude=None):
        """Ada deploy milik `user` (nama instance) yang berjalan, selain `exclude`?"""
        return any(j["status"] == "running" for i, j in self.jobs.items() if i.user == user and i != exclude)

    def running(self, inst):
        job = self.jobs.get(inst)
        return bool(job and job["status"] == "running")

    def start(self, inst, destroy_first=(), on_finish=None):
        """destroy_first: lab lain milik user yang dimatikan dulu (kapasitas: satu lab
        per user). on_finish: dipanggil di semua jalur selesai (melepas slot kapasitas)."""
        with self.lock:
            job = self.jobs.get(inst)
            if job and job["status"] == "running":
                return self.get(inst)
            job = {"status": "running", "step": None, "started": time.time(), "error": None, "log": []}
            self.jobs[inst] = job
        # env LAB_INSTANCE dkk.: reset-lab men-deploy instance ini (instance.py).
        threading.Thread(target=self._run, args=(job, inst.problem_dir, inst.env(), inst, destroy_first, on_finish),
                         daemon=True).start()
        return self.get(inst)

    def _run(self, job, directory, env=None, inst=None, destroy_first=(), on_finish=None):
        try:
            self._deploy(job, directory, env, inst, destroy_first)
        except Exception as error:  # noqa: BLE001 - mis. disk penuh saat mengarsipkan lab lama
            log.exception("Deploy gagal")
            job.update(status="error", error=f"Deploy gagal: {error}", finished=time.time())
        finally:
            if on_finish:
                on_finish()

    def _deploy(self, job, directory, env, inst, destroy_first):
        if inst is not None:
            # Watcher instance ini memegang .state/watch.log; reset.sh menghapus .state/.
            # Hanya instance ini: watcher user lain tetap jalan.
            RUNTIMES.stop(inst)
        for other in destroy_first:
            job["step"] = "destroy"
            RUNTIMES.stop(other)
            try:
                capacity.destroy(other, reason="replaced")
            except capacity.CapacityError as error:
                job.update(status="error", error=f"Lab {other.problem_dir.name} gagal dimatikan: {error}",
                           finished=time.time())
                return
        try:
            with subprocess.Popen([str(directory / "reset.sh")], cwd=directory, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  env=env, start_new_session=True) as proc:
                # Membaca stdout memblokir tanpa batas: watchdog membunuh seluruh grup proses,
                # supaya deploy macet tidak menahan slot kapasitas sampai server restart.
                timed_out = threading.Event()

                def kill_group():
                    timed_out.set()
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.killpg(proc.pid, signal.SIGKILL)

                watchdog = threading.Timer(DEPLOY_TIMEOUT, kill_group)
                watchdog.daemon = True
                watchdog.start()
                try:
                    for line in proc.stdout:
                        line = ANSI.sub("", line).rstrip()
                        if line.startswith("==> "):
                            job["step"] = line[4:].strip()
                        elif line:
                            job["log"] = (job["log"] + [line])[-30:]
                    code = proc.wait()
                finally:
                    watchdog.cancel()
        except OSError as error:
            job.update(status="error", error=str(error), finished=time.time())
            return
        if timed_out.is_set():
            job.update(status="error", error=f"Deploy dihentikan: melewati {DEPLOY_TIMEOUT // 60} menit.",
                       finished=time.time())
            return
        if code == 0:
            job.update(status="done", step="done")
        else:
            # Output inject.sh bisa menyebut lokasi fault, jadi tidak ikut ditampilkan.
            tail = [] if job["step"] == "inject" else job["log"][-6:]
            job.update(status="error", error="\n".join(tail) or f"reset.sh gagal di tahap {job['step']}")
        job["finished"] = time.time()


DEPLOYS = DeployJobs()
DEPLOY_GATE = threading.Lock()


# --- state sesi live --------------------------------------------------------------

def checkpoint_view(lab, hits, reveal):
    rows = []
    for cp in lab.checkpoints:
        hidden = cp.get("hidden") and not reveal
        hit = hits.get(cp["id"])
        row = {"id": None if hidden else cp["id"], "label": "Checkpoint tersembunyi" if hidden else cp.get("label", cp["id"]),
               "type": cp["type"], "hidden": bool(hidden),
               "status": "pending_llm" if cp["type"] == "llm_judge" else ("hit" if hit else "miss")}
        if hit:
            row["ts"] = hit["ts"]
            if not hidden:
                row["node"], row["evidence"] = hit["node"], hit["evidence"]
        rows.append(row)
    return rows


def armed(lab):
    """Sesi siap dimainkan: ada session_id dan ground truth dari inject.sh."""
    return bool(lab.session) and (lab.state / "ground_truth.json").exists()


def live_state(inst):
    lab = Lab(inst)
    problem = lab.problem
    lab_id = problem["id"]
    nodes = list(inst.topology["topology"]["nodes"])
    deploy = DEPLOYS.get(inst)
    if not armed(lab) or (deploy and deploy["status"] == "running"):
        # Selama deploy, session_id baru sudah ada tapi lab belum siap dimainkan.
        return {"lab": lab_id, "session": None, "nodes": nodes, "running": running_nodes(lab, nodes),
                "deploy": deploy}

    events = load_events(lab.events_dir, lab.session)
    timeline = build_timeline(events, NosRules(problem.get("nos", "linux-bridge"), HERE))
    commands = [e for e in timeline if e["id"].startswith("E")]
    is_done = evaluated(lab)
    used = used_levels(lab)
    hints = [{"level": h["level"], "penalty": h.get("penalty", 0), "opened": h["level"] in used,
              "text": h["text"] if h["level"] in used else None} for h in hint_list(lab)]
    job = JOBS.get(inst, lab.session)
    running = running_nodes(lab, nodes)
    return {
        "lab": lab_id, "session": lab.session, "nodes": nodes,
        "running": running,
        "gui_access": gui_access(lab, running),
        "started": events[0]["ts"] if events else None,
        "created": session_start(lab.session),
        "commands": len(commands),
        "activity": [{"id": e["id"], "node": e["node"], "command": e["command"], "ts": e["ts"],
                      "exit": e["exit"], "state_change": bool(e["state_change"]), "source": e.get("source")}
                     for e in reversed(timeline[-12:])],
        "checkpoints": checkpoint_view(lab, lab.load_hits(), reveal=is_done),
        "hints": hints,
        "evaluated": is_done,
        "job": job,
        "deploy": deploy,
    }


def state_signature(inst):
    state = inst.state_dir
    parts = []
    for path in [state / "session_id", state / "checkpoints.jsonl", state / "evaluation.json",
                 *sorted((state / "events").glob("*.jsonl"))]:
        try:
            st = path.stat()
            parts.append((path.name, st.st_size, st.st_mtime_ns))
        except FileNotFoundError:
            parts.append((path.name, None))
    return tuple(parts)


# --- mode, akun, dan login --------------------------------------------------------
#
# Mode Pribadi: tidak ada login, semua request dilayani sebagai LOCAL_USER
# (instance `local`), persis seperti sebelum ada akun.
# Mode Server: cookie `plab_session` berisi token dari AccountStore.login().
#   - HttpOnly (JS tidak bisa membaca token, XSS tidak bisa mencurinya),
#     SameSite=Lax (browser tidak mengirimnya di POST lintas situs), Secure kalau
#     request datang lewat HTTPS (langsung, atau X-Forwarded-Proto dari proxy
#     yang terdaftar di trusted_proxies).
#   - Semua /api/* butuh login kecuali PUBLIC_API; dicek di middleware, jadi
#     endpoint baru yang lupa Depends(current_user) tetap tertutup.
# Dua mode:
#   - Header Host harus nama yang diizinkan (host_ok), untuk SEMUA request HTTP
#     dan kedua WebSocket. Penangkal DNS rebinding: situs jahat mengarahkan
#     domainnya sendiri ke 127.0.0.1, lalu Origin dan Host sama-sama
#     `evil.example`, sehingga cek Origin = Host saja lolos. Pribadi: hanya
#     localhost/127.0.0.1/[::1]. Server: allowed_hosts (+ loopback).
#   - Request yang mengubah state dengan header Origin asing ditolak (CSRF; di
#     pribadi tidak ada cookie, jadi Host + Origin satu-satunya pelindung dari
#     situs lain). WebSocket juga wajib Origin = Host.

COOKIE = "plab_session"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PUBLIC_API = {"/api/auth/login", "/api/auth/logout", "/api/me"}
PURGE_INTERVAL = 15 * 60   # detik: sesi login kedaluwarsa dibersihkan dari DB
WS_RECHECK = 60            # detik: WebSocket yang terbuka memeriksa ulang login-nya
STAFF = ("guru", "admin")

# Diisi configure(); None = belum (dibaca saat pertama dipakai, lihat settings()).
AUTH = SimpleNamespace(config=None, accounts=None, capacity=None)


def local_user():
    """User semu mode Pribadi: instance `local`, admin, nama dari LAB_USER/akun OS."""
    return {"username": "local", "display_name": USER, "role": "admin"}


class LoginLimiter:
    """Batas percobaan login gagal di memori (cukup untuk satu proses server di LAN).

    Dua kunci: (IP, username) maks. PER_USER gagal per WINDOW, supaya password
    satu akun tidak bisa ditebak beruntun; dan IP saja maks. PER_IP, supaya satu
    komputer tidak bisa mencoba banyak username. Login sukses menghapus hitungan
    (IP, username)-nya. Di belakang reverse proxy semua klien tampak satu IP:
    batas per-username tetap berlaku, batas per-IP jadi batas global.
    """

    WINDOW = 5 * 60
    PER_USER = 5
    PER_IP = 30

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.fails = {}  # kunci -> deque waktu gagal

    def reset(self):
        with self.lock:
            self.fails.clear()

    def _recent(self, key, now):
        times = self.fails.get(key)
        while times and now - times[0] >= self.WINDOW:
            times.popleft()
        if times is not None and not times:
            del self.fails[key]
            return None
        return times

    def retry_after(self, ip, username):
        """Detik sampai boleh mencoba lagi (0 = boleh sekarang)."""
        now = self.clock()
        with self.lock:
            wait = 0
            for key, limit in ((("u", ip, username), self.PER_USER), (("ip", ip), self.PER_IP)):
                times = self._recent(key, now)
                if times and len(times) >= limit:
                    wait = max(wait, self.WINDOW - (now - times[0]))
            return wait

    def failed(self, ip, username):
        now = self.clock()
        with self.lock:
            if len(self.fails) > 10000:   # jaga memori: buang kunci yang sudah lewat jendela
                for key in list(self.fails):
                    self._recent(key, now)
            for key in (("u", ip, username), ("ip", ip)):
                self.fails.setdefault(key, deque()).append(now)

    def succeeded(self, ip, username):
        with self.lock:
            self.fails.pop(("u", ip, username), None)


LOGIN_LIMIT = LoginLimiter()


def configure(cfg=None, accounts=None):
    """Pasang mode server dari config (default config.load()). Dipanggil main() dan test."""
    cfg = cfg or configmod.load()
    AUTH.config = cfg
    AUTH.accounts = None
    # Kapasitas hanya di mode Server (pribadi: satu orang, satu mesin).
    AUTH.capacity = capacity.Capacity(cfg, labs_root=LABS_DIR) if cfg.is_server else None
    if cfg.is_server:
        # LAB_DB menang atas data_dir, sama seperti CLI p-lab-admin.
        AUTH.accounts = accounts or AccountStore(os.environ.get("LAB_DB") or cfg.db_path)
        if AUTH.accounts.count_admins() == 0:
            log.warning("Mode Server tanpa akun admin aktif: tidak ada yang bisa login untuk mengelola akun. "
                        "Buat dulu: platform/p-lab-admin create-user <username> --role admin")
    LOGIN_LIMIT.reset()
    return cfg


def settings():
    if AUTH.config is None:
        configure()
    return AUTH.config


def public_user(user):
    return {k: user[k] for k in ("username", "display_name", "role")} if user else None


def user_from_token(token):
    """User untuk token cookie; pribadi selalu local_user(); None = belum/tidak login."""
    if not settings().is_server:
        return local_user()
    return AUTH.accounts.user_for_token(token) if token else None


LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_warned_any_host = False


def host_name(netloc):
    """'localhost:5173' -> 'localhost', '[::1]:8000' -> '::1'; None kalau rusak."""
    netloc = (netloc or "").strip().lower()
    if netloc.startswith("["):
        name, sep, rest = netloc[1:].partition("]")
        if not sep or (rest and not (rest.startswith(":") and rest[1:].isdigit())):
            return None
        return name or None
    name, sep, port = netloc.partition(":")
    if sep and not port.isdigit():
        return None   # termasuk IPv6 tanpa kurung siku
    return name or None


def allowed_host(name):
    """Bolehkah nama host ini dipakai untuk membuka P-lab (port apa pun)?

    Port sengaja tidak dicek: Vite dev (localhost:5173) dan --port lain tetap
    jalan, dan DNS rebinding tidak bisa dicegah lewat port.
    """
    global _warned_any_host
    if not name:
        return False
    if name in LOOPBACK_HOSTS:
        return True   # pribadi: satu-satunya yang boleh; server: admin di mesin itu sendiri
    cfg = settings()
    if not cfg.is_server:
        return False
    if cfg.allowed_hosts:
        return name in cfg.allowed_hosts
    if not _warned_any_host:
        # Tanpa allowed_hosts cookie tetap terikat host (cookie milik `plab.sekolah`
        # tidak terkirim ke `evil.example`), jadi rebinding hanya mendapat 401.
        _warned_any_host = True
        log.warning("allowed_hosts kosong: semua header Host diterima. Isi allowed_hosts di %s dengan "
                    "nama/IP yang dipakai user membuka P-lab (penangkal DNS rebinding).",
                    cfg.path or "server.yaml")
    return True


def host_ok(headers):
    return allowed_host(host_name(headers.get("host")))


def origin_ok(headers):
    """Host harus diizinkan (host_ok), dan header Origin (kalau ada) harus sama
    dengan Host itu, jadi Origin juga selalu host yang diizinkan.

    Browser selalu mengirim Origin di POST lintas situs dan di WebSocket; klien
    non-browser (curl) biasanya tidak, dan mereka tetap butuh cookie login.
    Vite dev server meneruskan Host apa adanya, jadi `npm run dev` tetap lolos.
    """
    if not host_ok(headers):
        return False
    origin = headers.get("origin")
    if origin is None:
        return True
    try:
        netloc = urlsplit(origin).netloc
    except ValueError:
        return False
    return bool(netloc) and netloc.lower() == headers.get("host", "").lower()


def from_trusted_proxy(ip):
    proxies = settings().trusted_proxies
    if not proxies or not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in proxies)


def client_ip(request):
    """IP klien untuk batas login gagal.

    Tanpa trusted_proxies: alamat koneksi apa adanya (X-Forwarded-For diabaikan,
    siapa pun bisa menulisnya). Dari proxy tepercaya: X-Forwarded-For dibaca dari
    KANAN sambil melewati proxy tepercaya; alamat pertama yang tidak tepercaya
    adalah klien. Entri paling kiri tidak dipakai karena klien bisa mengisinya.
    """
    peer = request.client.host if request.client else "?"
    if not from_trusted_proxy(peer):
        return peer
    chain = [part.strip() for value in request.headers.getlist("x-forwarded-for") for part in value.split(",")]
    chain = [part for part in chain if part]
    for hop in reversed(chain):
        if not from_trusted_proxy(hop):
            return hop
    return chain[0] if chain else peer


def is_https(request):
    if request.url.scheme == "https":
        return True
    # X-Forwarded-Proto hanya dipercaya dari proxy terdaftar; kalau tidak, klien bisa
    # memaksa cookie Secure yang lalu tidak pernah terkirim lewat HTTP.
    peer = request.client.host if request.client else None
    return from_trusted_proxy(peer) and request.headers.get("x-forwarded-proto", "").lower() == "https"


def current_user(request: Request):
    """Dependency: user yang login (pribadi: local_user()); 401 kalau belum login."""
    user = getattr(request.state, "user", None)
    if user is None:   # middleware selalu mengisi untuk /api/*; jaga-jaga di luar itu
        user = user_from_token(request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "Belum login.")
    return user


def require_role(*roles):
    """Dependency: user login dengan salah satu `roles`, selain itu 403."""
    def dependency(user: dict = Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Halaman ini hanya untuk " + " / ".join(roles) + ".")
        return user
    return dependency


def ws_instance(websocket, lab_id):
    """Instance yang boleh dibuka WebSocket ini, atau None (ditolak).

    Cek Host + Origin (cegah DNS rebinding dan cross-site WebSocket hijacking:
    cookie ikut terkirim walau halaman asalnya situs lain), cek cookie login, lalu
    instance diambil dari user itu sendiri, jadi user tidak pernah bisa menunjuk
    instance orang lain.

    Token divalidasi ulang ke DB di SETIAP panggilan (tanpa cache), dan satu-
    satunya tulisan adalah last_seen sesi login. Jadi termbridge/session_ws aman
    memanggilnya berulang: logout, akun nonaktif, atau sesi kedaluwarsa = None.
    """
    if not origin_ok(websocket.headers):
        return None
    user = user_from_token(websocket.cookies.get(COOKIE))
    if user is None:
        return None
    try:
        return instance(lab_dir(lab_id), user)
    except HTTPException:
        return None


async def terminal_instance(websocket, lab_id):
    """Resolver untuk termbridge.py (akses DB akun dijalankan di thread)."""
    return await asyncio.to_thread(ws_instance, websocket, lab_id)


REAP_INTERVAL = 60
LAST_SEEN = {}          # Instance -> epoch terakhir halaman lab terbuka (WebSocket live)


def evaluating(inst):
    job = JOBS.get(inst, Lab(inst).session)
    return bool(job and job["status"] == "running")


def reap_labs_once():
    """Matikan lab milik akun nonaktif/terhapus dan lab yang menganggur (mode Server).
    Sesi yang belum dinilai diarsipkan dulu sebagai "ditinggalkan" (capacity.destroy)."""
    cap = AUTH.capacity

    def busy(inst):
        return DEPLOYS.running(inst) or evaluating(inst)

    active = {u["username"] for u in AUTH.accounts.list_users() if u["active"]}
    targets = {inst: "orphan" for inst in cap.orphan_candidates(active)}
    # Halaman lab yang masih terbuka dihitung aktivitas: membaca tiket atau berpikir
    # tidak menghasilkan event, tapi lab itu sedang dipakai.
    for inst in cap.idle_candidates(busy=busy, last_seen=LAST_SEEN.get):
        targets.setdefault(inst, "idle")
    for inst, reason in targets.items():
        # Satu instance bermasalah tidak boleh menghentikan putaran untuk instance lain.
        try:
            if busy(inst):
                continue
            RUNTIMES.stop(inst)
            capacity.destroy(inst, reason=reason)
            LAST_SEEN.pop(inst, None)
            log.info("lab %s dimatikan (%s)", inst.clab_name, reason)
        except Exception as error:  # noqa: BLE001
            log.warning("gagal mematikan lab %s: %s", inst.clab_name, error)
    return targets


async def reap_labs():
    while True:
        await asyncio.sleep(REAP_INTERVAL)
        try:
            await asyncio.to_thread(reap_labs_once)
        except Exception:  # noqa: BLE001 - jangan sampai task berhenti diam-diam
            log.exception("Reaper lab gagal")


async def purge_sessions():
    while True:
        try:
            removed = await asyncio.to_thread(AUTH.accounts.purge_expired)
            if removed:
                log.info("%d sesi login kedaluwarsa dihapus", removed)
        except Exception:  # noqa: BLE001 - jangan sampai task berhenti diam-diam
            log.exception("Gagal membersihkan sesi login kedaluwarsa")
        await asyncio.sleep(PURGE_INTERVAL)


# --- API --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app):
    tasks = [asyncio.create_task(purge_sessions()), asyncio.create_task(reap_labs())] if settings().is_server else []
    yield
    for task in tasks:
        task.cancel()
    RUNTIMES.stop_all()  # watcher ikut berhenti bersama server


app = FastAPI(title="P-lab", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    is_api = path == "/api" or path.startswith("/api/")
    if not host_ok(request.headers):
        # Semua HTTP, termasuk file SPA. SPA tidak rahasia, tapi satu aturan untuk
        # semua lebih mudah dipahami admin: alamat salah = pesan jelas di halaman,
        # bukan UI yang terbuka lalu semua panggilan API gagal.
        message = ("Alamat (header Host) ini tidak diizinkan. Buka P-lab lewat localhost, "
                   "atau tambahkan nama ini ke allowed_hosts di config server.")
        if is_api:
            return JSONResponse({"detail": message}, status_code=400)
        return PlainTextResponse(message, status_code=400)
    if request.method in UNSAFE_METHODS and not origin_ok(request.headers):
        return JSONResponse({"detail": "Permintaan lintas situs ditolak (Origin tidak cocok dengan server)."},
                            status_code=403)
    if is_api:
        if settings().is_server:
            request.state.user = await asyncio.to_thread(user_from_token, request.cookies.get(COOKIE))
        else:
            request.state.user = local_user()
        if request.state.user is None and path not in PUBLIC_API:
            return JSONResponse({"detail": "Belum login."}, status_code=401)
    return await call_next(request)


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response):
    if not settings().is_server:
        raise HTTPException(404, "Mode Pribadi tidak memakai login.")
    ip = client_ip(request)
    username = body.username.strip().lower()[:64]
    wait = LOGIN_LIMIT.retry_after(ip, username)
    if wait:
        minutes = max(1, math.ceil(wait / 60))
        raise HTTPException(429, f"Terlalu banyak percobaan login. Coba lagi dalam {minutes} menit.",
                            headers={"Retry-After": str(math.ceil(wait))})
    token = AUTH.accounts.login(username, body.password)
    if not token:
        LOGIN_LIMIT.failed(ip, username)
        raise HTTPException(401, "Username atau password salah.")
    LOGIN_LIMIT.succeeded(ip, username)
    response.set_cookie(COOKIE, token, max_age=AUTH.accounts.session_ttl, path="/",
                        httponly=True, samesite="lax", secure=is_https(request))
    return {"user": public_user(AUTH.accounts.user_for_token(token))}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    if settings().is_server:
        AUTH.accounts.logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=is_https(request))
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    cfg = settings()
    user = getattr(request.state, "user", None)
    info = {"mode": cfg.mode, "style": cfg.style, "auth": cfg.is_server, "user": public_user(user)}
    if user is None:
        # Belum login (mode Server): cukup untuk halaman login. Info LLM/deploy bukan
        # untuk orang asing, dan deploy_support() menjalankan subprocess (sudo -n -l)
        # yang tidak boleh bisa dipicu tanpa login.
        return info
    provider = os.environ.get("LAB_LLM_PROVIDER") or "anthropic"
    missing = next((m for name, _desc, m in list_providers() if name == provider), None)
    return {**info, "llm": {"provider": provider, "model": os.environ.get("LAB_LLM_MODEL"), "missing_env": missing},
            "deploy": deploy_support()}


@app.get("/api/labs")
def labs(user: dict = Depends(current_user)):
    return [lab_card(d, user) for d in all_lab_dirs()]


@app.get("/api/labs/{lab_id}")
def lab_detail(lab_id: str, user: dict = Depends(current_user)):
    directory = lab_dir(lab_id)
    problem = yaml.safe_load((directory / "problem.yaml").read_text())
    return {**lab_card(directory, user), "brief": brief_parts(directory, problem),
            "topology": topology(directory, problem),
            # Image yang harus dibangun lokal (mis. RouterOS); image biasa diunduh containerlab saat deploy.
            "missing_images": [{"image": i, "build": image_hint(i)} for i in (missing_images(directory, problem) or [])
                               if image_hint(i)],
            "weights": {**evaluate.scoring.DEFAULT_WEIGHTS, **(problem.get("scoring") or {}).get("weights", {})},
            "history": archived_evaluations(instance(directory, user))}


@app.get("/api/labs/{lab_id}/session")
def session_state(lab_id: str, user: dict = Depends(current_user)):
    return live_state(instance(lab_dir(lab_id), user))


@app.post("/api/labs/{lab_id}/runtime")
def runtime(lab_id: str, user: dict = Depends(current_user)):
    lab = user_lab(lab_id, user)
    if not lab.session:
        raise HTTPException(409, "Belum ada sesi. Jalankan ./reset.sh dulu.")
    return RUNTIMES.ensure(lab.instance, lab.session)


class HintRequest(BaseModel):
    level: int | None = None


@app.post("/api/labs/{lab_id}/hint")
def hint(lab_id: str, body: HintRequest, user: dict = Depends(current_user)):
    lab = user_lab(lab_id, user)
    if evaluated(lab):
        raise HTTPException(409, "Sesi ini sudah dinilai.")
    try:
        opened, new = open_hint(lab, body.level)
    except HintError as error:
        raise HTTPException(409, str(error))
    return {"level": opened["level"], "text": opened["text"], "penalty": opened.get("penalty", 0), "new": new}


@app.post("/api/labs/{lab_id}/start")
def start(lab_id: str, user: dict = Depends(current_user)):
    lab = user_lab(lab_id, user)
    if DEPLOYS.busy(lab.instance.user):
        raise HTTPException(409, "Lab sedang di-deploy.")
    if armed(lab) and not evaluated(lab):
        return {"session": lab.session, "new": False}
    try:
        session = sessions.rearm(lab.instance)
    except sessions.SessionError as error:
        raise HTTPException(409, str(error))
    RUNTIMES.ensure(lab.instance, session)
    return {"session": session, "new": True}


@app.post("/api/labs/{lab_id}/deploy")
def deploy(lab_id: str, user: dict = Depends(current_user)):
    directory = lab_dir(lab_id)
    if not (directory / "reset.sh").exists():
        raise HTTPException(409, "Soal ini tidak punya reset.sh.")
    support = deploy_support()
    if not support["available"]:
        raise HTTPException(409, support["reason"])
    problem = yaml.safe_load((directory / "problem.yaml").read_text())
    unbuilt = [i for i in (missing_images(directory, problem) or []) if image_hint(i)]
    if unbuilt:
        raise HTTPException(409, f"Image {', '.join(unbuilt)} belum dibangun. Jalankan: {image_hint(unbuilt[0])}")
    inst = instance(directory, user)
    if DEPLOYS.busy(inst.user, exclude=inst):
        raise HTTPException(409, "Lab lain sedang di-deploy.")
    job = JOBS.get(inst, Lab(inst).session)
    if job and job["status"] == "running":
        raise HTTPException(409, "Sesi sedang dinilai.")
    if AUTH.capacity is None:
        return DEPLOYS.start(inst)
    # Mode Server. Cek + reservasi + start satu langkah: request ganda (klik dua kali, dua
    # tab) tidak boleh membuat dua reservasi untuk satu instance.
    with DEPLOY_GATE:
        if DEPLOYS.running(inst):
            return DEPLOYS.get(inst)
        decision = AUTH.capacity.try_acquire(inst.user, inst)
        if not decision:
            raise HTTPException(409 if decision.code == "busy" else 503, decision.reason)
        # Lab yang akan dimatikan sedang dinilai: membunuhnya menghilangkan skor (biaya LLM sudah terpakai).
        if any(evaluating(other) for other in decision.destroy):
            AUTH.capacity.release_deploy(inst)
            raise HTTPException(409, "Lab kamu yang lain sedang dinilai. Tunggu sampai selesai, lalu deploy lagi.")
        return DEPLOYS.start(inst, destroy_first=decision.destroy,
                             on_finish=lambda: AUTH.capacity.release_deploy(inst))


class EvaluateRequest(BaseModel):
    use_llm: bool = True
    provider: str | None = None
    model: str | None = None


@app.post("/api/labs/{lab_id}/evaluate")
def evaluate_session(lab_id: str, body: EvaluateRequest, user: dict = Depends(current_user)):
    lab = user_lab(lab_id, user)
    if not armed(lab):
        raise HTTPException(409, "Tidak ada sesi aktif.")
    provider, model = body.provider, body.model
    if settings().is_server and user["role"] != "admin":
        # Provider/model menentukan API key siapa yang terpakai (biaya) dan ke mana
        # transcript siswa dikirim: keputusan pemilik server (admin), bukan siswa
        # atau guru. Yang lain memakai default server (LAB_LLM_PROVIDER/MODEL).
        provider = model = None
    return JOBS.start(lab.instance, lab.session, body.use_llm, provider, model)


SESSION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def find_session_dir(inst, session, golden=True):
    # Nama sesi masuk ke path: tolak `..` dan sejenisnya supaya tidak keluar dari arsip instance.
    # golden=False: golden/ milik soal (jawaban expert) tidak ikut dicari.
    if SESSION_NAME.fullmatch(session or ""):
        for kind in ("sessions", "golden") if golden else ("sessions",):
            path = archive_root(inst, kind) / session
            if (path / "evaluation.json").exists():
                return kind, path
    raise HTTPException(404, f"Sesi {session} belum dinilai")


@app.get("/api/labs/{lab_id}/sessions/{session}")
def session_result(lab_id: str, session: str, user: dict = Depends(current_user)):
    inst = instance(lab_dir(lab_id), user)
    # Golden transcript = jawaban lengkap soal. Pribadi: milik pemain itu sendiri.
    # Server: hanya guru/admin; siswa mendapat 404 yang sama dengan sesi yang tidak
    # ada (tidak membocorkan bahwa golden itu ada).
    kind, path = find_session_dir(inst, session, golden=not settings().is_server or user["role"] in STAFF)
    if kind == "sessions":
        inst.ensure_marker()   # evaluate.Session mencari pemilik arsip lewat instance.json
    result = json.loads((path / "evaluation.json").read_text())
    try:
        archived = evaluate.Session(path, live_verify=False)
    except evaluate.EvaluatorError as error:
        raise HTTPException(500, str(error))
    timeline = [{k: e.get(k) for k in ("id", "t", "node", "command", "exit", "source", "state_change", "rework",
                                       "hint_level", "output")} for e in archived.timeline]
    labels = {cp["id"]: cp.get("label", cp["id"]) for cp in archived.lab.checkpoints}
    result.pop("llm_runs", None)
    events = archived.events
    expected = path / "expected.yaml"
    return {"kind": kind, "result": result, "timeline": timeline, "checkpoint_labels": labels,
            "title": archived.problem["title"], "date": session_start(session),
            "duration_s": duration(events),
            "label": (yaml.safe_load(expected.read_text()) or {}).get("label") if expected.exists() else None}


def user_sessions(username):
    """Semua sesi yang sudah dinilai milik instance `username`, terbaru dulu."""
    rows = []
    for directory in all_lab_dirs():
        inst = Instance(directory, username)
        for entry in archived_evaluations(inst):
            rows.append({**entry, "lab": inst.problem["id"], "title": inst.problem["title"]})
    rows.sort(key=lambda r: r["date"] or 0, reverse=True)
    return rows


@app.get("/api/progress")
def progress(user: dict = Depends(current_user)):
    rows = user_sessions(user["username"])
    return {"sessions": rows, "points": points(rows)}


def points(rows):
    """Points = jumlah skor akhir terbaik per lab (mengulang lab tidak menambah poin)."""
    best = {}
    for row in rows:
        if row["final_score"] is not None:
            best[row["lab"]] = max(best.get(row["lab"], 0), row["final_score"])
    return round(sum(best.values()))


def board_stats(rows):
    scored = [r for r in rows if r["final_score"] is not None]
    methodology = [r["scores"]["methodology"] for r in scored if (r["scores"] or {}).get("methodology") is not None]
    return {"points": points(rows), "labs": len({r["lab"] for r in scored}),
            "methodology_avg": round(sum(methodology) / len(methodology)) if methodology else None}


def ranked(entries):
    entries.sort(key=lambda e: e["points"], reverse=True)
    for rank, entry in enumerate(entries, 1):
        entry["rank"] = rank
    return entries


@app.get("/api/leaderboard")
def leaderboard(user: dict = Depends(current_user)):
    """Pribadi: kamu vs golden transcript tiap soal. Server: antar-user.

    Gaya `mandiri`: semua user aktif, nama terlihat. Gaya `kelas`: hanya siswa
    yang diperingkat; siswa melihat poin teman sekelas tanpa nama (anonim),
    guru/admin melihat semua nama.
    """
    cfg = settings()
    if not cfg.is_server:
        return golden_leaderboard(user)
    kelas = cfg.style == "kelas"
    show_names = not kelas or user["role"] in STAFF
    entries = []
    accounts = AUTH.accounts.list_users()
    if not show_names:
        # Urutan list_users = urutan username: kalau dipakai untuk poin yang seri,
        # posisi baris anonim membocorkan siapa dia. Acak per request (sort stabil).
        random.shuffle(accounts)
    for account in accounts:
        if not account["active"] or (kelas and account["role"] != "siswa"):
            continue
        you = account["username"] == user["username"]
        entry = {**board_stats(user_sessions(account["username"])), "you": you}
        if you or show_names:
            entry.update(name=account["display_name"], username=account["username"])
        else:
            entry.update(name="Siswa lain", anonymous=True)
        entries.append(entry)
    return ranked(entries)


def golden_leaderboard(user):
    """Single-user lokal: kamu dibandingkan dengan golden transcript tiap soal."""
    entries = [{"name": user["display_name"], "you": True, **board_stats(user_sessions(user["username"]))}]
    for directory in all_lab_dirs():
        inst = instance(directory, user)
        for golden in archived_evaluations(inst, "golden"):
            if golden["final_score"] is None:
                continue
            entries.append({"name": golden["label"] or golden["session"], "you": False, "golden": True,
                            "lab": inst.problem["id"], "session": golden["session"],
                            "points": round(golden["final_score"]), "labs": 1,
                            "methodology_avg": (golden["scores"] or {}).get("methodology")})
    return ranked(entries)


@app.get("/api/class/progress")
def class_progress(_user: dict = Depends(require_role(*STAFF))):
    """Ringkasan kelas untuk guru/admin (mode Server, gaya kelas): sesi dan skor terbaik per lab tiap user."""
    cfg = settings()
    if not (cfg.is_server and cfg.style == "kelas"):
        raise HTTPException(404, "Ringkasan kelas hanya ada di mode Server dengan gaya kelas.")
    labs_meta = []
    for directory in all_lab_dirs():
        problem = yaml.safe_load((directory / "problem.yaml").read_text())
        labs_meta.append({"id": problem["id"], "title": problem["title"]})
    users = []
    for account in AUTH.accounts.list_users():
        if not account["active"]:
            continue
        rows = user_sessions(account["username"])
        best = {}
        for row in rows:
            if row["final_score"] is not None:
                best[row["lab"]] = max(best.get(row["lab"], 0), row["final_score"])
        users.append({**public_user(account), "sessions": len(rows), "points": points(rows),
                      "best_scores": best, "last_session": rows[0]["date"] if rows else None})
    return {"labs": labs_meta, "users": users}


@app.websocket("/api/labs/{lab_id}/ws")
async def session_ws(websocket: WebSocket, lab_id: str):
    # Ditolak sebelum accept() = handshake gagal (HTTP 403), tanpa membocorkan alasannya.
    inst = await asyncio.to_thread(ws_instance, websocket, lab_id)
    if inst is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    token = websocket.cookies.get(COOKIE)
    last_sig, last_job, checked = None, None, time.monotonic()

    async def until_disconnect():
        # Klien tidak mengirim apa pun, jadi putusnya hanya terlihat dengan menunggu pesan.
        # Tanpa ini task polling hidup terus (sampai state berubah) dan menahan shutdown.
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass

    gone = asyncio.create_task(until_disconnect())
    try:
        while not gone.done():
            LAST_SEEN[inst] = time.time()
            if settings().is_server and time.monotonic() - checked > WS_RECHECK:
                # Logout/akun dinonaktifkan/sesi kedaluwarsa juga memutus WebSocket yang sudah terbuka.
                checked = time.monotonic()
                if await asyncio.to_thread(user_from_token, token) is None:
                    await websocket.close(code=4401)
                    return
            sig = state_signature(inst)
            lab_session = inst.state_dir / "session_id"
            session = lab_session.read_text().strip() if lab_session.exists() else None
            job = [JOBS.get(inst, session), DEPLOYS.get(inst)]
            job_sig = json.dumps(job, sort_keys=True, default=str)
            if sig != last_sig or job_sig != last_job:
                last_sig, last_job = sig, job_sig
                state = await asyncio.to_thread(live_state, inst)
                await websocket.send_json(state)
            await asyncio.wait({gone}, timeout=0.5)
    except (WebSocketDisconnect, RuntimeError):
        pass   # RuntimeError: send setelah klien putus
    finally:
        gone.cancel()


# --- terminal web (termbridge.py) --------------------------------------------------
# Dibuat terpisah; kalau belum ada, server tetap jalan tanpa terminal web.

try:
    import termbridge  # noqa: E402
except ImportError as error:
    termbridge = None
    log.warning("Terminal web nonaktif: platform/termbridge.py tidak bisa dimuat (%s).", error)
else:
    termbridge.set_resolver(terminal_instance)
    app.include_router(termbridge.router)


# --- file statis (hasil `npm run build` di web/) ------------------------------------

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        file = WEB_DIST / path
        if path and file.is_file() and WEB_DIST in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(WEB_DIST / "index.html")


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description="Web UI P-lab")
    parser.add_argument("--host", help="default: dari config (pribadi 127.0.0.1)")
    parser.add_argument("--port", type=int, help="default: dari config (8000)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="p-lab: %(levelname)s %(message)s")
    try:
        cfg = configure()   # config rusak = berhenti di sini dengan daftar masalahnya
    except configmod.ConfigError as error:
        sys.exit(str(error))
    if not WEB_DIST.exists():
        print("web/dist belum ada: jalankan `npm install && npm run build` di web/ "
              "(atau `npm run dev` untuk mode pengembangan).", file=sys.stderr)
    log.info("mode %s%s", cfg.mode, f" (gaya {cfg.style}, data {cfg.data_dir})" if cfg.is_server else "")
    # proxy_headers=False: bawaan uvicorn mempercayai X-Forwarded-* dari 127.0.0.1;
    # di sini hanya trusted_proxies (client_ip, is_https) yang menentukan.
    uvicorn.run(app, host=args.host or cfg.host, port=args.port or cfg.port, log_level="warning",
                proxy_headers=False)


if __name__ == "__main__":
    main()
