"""API admin: kelola akun mode Server (daftar, buat, import CSV, ubah, reset password).

Tidak ada endpoint hapus akun (sengaja): akun dinonaktifkan saja, supaya riwayat
dan nilainya tetap ada. Password acak hanya dikembalikan sekali di respons dan
tidak pernah ditulis ke log.
"""

import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import accounts
from accounts import AccountError
from dashboard import H, require_admin

log = logging.getLogger("p-lab.admin_accounts")
router = APIRouter()

MAX_CSV_BYTES = 256 * 1024


class CreateBody(BaseModel):
    username: str
    display_name: Optional[str] = None
    role: str = "siswa"
    password: Optional[str] = None


class ImportBody(BaseModel):
    csv: str
    default_role: str = "siswa"


class PatchBody(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None


class PasswordBody(BaseModel):
    password: Optional[str] = None


def admin_user(row, seen):
    """Bentuk AdminUser untuk frontend (tanpa id dan pw_hash)."""
    return {"username": row["username"], "display_name": row["display_name"], "role": row["role"],
            "active": row["active"], "created_at": row["created_at"],
            "last_seen": seen.get(row["username"])}


def existing_user(username):
    """Baris user, atau 404 (juga untuk username yang bentuknya tidak valid)."""
    try:
        accounts.validate_username(username)
    except AccountError:
        raise HTTPException(404, "Akun tidak ditemukan.")
    row = H.accounts().get_user(username)
    if not row:
        raise HTTPException(404, "Akun tidak ditemukan.")
    return row


def bad_request(error):
    return HTTPException(400, str(error))


def stop_user_labs(username):
    """Matikan semua lab milik user: (dimatikan, dilewati), berisi id soal.

    Yang sibuk (deploy/dinilai/sedang dimatikan) atau gagal dilewati; reaper mematikannya
    nanti karena akunnya sudah nonaktif.
    """
    stopped, skipped = [], []
    try:
        instances = [i for i in H.capacity().existing() if i.user == username]
    except Exception as error:   # docker tidak terjangkau: akun tetap nonaktif
        log.warning("Tidak bisa mendaftar lab milik %s: %s", username, error)
        return stopped, skipped
    for inst in instances:
        lab_id = inst.problem.get("id", inst.problem_dir.name)
        try:
            H.stop_lab(inst, "orphan")
            stopped.append(lab_id)
        except HTTPException as error:
            skipped.append(lab_id)
            log.warning("Lab %s milik %s dilewati: %s", lab_id, username, error.detail)
        except Exception as error:
            skipped.append(lab_id)
            log.warning("Lab %s milik %s gagal dimatikan: %s", lab_id, username, error)
    return stopped, skipped


def normalize_csv(text):
    """Teks CSV dari textarea: buang BOM, dan ubah pemisah `;` (Excel locale Indonesia) ke `,`."""
    text = text.lstrip("\ufeff")
    header = text.split("\n", 1)[0]
    if ";" in header and "," not in header:
        out = io.StringIO()
        csv.writer(out).writerows(csv.reader(io.StringIO(text), delimiter=";"))
        text = out.getvalue()
    return text


@router.get("/api/admin/users")
def list_users(user: dict = Depends(require_admin)):
    seen = H.accounts().last_seen_map()
    return {"users": [admin_user(r, seen) for r in H.accounts().list_users()]}


@router.post("/api/admin/users", status_code=201)
def create_user(body: CreateBody, user: dict = Depends(require_admin)):
    store = H.accounts()
    generated = None
    password = body.password
    try:
        accounts.validate_username(body.username)
        accounts.validate_role(body.role)
        if password:
            accounts.check_password_policy(password)
    except AccountError as error:
        raise bad_request(error)
    if store.get_user(body.username):
        raise HTTPException(409, f"Username '{body.username}' sudah dipakai.")
    if not password:
        password = generated = accounts.random_password()
    try:
        row = store.create_user(body.username, password, body.role, body.display_name)
    except AccountError as error:   # balapan dua request: dipakai di antara cek dan insert
        if store.get_user(body.username):
            raise HTTPException(409, f"Username '{body.username}' sudah dipakai.")
        raise bad_request(error)
    return {"user": admin_user(row, {}), "password": generated}


@router.post("/api/admin/users/import")
def import_users(body: ImportBody, user: dict = Depends(require_admin)):
    if len(body.csv.encode()) > MAX_CSV_BYTES:
        raise HTTPException(413, f"CSV terlalu besar (maksimal {MAX_CSV_BYTES // 1024} KB).")
    try:
        accounts.validate_role(body.default_role)
        result = H.accounts().import_csv(io.StringIO(normalize_csv(body.csv)), body.default_role)
    except AccountError as error:
        raise bad_request(error)
    return {"created": [{"username": u, "password": p} for u, p in result.created],
            "errors": [{"line": line, "message": message} for line, message in result.errors]}


@router.patch("/api/admin/users/{username}")
def update_user(username: str, body: PatchBody, user: dict = Depends(require_admin)):
    store = H.accounts()
    row = existing_user(username)
    is_self = username == user["username"]
    if is_self and body.role is not None and body.role != row["role"]:
        raise HTTPException(409, "Kamu tidak bisa mengubah role akunmu sendiri.")
    if is_self and body.active is False:
        raise HTTPException(409, "Kamu tidak bisa menonaktifkan akunmu sendiri.")
    try:
        if body.role is not None:
            accounts.validate_role(body.role)
        if body.display_name is not None:
            if not body.display_name.strip():
                raise AccountError("Nama tampilan wajib diisi.")
            accounts.validate_display_name(body.display_name.strip())
    except AccountError as error:
        raise bad_request(error)
    stopped, skipped = [], []
    try:
        # Urutan: yang bisa ditolak aturan admin terakhir dulu, nama paling akhir.
        if body.role is not None and body.role != row["role"]:
            store.set_role(username, body.role)
        if body.active is not None and body.active != row["active"]:
            store.set_active(username, body.active)
            if not body.active:
                stopped, skipped = stop_user_labs(username)
    except AccountError as error:
        # Validasi sudah di atas; yang tersisa di sini aturan admin aktif terakhir.
        raise HTTPException(409, str(error))
    if body.display_name is not None:
        try:
            store.set_display_name(username, body.display_name)
        except AccountError as error:
            raise bad_request(error)
    return {"user": admin_user(store.get_user(username), store.last_seen_map()),
            "stopped_labs": stopped, "skipped_labs": skipped}


@router.post("/api/admin/users/{username}/password")
def reset_password(username: str, body: PasswordBody, user: dict = Depends(require_admin)):
    existing_user(username)
    if username == user["username"]:
        # set_password menghapus semua sesi login, termasuk sesi admin ini: password acak
        # yang baru tidak sempat terlihat dan satu-satunya admin terkunci dari web.
        raise HTTPException(409, "Password akunmu sendiri diganti lewat CLI: "
                                 "sudo platform/p-lab-admin reset-password " + username)
    password = body.password
    generated = None
    try:
        if password:
            accounts.check_password_policy(password)
        else:
            password = generated = accounts.random_password()
        H.accounts().set_password(username, password)
    except AccountError as error:
        raise bad_request(error)
    return {"password": generated}
