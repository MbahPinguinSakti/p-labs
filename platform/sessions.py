"""Siklus hidup sesi: mulai ulang tanpa sudo (rearm) dan arsip sesi selesai.

Per instance (instance.py; local = layout lama di labs/<id>/):
  .state/                    sesi yang sedang berjalan (satu per instance)
  sessions/<session_id>/     arsip sesi yang sudah dinilai (salinan .state/)
Per soal:
  golden/<session_id>/       golden transcript (arsip + notes.md + expected.yaml)

Fungsi di sini menerima Instance, atau direktori soal (instance dari LAB_INSTANCE).
Dipakai autoplay.py dan web UI (server.py).
"""

import json
import shutil
import subprocess
import time

from instance import Instance


class SessionError(Exception):
    pass


def run_script(inst, name):
    """Jalankan script soal dengan env instance (kontrak labenv.sh)."""
    return subprocess.run([str(inst.problem_dir / name)], capture_output=True, text=True, env=inst.env())


def verify(problem_dir):
    inst = Instance.coerce(problem_dir)
    proc = run_script(inst, "verify.sh")
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
    inst = Instance.coerce(problem_dir)
    result = verify(inst)
    if result.get("correctness") != 100:
        raise SessionError("Lab belum sehat (correctness "
                           f"{result.get('correctness')}), jadi tidak bisa dimulai ulang tanpa deploy. "
                           "Jalankan ./reset.sh.")
    state = inst.state_dir
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
    proc = run_script(inst, "inject.sh")
    if proc.returncode != 0:
        raise SessionError(f"inject.sh gagal: {proc.stderr or proc.stdout}")
    if not (state / "ground_truth.json").exists():
        raise SessionError("inject.sh tidak menulis .state/ground_truth.json.")
    # Ditulis terakhir (sama seperti reset-lab): session_id = sesi siap dimainkan.
    session = time.strftime("%Y%m%d-%H%M%S")
    (state / "session_id").write_text(session + "\n")
    return session


def archive(problem_dir, dest_root=None):
    """Salin .state/ instance ke <dest_root>/<session_id>/ (ditimpa kalau sudah ada).

    dest_root default sessions/ instance; path relatif (mis. "golden") dihitung
    dari direktori soal, karena golden milik soal, bukan instance.
    """
    inst = Instance.coerce(problem_dir)
    state = inst.state_dir
    session = (state / "session_id").read_text().strip()
    root = inst.sessions_dir if dest_root is None else inst.problem_dir / dest_root
    dest = root / session
    shutil.copytree(state, dest, ignore=shutil.ignore_patterns("watch.log"), dirs_exist_ok=True)
    return dest
