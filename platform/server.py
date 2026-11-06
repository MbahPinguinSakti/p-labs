#!/usr/bin/env python3
"""Web UI P-lab (Fase 3): API + WebSocket + file statis hasil build web/.

  python3 platform/server.py [--port 8000] [--host 127.0.0.1]
  lalu buka http://localhost:8000

Satu service lokal, single-user. Server ini:
  - membaca katalog soal dari labs/*/problem.yaml,
  - menjalankan ttyd (terminal per node) dan checkpoint watcher untuk sesi aktif,
  - mendorong state sesi (checkpoint, aktivitas, hint) lewat WebSocket,
  - membuka hint (hints.py), memulai sesi baru (sessions.rearm), dan menilai
    sesi (evaluate.py) lalu mengarsipkannya ke labs/<id>/sessions/<sesi>/.

Yang dikirim ke browser sengaja dibatasi: ground truth, parameter soal, definisi
checkpoint, dan teks hint yang belum dibuka tidak pernah keluar dari server.
"""

import argparse
import asyncio
import getpass
import json
import os
import shutil
import re
import socket
import stat
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import evaluate  # noqa: E402
import ros  # noqa: E402
import sessions  # noqa: E402
from checkpoints import Lab  # noqa: E402
from hints import HintError, hint_list, open_hint, used_levels  # noqa: E402
from llm import LLMError, list_providers  # noqa: E402
from transcript import NosRules, build_timeline, load_events  # noqa: E402

LABS_DIR = Path(os.environ.get("LAB_LABS_DIR", ROOT / "labs"))
WEB_DIST = ROOT / "web" / "dist"
TTYD_PORT = int(os.environ.get("LAB_TTYD_PORT", 7681))
USER = os.environ.get("LAB_USER") or getpass.getuser()

# Tema xterm.js di ttyd, mengikuti design tokens (web/src/styles/tokens.css).
TTYD_THEME = {
    "background": "#0B0E0C", "foreground": "#ECF3EE", "cursor": "#5FF0B0",
    "cursorAccent": "#04120C", "selectionBackground": "#1D5A41",
    "green": "#5FF0B0", "brightGreen": "#5FF0B0", "yellow": "#F0BD4F", "red": "#FF7B47",
}


# --- katalog soal -----------------------------------------------------------------

def lab_dir(lab_id):
    for path in sorted(LABS_DIR.glob("*/problem.yaml")):
        problem = yaml.safe_load(path.read_text())
        if problem.get("id") == lab_id:
            return path.parent
    raise HTTPException(404, f"Lab {lab_id} tidak ada")


def all_lab_dirs():
    return [path.parent for path in sorted(LABS_DIR.glob("*/problem.yaml"))]


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


def archived_evaluations(directory, kind="sessions"):
    results = []
    for path in sorted((directory / kind).glob("*/evaluation.json")):
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


def lab_card(directory):
    problem = yaml.safe_load((directory / "problem.yaml").read_text())
    history = archived_evaluations(directory)
    scored = [h for h in history if h["final_score"] is not None]
    best = max((h["final_score"] for h in scored), default=None)
    lab = Lab(directory)
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


# --- runtime: ttyd + watcher per sesi -------------------------------------------

def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def lab_ttyd_on(port, directory):
    """Apakah proses di port ini ttyd milik P-lab untuk lab ini (mis. dari `platform/serve`)?

    Port yang terbuka saja tidak cukup: paket ttyd di Debian/Ubuntu memasang
    service systemd `ttyd` yang menjalankan `login` (read-only) di port 7681,
    yaitu port default kita. Kalau dipakai, pemain melihat `login:` dan tidak
    bisa mengetik. Jadi ttyd luar hanya dipakai kalau command line-nya
    menjalankan lab-shell untuk direktori lab yang sama.
    """
    target = str(Path(directory).resolve())
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in argv if a]
        if (args and Path(args[0]).name == "ttyd" and "-p" in args[:-1]
                and args[args.index("-p") + 1] == str(port)
                and any(Path(a).name == "lab-shell" for a in args)
                and any(a == target or (a.startswith("/") and Path(a).resolve() == Path(target)) for a in args)):
            return True
    return False


