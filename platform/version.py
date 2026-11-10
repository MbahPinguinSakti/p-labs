"""Versi P-lab yang sedang jalan: nomor dari file VERSION + commit git.

Nomor (`0.3.0`) naik saat rilis ke main; commit menunjukkan kode persisnya, karena
dua mesin bisa sama-sama "0.3.0" tapi berbeda beberapa commit. Dipakai log start
server, /api/me, dan `install.sh --check`.

Commit dibaca langsung dari .git (tanpa program git): di mode Server proses jalan
sebagai `plab`, sedangkan repo milik admin, dan git menolak repo milik user lain
("dubious ownership"). Hanya status "ada perubahan lokal" yang butuh program git;
kalau git tidak bisa, status itu None (tidak diketahui), bukan error.

CLI: python platform/version.py  ->  0.3.0 (f75e43c, feat/mode-server)
"""

import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git_dir(root):
    git = root / ".git"
    if git.is_file():   # worktree / submodule: "gitdir: <path>"
        text = git.read_text().strip()
        if text.startswith("gitdir:"):
            target = Path(text.split(":", 1)[1].strip())
            return target if target.is_absolute() else (root / target).resolve()
    return git if git.is_dir() else None


def _ref_commit(git, ref):
    loose = git / ref
    if loose.is_file():
        return loose.read_text().strip()
    # Ref yang sudah di-pack (git gc) ada di packed-refs; worktree: lihat commondir.
    common = git
    if (git / "commondir").is_file():
        common = (git / (git / "commondir").read_text().strip()).resolve()
        if (common / ref).is_file():
            return (common / ref).read_text().strip()
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    return None


def git_info(root=ROOT):
    """(commit 7 karakter | None, branch | None). Tidak pernah melempar exception."""
    try:
        git = _git_dir(root)
        if git is None:
            return None, None
        head = (git / "HEAD").read_text().strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            commit = _ref_commit(git, ref)
            branch = ref.removeprefix("refs/heads/")
        else:   # detached HEAD, mis. `git checkout v0.3.0`
            commit, branch = head, None
        return (commit[:7] if commit else None), branch
    except (OSError, UnicodeDecodeError):
        return None, None


def git_dirty(root=ROOT):
    """True/False = ada/tidak ada file terlacak yang diubah; None = tidak bisa dicek."""
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={root}", "-C", str(root), "status", "--porcelain",
             "--untracked-files=no"],
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def number(root=ROOT):
    try:
        return (root / "VERSION").read_text().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


@lru_cache(maxsize=1)
def info():
    """Dihitung sekali per proses: yang dilaporkan adalah kode yang dimuat saat start."""
    commit, branch = git_info()
    return {"version": number(), "commit": commit, "branch": branch, "dirty": git_dirty()}


def describe(data=None):
    """'0.3.0 (f75e43c, feat/mode-server, ada perubahan lokal)'."""
    data = data or info()
    extra = [x for x in (data["commit"], data["branch"]) if x]
    if data["dirty"]:
        extra.append("ada perubahan lokal")
    return data["version"] + (f" ({', '.join(extra)})" if extra else "")


if __name__ == "__main__":
    print(describe())
