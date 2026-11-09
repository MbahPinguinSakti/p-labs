"""Halaman guru (gaya kelas, mode Server): progres siswa, detail, laporan sesi, export CSV.

Semua endpoint hanya untuk guru dan admin (require_staff): di mode Pribadi dan
gaya mandiri 404, tanpa login 401, role siswa 403. Yang dihitung dan boleh dibuka
hanya akun role siswa yang aktif.
"""

import csv
import io

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from accounts import AccountError, validate_username
from dashboard import H, require_staff
from instance import Instance, InstanceError

router = APIRouter()

NOT_FOUND = "Siswa tidak ditemukan."
CSV_INJECTION = ("=", "+", "-", "@", "\t", "\r")   # sel teks yang diawali ini bisa dijalankan Excel/Calc


def _siswa(username):
    """Akun siswa aktif `username`. Username tidak valid, bukan siswa, atau nonaktif = 404."""
    try:
        validate_username(username)
    except AccountError:
        raise HTTPException(404, NOT_FOUND)
    user = H.accounts().get_user(username)
    if not user or user["role"] != "siswa" or not user["active"]:
        raise HTTPException(404, NOT_FOUND)
    return user


def _students():
    return [s for s in H.accounts().list_users(role="siswa") if s["active"]]


def _labs():
    labs = []
    for directory in H.all_lab_dirs():
        problem = yaml.safe_load((directory / "problem.yaml").read_text())
        labs.append({"id": problem["id"], "title": problem["title"]})
    return labs


def _stats(student, rows):
    """Ringkasan satu siswa dari `rows` (hasil H.user_sessions, terbaru dulu)."""
    best, attempts = {}, {}
    for row in rows:
        lab = row["lab"]
        attempts[lab] = attempts.get(lab, 0) + 1
        score = row["final_score"]
        if score is not None and (lab not in best or score > best[lab]):
            best[lab] = score
    dates = [row["date"] for row in rows if row["date"] is not None]
    return {
        "username": student["username"], "display_name": student["display_name"],
        "points": H.points(rows), "sessions": len(rows),
        "best_scores": best, "attempts": attempts,
        "last_session": max(dates) if dates else None,
    }


@router.get("/api/class/progress")
def class_progress(user: dict = Depends(require_staff)):
    students = [_stats(s, H.user_sessions(s["username"])) for s in _students()]
    return {"labs": _labs(), "students": students}


@router.get("/api/class/students/{username}")
def class_student(username: str, user: dict = Depends(require_staff)):
    student = _siswa(username)
    rows = H.user_sessions(student["username"])
    return {"student": H.public_user(student), "points": H.points(rows), "sessions": rows}


@router.get("/api/class/students/{username}/labs/{lab_id}/sessions/{session}")
def class_session(username: str, lab_id: str, session: str, user: dict = Depends(require_staff)):
    student = _siswa(username)
    try:
        inst = Instance(H.lab_dir(lab_id), student["username"])
    except InstanceError as error:
        raise HTTPException(404, str(error))
    # golden=False: jawaban expert (golden/) tidak pernah lewat endpoint ini.
    return H.session_payload(inst, session, golden=False)


def _cell(value):
    if isinstance(value, str) and value.startswith(CSV_INJECTION):
        return "'" + value
    return value


@router.get("/api/class/export.csv")
def class_export(user: dict = Depends(require_staff)):
    lab_ids = [lab["id"] for lab in _labs()]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([_cell(c) for c in ("username", "nama", "poin", "sesi", *lab_ids)])
    for student in _students():
        stats = _stats(student, H.user_sessions(student["username"]))
        scores = [round(stats["best_scores"][lab]) if lab in stats["best_scores"] else None for lab in lab_ids]
        writer.writerow([_cell(v) for v in (stats["username"], stats["display_name"], stats["points"],
                                            stats["sessions"], *scores)])
    # BOM: Excel di Windows baru membaca UTF-8 (nama dengan huruf non-ASCII) kalau ada BOM.
    return Response(content="\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="nilai-kelas.csv"'})