def free_port(start, tries=50):
    for port in range(start, start + tries):
        if not port_open(port):
            return port
    raise RuntimeError(f"tidak ada port kosong untuk ttyd di {start}-{start + tries - 1}")


class Runtime:
    """ttyd + checkpoint watcher untuk sesi aktif. Satu soal aktif dalam satu waktu."""

    def __init__(self):
        self.lock = threading.Lock()
        self.lab_dir = None
        self.session = None
        self.ttyd = None
        self.watcher = None
        self.external_ttyd = False
        self.port = TTYD_PORT

    def ensure(self, directory, session):
        with self.lock:
            if self.lab_dir == directory and self.session == session and self._alive():
                return self.status()
            self._stop_locked()
            self.lab_dir, self.session = directory, session
            # Watcher membaca session_id saat start, jadi harus diulang per sesi.
            log = (directory / ".state" / "watch.log").open("a")
            self.watcher = subprocess.Popen(
                [sys.executable, str(HERE / "checkpoints.py"), "watch", str(directory)],
                stdout=log, stderr=subprocess.STDOUT)
            # ttyd dari `platform/serve` untuk lab yang sama boleh dipakai ulang.
            # Proses lain di port default (mis. service ttyd bawaan distro): cari port lain.
            self.external_ttyd = port_open(TTYD_PORT) and lab_ttyd_on(TTYD_PORT, directory)
            if self.external_ttyd:
                self.port = TTYD_PORT
            elif shutil.which("ttyd"):
                self.port = free_port(TTYD_PORT)
                self.ttyd = subprocess.Popen(
                    ["ttyd", "-W", "-a", "-i", "lo", "-p", str(self.port),
                     "-t", "titleFixed=P-lab", "-t", "disableLeaveAlert=true",
                     "-t", "fontSize=13", "-t", "fontFamily=JetBrains Mono, ui-monospace, monospace",
                     "-t", "theme=" + json.dumps(TTYD_THEME),
                     str(HERE / "lab-shell"), str(directory)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Tunggu sebentar sampai ttyd listen, supaya iframe tidak memuat port kosong.
                for _ in range(20):
                    if port_open(self.port) or self.ttyd.poll() is not None:
                        break
                    time.sleep(0.1)
            return self.status()

    def _alive(self):
        watcher_ok = self.watcher is not None and self.watcher.poll() is None
        ttyd_ok = self.external_ttyd or (self.ttyd is not None and self.ttyd.poll() is None)
        return watcher_ok and ttyd_ok

    def _stop_locked(self):
        for proc in (self.watcher, self.ttyd):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self.watcher = self.ttyd = None
        self.lab_dir = self.session = None
        self.external_ttyd = False

    def stop(self):
        with self.lock:
            self._stop_locked()

    def status(self):
        return {"ttyd_port": self.port, "ttyd": self.external_ttyd or bool(self.ttyd and self.ttyd.poll() is None),
                "ttyd_available": bool(shutil.which("ttyd")) or self.external_ttyd,
                "watcher": bool(self.watcher and self.watcher.poll() is None)}


RUNTIME = Runtime()


def running_nodes(lab, nodes):
    names = [lab.container(n) for n in nodes]
    try:
        proc = subprocess.run(["docker", "inspect", "-f", "{{.Name}} {{.State.Running}}", *names],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None  # docker tidak bisa diakses
    up = {line.split()[0].lstrip("/") for line in proc.stdout.splitlines() if line.endswith(" true")}
    return [n for n in nodes if lab.container(n) in up]


_mgmt_ip = {}


def gui_access(lab, running):
    """Alamat Winbox router RouterOS yang sedang jalan. Perubahan dari Winbox ikut
    dinilai lewat guiwatch.py. IP management berubah tiap deploy: cache per sesi."""
    rows = []
    for node in running or []:
        if lab.kinds.get(node) != ros.ROS_KIND:
            continue
        key = (lab.session, node)
        if key not in _mgmt_ip:
            try:
                _mgmt_ip[key] = ros.container_ip(lab.container(node))
            except (ConnectionError, OSError, subprocess.TimeoutExpired):
                continue
        rows.append({"node": node, "host": _mgmt_ip[key], "port": 8291,
                     "user": ros.USERNAME, "password": ros.PASSWORD})
    return rows


# --- penilaian (background) --------------------------------------------------------

class EvalJobs:
    def __init__(self):
        self.jobs = {}  # lab_id -> state
        self.lock = threading.Lock()

    def get(self, lab_id, session):
        job = self.jobs.get(lab_id)
        return job if job and job["session"] == session else None

    def start(self, lab_id, directory, session, use_llm, provider=None, model=None):
        with self.lock:
            job = self.get(lab_id, session)
            if job and job["status"] == "running":
                return job
            job = {"session": session, "status": "running", "phase": "verify", "started": time.time(),
                   "use_llm": use_llm, "error": None}
            self.jobs[lab_id] = job
        threading.Thread(target=self._run, args=(job, directory, use_llm, provider, model), daemon=True).start()
        return job

    def _run(self, job, directory, use_llm, provider, model):
        try:
            session = evaluate.Session(directory)  # menjalankan verify.sh
            job["phase"] = "llm" if use_llm else "rules"
            result = evaluate.evaluate(session, provider, dry_run=not use_llm, model=model)
            evaluate.write_outputs(session, result)
            job["phase"] = "archive"
            sessions.archive(directory)
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


class DeployJobs:
    """reset.sh di background. Satu deploy per soal; log disimpan di memori."""

    def __init__(self):
        self.jobs = {}  # lab_id -> state
        self.lock = threading.Lock()

    def get(self, lab_id):
        job = self.jobs.get(lab_id)
        return {k: v for k, v in job.items() if k != "log"} if job else None

    def busy(self, exclude=None):
        return any(j["status"] == "running" for lid, j in self.jobs.items() if lid != exclude)

    def start(self, lab_id, directory):
        with self.lock:
            job = self.jobs.get(lab_id)
            if job and job["status"] == "running":
                return self.get(lab_id)
            job = {"status": "running", "step": None, "started": time.time(), "error": None, "log": []}
            self.jobs[lab_id] = job
        threading.Thread(target=self._run, args=(job, directory), daemon=True).start()
        return self.get(lab_id)

    def _run(self, job, directory):
        RUNTIME.stop()  # watcher memegang .state/watch.log; reset.sh menghapus .state/
        try:
            with subprocess.Popen([str(directory / "reset.sh")], cwd=directory, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
                for line in proc.stdout:
                    line = ANSI.sub("", line).rstrip()
                    if line.startswith("==> "):
                        job["step"] = line[4:].strip()
                    elif line:
                        job["log"] = (job["log"] + [line])[-30:]
                code = proc.wait(timeout=600)
        except (OSError, subprocess.TimeoutExpired) as error:
            job.update(status="error", error=str(error), finished=time.time())
            return
        if code == 0:
            job.update(status="done", step="done")
        else:
            # Output inject.sh bisa menyebut lokasi fault, jadi tidak ikut ditampilkan.
            tail = [] if job["step"] == "inject" else job["log"][-6:]
            job.update(status="error", error="\n".join(tail) or f"reset.sh gagal di tahap {job['step']}")
        job["finished"] = time.time()


DEPLOYS = DeployJobs()


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


def live_state(lab_id):
    directory = lab_dir(lab_id)
    lab = Lab(directory)
    problem = lab.problem
    nodes = list(yaml.safe_load((directory / problem["lab_topology"]).read_text())["topology"]["nodes"])
    deploy = DEPLOYS.get(lab_id)
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
    job = JOBS.get(lab_id, lab.session)
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


def state_signature(directory):
    state = directory / ".state"
    parts = []
    for path in [state / "session_id", state / "checkpoints.jsonl", state / "evaluation.json",
                 *sorted((state / "events").glob("*.jsonl"))]:
        try:
            st = path.stat()
            parts.append((path.name, st.st_size, st.st_mtime_ns))
        except FileNotFoundError:
            parts.append((path.name, None))
    return tuple(parts)


# --- API --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app):
    yield
    RUNTIME.stop()  # ttyd + watcher ikut berhenti bersama server


app = FastAPI(title="P-lab", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


@app.get("/api/me")
def me():
    provider = os.environ.get("LAB_LLM_PROVIDER") or "anthropic"
    missing = next((m for name, _desc, m in list_providers() if name == provider), None)
    return {"user": USER, "llm": {"provider": provider, "model": os.environ.get("LAB_LLM_MODEL"),
                                  "missing_env": missing},
            "deploy": deploy_support()}


@app.get("/api/labs")
def labs():
    return [lab_card(d) for d in all_lab_dirs()]


@app.get("/api/labs/{lab_id}")
def lab_detail(lab_id: str):
    directory = lab_dir(lab_id)
    problem = yaml.safe_load((directory / "problem.yaml").read_text())
    return {**lab_card(directory), "brief": brief_parts(directory, problem),
            "topology": topology(directory, problem),
            # Image yang harus dibangun lokal (mis. RouterOS); image biasa diunduh containerlab saat deploy.
            "missing_images": [{"image": i, "build": image_hint(i)} for i in (missing_images(directory, problem) or [])
                               if image_hint(i)],
            "weights": {**evaluate.scoring.DEFAULT_WEIGHTS, **(problem.get("scoring") or {}).get("weights", {})},
            "history": archived_evaluations(directory)}


@app.get("/api/labs/{lab_id}/session")
def session_state(lab_id: str):
    return live_state(lab_id)


@app.post("/api/labs/{lab_id}/runtime")
def runtime(lab_id: str):
    directory = lab_dir(lab_id)
    lab = Lab(directory)
    if not lab.session:
        raise HTTPException(409, "Belum ada sesi. Jalankan ./reset.sh dulu.")
    return RUNTIME.ensure(directory, lab.session)


class HintRequest(BaseModel):
    level: int | None = None


@app.post("/api/labs/{lab_id}/hint")
def hint(lab_id: str, body: HintRequest):
    lab = Lab(lab_dir(lab_id))
    if evaluated(lab):
        raise HTTPException(409, "Sesi ini sudah dinilai.")
    try:
        opened, new = open_hint(lab, body.level)
    except HintError as error:
        raise HTTPException(409, str(error))
    return {"level": opened["level"], "text": opened["text"], "penalty": opened.get("penalty", 0), "new": new}


@app.post("/api/labs/{lab_id}/start")
def start(lab_id: str):
    directory = lab_dir(lab_id)
    lab = Lab(directory)
    if DEPLOYS.busy():
        raise HTTPException(409, "Lab sedang di-deploy.")
    if armed(lab) and not evaluated(lab):
        return {"session": lab.session, "new": False}
    try:
        session = sessions.rearm(directory)
    except sessions.SessionError as error:
        raise HTTPException(409, str(error))
    RUNTIME.ensure(directory, session)
    return {"session": session, "new": True}


@app.post("/api/labs/{lab_id}/deploy")
def deploy(lab_id: str):
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
    if DEPLOYS.busy(exclude=lab_id):
        raise HTTPException(409, "Lab lain sedang di-deploy.")
    job = JOBS.get(lab_id, Lab(directory).session)
    if job and job["status"] == "running":
        raise HTTPException(409, "Sesi sedang dinilai.")
    return DEPLOYS.start(lab_id, directory)


class EvaluateRequest(BaseModel):
    use_llm: bool = True
    provider: str | None = None
    model: str | None = None


@app.post("/api/labs/{lab_id}/evaluate")
def evaluate_session(lab_id: str, body: EvaluateRequest):
    directory = lab_dir(lab_id)
    lab = Lab(directory)
    if not armed(lab):
        raise HTTPException(409, "Tidak ada sesi aktif.")
    return JOBS.start(lab_id, directory, lab.session, body.use_llm, body.provider, body.model)


def find_session_dir(directory, session):
    for kind in ("sessions", "golden"):
        path = directory / kind / session
        if (path / "evaluation.json").exists():
            return kind, path
    raise HTTPException(404, f"Sesi {session} belum dinilai")


@app.get("/api/labs/{lab_id}/sessions/{session}")
def session_result(lab_id: str, session: str):
    directory = lab_dir(lab_id)
    kind, path = find_session_dir(directory, session)
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


@app.get("/api/progress")
def progress():
    rows = []
    for directory in all_lab_dirs():
        problem = yaml.safe_load((directory / "problem.yaml").read_text())
        for entry in archived_evaluations(directory):
            rows.append({**entry, "lab": problem["id"], "title": problem["title"]})
    rows.sort(key=lambda r: r["date"] or 0, reverse=True)
    return {"sessions": rows, "points": points(rows)}


def points(rows):
    """Points = jumlah skor akhir terbaik per lab (mengulang lab tidak menambah poin)."""
    best = {}
    for row in rows:
        if row["final_score"] is not None:
            best[row["lab"]] = max(best.get(row["lab"], 0), row["final_score"])
    return round(sum(best.values()))


@app.get("/api/leaderboard")
def leaderboard():
    """Single-user lokal: kamu dibandingkan dengan golden transcript tiap soal."""
    entries = []
    mine = progress()["sessions"]
    scored = [r for r in mine if r["final_score"] is not None]
    methodology = [r["scores"]["methodology"] for r in scored if r["scores"].get("methodology") is not None]
    entries.append({"name": USER, "you": True, "points": points(mine), "labs": len({r["lab"] for r in scored}),
                    "methodology_avg": round(sum(methodology) / len(methodology)) if methodology else None})
    for directory in all_lab_dirs():
        problem = yaml.safe_load((directory / "problem.yaml").read_text())
        for golden in archived_evaluations(directory, "golden"):
            if golden["final_score"] is None:
                continue
            entries.append({"name": golden["label"] or golden["session"], "you": False, "golden": True,
                            "lab": problem["id"], "session": golden["session"],
                            "points": round(golden["final_score"]), "labs": 1,
                            "methodology_avg": (golden["scores"] or {}).get("methodology")})
    entries.sort(key=lambda e: e["points"], reverse=True)
    for rank, entry in enumerate(entries, 1):
        entry["rank"] = rank
    return entries


@app.websocket("/api/labs/{lab_id}/ws")
async def session_ws(websocket: WebSocket, lab_id: str):
    await websocket.accept()
    try:
        directory = lab_dir(lab_id)
    except HTTPException:
        await websocket.close(code=4404)
        return
    last_sig, last_job = None, None
    try:
        while True:
            sig = state_signature(directory)
            lab_session = (directory / ".state" / "session_id")
            session = lab_session.read_text().strip() if lab_session.exists() else None
            job = [JOBS.get(lab_id, session), DEPLOYS.get(lab_id)]
            job_sig = json.dumps(job, sort_keys=True, default=str)
            if sig != last_sig or job_sig != last_job:
                last_sig, last_job = sig, job_sig
                state = await asyncio.to_thread(live_state, lab_id)
                await websocket.send_json(state)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass


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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not WEB_DIST.exists():
        print("web/dist belum ada: jalankan `npm install && npm run build` di web/ "
              "(atau `npm run dev` untuk mode pengembangan).", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
