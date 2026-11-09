"""Penghubung router dashboard (admin_accounts.py, admin_labs.py, class_api.py) ke server.py.

Router dashboard tidak meng-import server.py. Kalau server dijalankan langsung
(`python server.py`), modulnya bernama __main__; `import server` dari modul lain
akan memuat salinan kedua dengan AUTH, DEPLOYS, dan RUNTIMES sendiri (kosong).
Jadi server.py memanggil bind(...) sekali saat start, dan router memakai H.*:

  H.settings()                  config.Config aktif (is_server, style, capacity)
  H.current_user(request)       dict user login (401 kalau belum)
  H.accounts()                  accounts.AccountStore
  H.capacity()                  capacity.Capacity
  H.all_lab_dirs()              [Path] direktori soal
  H.lab_dir(lab_id)             Path direktori soal (HTTPException 404 kalau tidak ada)
  H.user_sessions(username)     sesi bernilai milik user, terbaru dulu (bentuk /api/progress)
  H.points(rows)                poin dari hasil user_sessions
  H.session_payload(inst, session, golden)  isi /api/labs/{id}/sessions/{s} untuk instance mana pun
  H.lab_busy(inst)              None | "deploy" | "evaluate"
  H.deploy_job(inst)            status deploy (dict DeployJob) atau None
  H.deploy_queue()              antrian deploy FIFO: [{"instance", "position", "reason", "queued_at"}]
                                urut posisi (reason: "busy" | "memory"); [] kalau kosong
  H.last_seen(inst)             epoch halaman lab terakhir terbuka (WebSocket) atau None
  H.stop_lab(inst, reason)      matikan satu lab (arsip sesi belum dinilai); 409 kalau sibuk.
                                Mengembalikan session_id yang diarsipkan atau None.
  H.public_user(user)           {username, display_name, role}

Dependency di bawah sudah memeriksa mode Server (404 di mode Pribadi) dan role.
"""

from types import SimpleNamespace

from fastapi import HTTPException, Request

H = SimpleNamespace(bound=False)


def bind(**hooks):
    """Dipanggil server.py. Test boleh memanggil ulang dengan sebagian hook palsu."""
    H.__dict__.update(hooks)
    H.bound = True


def require(*roles, kelas_only=False):
    """Dependency: user login dengan salah satu `roles`, di mode Server.

    Mode Pribadi tidak punya akun lain, jadi dashboard = 404 (bukan 403).
    kelas_only: halaman guru, hanya ada di gaya `kelas`.
    """
    def dependency(request: Request):
        cfg = H.settings()
        user = H.current_user(request)
        if not cfg.is_server:
            raise HTTPException(404, "Dashboard hanya ada di mode Server.")
        if kelas_only and cfg.style != "kelas":
            raise HTTPException(404, "Halaman kelas hanya ada di mode Server dengan gaya kelas.")
        if user["role"] not in roles:
            raise HTTPException(403, "Halaman ini hanya untuk " + " / ".join(roles) + ".")
        return user
    return dependency


require_admin = require("admin")
require_staff = require("guru", "admin", kelas_only=True)
