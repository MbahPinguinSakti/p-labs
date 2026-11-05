"""Siklus hidup sesi: mulai ulang tanpa sudo (rearm) dan arsip sesi selesai.

  .state/                    sesi yang sedang berjalan (satu per soal)
  sessions/<session_id>/     arsip sesi yang sudah dinilai (salinan .state/)
  golden/<session_id>/       golden transcript (arsip + notes.md + expected.yaml)

Dipakai autoplay.py dan web UI (server.py).
"""

import json
import shutil
import subprocess
import time
from pathlib import Path


class SessionError(Exception):
    pass


def verify(problem_dir):
    proc = subprocess.run([str(Path(problem_dir) / "verify.sh")], capture_output=True, text=True)
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise SessionError(f"verify.sh tidak mengeluarkan JSON: {proc.stdout}{proc.stderr}")


def rearm(problem_dir):
    """Sesi baru di lab yang sudah berjalan: kosongkan .state/, lalu inject ulang.

    Pengganti reset.sh tanpa sudo. Butuh lab sehat (verify correctness 100),
    karena inject.sh hanya menghapus VLAN; sisa kerusakan sesi lama (mis.
    vlan_filtering 0) tidak dibersihkan, jadi kasus itu tetap perlu reset.sh.
    """
    problem_dir = Path(problem_dir)
    result = verify(problem_dir)
    if result.get("correctness") != 100:
        raise SessionError("Lab belum sehat (correctness "
                           f"{result.get('correctness')}), jadi tidak bisa dimulai ulang tanpa deploy. "
                           "Jalankan ./reset.sh.")
    state = problem_dir / ".state"
    # events/ di-bind-mount ke container: kalau direktorinya dihapus lalu dibuat
    # ulang, container tetap menulis ke inode lama yang sudah terhapus. Jadi
    # events/ hanya dikosongkan; sisanya boleh dihapus.
    events = state / "events"
    for child in state.iterdir() if state.exists() else []:
        if child == events:
            for item in events.iterdir():
                item.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    events.mkdir(parents=True, exist_ok=True)
    (state / "tty").mkdir(exist_ok=True)
    proc = subprocess.run([str(problem_dir / "inject.sh")], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SessionError(f"inject.sh gagal: {proc.stderr or proc.stdout}")
    if not (state / "ground_truth.json").exists():
        raise SessionError("inject.sh tidak menulis .state/ground_truth.json.")
    # Ditulis terakhir (sama seperti reset-lab): session_id = sesi siap dimainkan.
    session = time.strftime("%Y%m%d-%H%M%S")
    (state / "session_id").write_text(session + "\n")
    return session


def archive(problem_dir, dest_root="sessions"):
    """Salin .state/ ke <dest_root>/<session_id>/ (ditimpa kalau sudah ada)."""
    state = Path(problem_dir) / ".state"
    session = (state / "session_id").read_text().strip()
    dest = Path(problem_dir) / dest_root / session
    shutil.copytree(state, dest, ignore=shutil.ignore_patterns("watch.log"), dirs_exist_ok=True)
    return dest
