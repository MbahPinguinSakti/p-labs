"""API admin: lab yang sedang berjalan di mode Server (lihat, matikan)."""

import time

from fastapi import APIRouter, Depends, HTTPException

import accounts
from dashboard import H, require_admin
from instance import LOCAL, Instance, InstanceError

router = APIRouter()

LOCAL_NAME = "local (terminal server)"


def _docker_error(error):
    return HTTPException(503, f"Docker tidak bisa dibaca: {error}")


def _session(inst):
    try:
        return (inst.state_dir / "session_id").read_text().strip() or None
    except OSError:
        return None


def _display_name(username, users):
    if username == LOCAL:
        return LOCAL_NAME
    user = users.get(username)
    return (user.get("display_name") if user else None) or username


def _lab(inst, running, deploying, users, now):
    import capacity
    cap = H.capacity()
    job = H.deploy_job(inst)
    job_running = bool(job and job.get("status") == "running")
    if inst in deploying or job_running:
        state = "deploying"
    elif inst in running:
        state = "running"
    else:
        state = "stopped"
    try:
        activity = capacity.last_activity(inst)
    except OSError:   # .state/ dihapus reset.sh di tengah pembacaan (deploy berjalan)
        activity = None
    seen = [t for t in (activity, H.last_seen(inst)) if t is not None]
    last = max(seen) if seen else None
    return {
        "lab_id": (inst.problem or {}).get("id") or inst.problem_dir.name,
        "title": (inst.problem or {}).get("title") or inst.problem_dir.name,
        "username": inst.user,
        "display_name": _display_name(inst.user, users),
        "clab_name": inst.clab_name,
        "mem_mb": cap.estimate(inst),
        "state": state,
        "deploy_step": (job or {}).get("step") if state == "deploying" else None,
        "session": _session(inst),
        "last_activity": last,
        "idle_s": round(now - last) if last is not None else None,
        "busy": H.lab_busy(inst),
    }


@router.get("/api/admin/labs")
def list_labs(user: dict = Depends(require_admin)):
    cap = H.capacity()
    try:
        running = cap.running()       # docker dibaca sekali per request
        existing = cap.existing()
    except OSError as error:
        raise _docker_error(error)
    with cap.cond:
        deploying = dict(cap.deploying)
    insts = sorted(existing | set(deploying), key=lambda i: (i.user, i.problem_dir.name))
    users = {u["username"]: u for u in H.accounts().list_users()}
    now = time.time()
    labs = [_lab(i, running, deploying, users, now) for i in insts]
    used = sum(cap.estimate(i) for i in running | set(deploying))
    queue = [{"username": row["instance"].user,
              "display_name": _display_name(row["instance"].user, users),
              "lab_id": (row["instance"].problem or {}).get("id") or row["instance"].problem_dir.name,
              "title": (row["instance"].problem or {}).get("title") or row["instance"].problem_dir.name,
              "position": row["position"], "reason": row["reason"], "queued_at": row["queued_at"]}
             for row in getattr(H, "deploy_queue", lambda: [])()]
    return {
        "queue": queue,
        "capacity": {"used_mb": used, "limit_mb": cap.cap.mem_mb, "deploying": len(deploying),
                     "max_deploys": cap.cap.max_deploys, "idle_minutes": cap.cap.idle_minutes},
        "labs": labs,
    }


@router.post("/api/admin/labs/{username}/{lab_id}/stop")
def stop_lab(username: str, lab_id: str, user: dict = Depends(require_admin)):
    if username != LOCAL:
        try:
            accounts.validate_username(username)
        except accounts.AccountError:
            raise HTTPException(404, "Lab tidak ditemukan.")
    problem_dir = H.lab_dir(lab_id)    # 404 kalau soal tidak ada
    try:
        inst = Instance(problem_dir, username)
    except InstanceError:
        raise HTTPException(404, "Lab tidak ditemukan.")
    try:
        existing = H.capacity().existing()
    except OSError as error:
        raise _docker_error(error)
    if inst not in existing:
        raise HTTPException(404, "Lab tidak berjalan.")
    archived = H.stop_lab(inst, "manual")
    return {"ok": True, "archived": archived}
