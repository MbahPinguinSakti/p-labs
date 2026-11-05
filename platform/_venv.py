"""Jalankan ulang script CLI dengan Python dari .venv project.

Script di platform/ memakai `#!/usr/bin/env python3`, yaitu Python sistem yang
belum tentu punya PyYAML/FastAPI. Kalau .venv ada dan script dipanggil dengan
Python lain, proses diganti (exec) dengan Python venv. Saat diimpor sebagai
modul (oleh server atau test) tidak terjadi apa-apa, karena pemanggilnya
hanya di bawah `if __name__ == "__main__"`.
"""

import os
import sys
from pathlib import Path

VENV = Path(__file__).resolve().parent.parent / ".venv"


def ensure():
    python = VENV / "bin" / "python"
    if python.exists() and Path(sys.prefix).resolve() != VENV.resolve():
        os.execv(str(python), [str(python), sys.argv[0], *sys.argv[1:]])
