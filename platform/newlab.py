#!/usr/bin/env python3
"""Buat lab baru dari template.

  newlab.py <id> [--title "Judul soal"] [--template DIR]

Template default (platform/templates/lab) adalah soal kecil yang langsung bisa
dimainkan: dua host + satu Linux bridge, dengan fault "port dilepas dari bridge".
Ubah file-filenya menjadi skenariomu sendiri (panduan: docs/membuat-lab.md).

Di dalam template, __ID__, __TITLE__, dan __CLAB_NAME__ diganti. {{nama}}
dibiarkan apa adanya, karena itu placeholder parameter soal yang diisi saat sesi.
"""

if __name__ == "__main__":
    import _venv  # noqa: E402  (Python venv, lihat _venv.py)
    _venv.ensure()

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TEMPLATE = HERE / "templates" / "lab"
SCRIPTS = {"inject.sh", "verify.sh", "reset.sh"}


def existing_ids(labs_dir):
    ids = {}
    for path in labs_dir.glob("*/problem.yaml"):
        problem = yaml.safe_load(path.read_text()) or {}
        ids[problem.get("id")] = path.parent
    return ids


def create(lab_id, title, labs_dir, template=TEMPLATE):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", lab_id):
        raise ValueError("id hanya boleh huruf kecil, angka, dan '-' (contoh: net-002)")
    dest = labs_dir / lab_id
    if dest.exists():
        raise ValueError(f"{dest} sudah ada")
    if lab_id in existing_ids(labs_dir):
        raise ValueError(f"id {lab_id} sudah dipakai oleh {existing_ids(labs_dir)[lab_id]}")
    # Nama topologi containerlab: container jadi clab-<nama>-<node>.
    clab_name = re.sub(r"[^a-z0-9]", "", lab_id)
    values = {"__ID__": lab_id, "__TITLE__": title.replace('"', "'"), "__CLAB_NAME__": clab_name}

    shutil.copytree(template, dest)
    for path in dest.rglob("*"):
        if path.is_file():
            text = path.read_text()
            for key, value in values.items():
                text = text.replace(key, value)
            path.write_text(text)
            if path.name in SCRIPTS:
                path.chmod(0o755)
    return dest


def main():
    parser = argparse.ArgumentParser(description="Buat lab baru dari template")
    parser.add_argument("id", help="id soal, mis. net-002")
    parser.add_argument("--title", default="Lab baru", help="judul soal")
    parser.add_argument("--template", type=Path, default=TEMPLATE)
    parser.add_argument("--labs-dir", type=Path, default=ROOT / "labs")
    args = parser.parse_args()
    try:
        dest = create(args.id, args.title, args.labs_dir, args.template)
    except ValueError as error:
        sys.exit(f"Gagal: {error}")
    rel = dest.relative_to(ROOT) if dest.is_relative_to(ROOT) else dest
    print(f"Lab dibuat di {rel}/")
    print("Langkah berikutnya:")
    print(f"  1. Ubah topologi, brief.md, inject.sh, verify.sh, dan problem.yaml di {rel}/")
    print(f"  2. platform/lab-lint {rel}")
    print(f"  3. {rel}/reset.sh, lalu buka http://localhost:8000/labs/{args.id}")
    print("Panduan: docs/membuat-lab.md")


if __name__ == "__main__":
    main()
