#!/usr/bin/env python3
"""Mainkan sesi pemain secara otomatis lewat lab-shell sungguhan.

Dipakai untuk membuat golden transcript yang bisa diulang (mis. "expert",
"nyontek"). Semua jalur perekaman asli dipakai: lab-shell (rekaman `script`
+ timing), hook bash di node (events JSONL), dan watcher checkpoint
(`checkpoints.py watch`, termasuk state_check live). Bedanya dengan pemain
manusia hanya: command diketik oleh skrip ini.

Usage:
  autoplay.py <problem_dir> <skenario.yaml> [--rearm] [--capture] [--speed F]

  --rearm    Sebelum main: lab harus sehat (verify.sh correctness 100), lalu
             .state/ dibuat ulang dan fault di-inject (inject.sh). Pengganti
             reset.sh tanpa sudo, untuk sesi kedua dst. setelah lab diperbaiki.
  --capture  Setelah main: simpan verify.json, salin .state/ ke
             golden/<session_id>/, dan tulis notes.md dari skenario.
  --speed F  Kalikan semua jeda "think" dengan F (mis. 0.5 = 2x lebih cepat).

Format skenario (YAML):
  label: "..."             # deskripsi singkat, masuk notes.md
  notes: |                  # label manusia untuk evaluator (notes.md)
    ...
  steps:
    - {node: host-a, cmd: "ping -c 2 10.20.0.2", think: 20}
    - {hint: 1, think: 30}     # buka hint lewat platform/lab-hint
  think = jeda (detik) SEBELUM mengetik command, meniru waktu berpikir.

  --capture-only  Lewati permainan, langsung simpan sesi yang ada ke golden/
                  (mis. setelah `evaluate.py run .` dijalankan di sesi live).

Butuh akses docker (jalankan di dalam `newgrp docker` kalau perlu).
"""

if __name__ == "__main__":
    import _venv  # noqa: E402  (Python venv, lihat _venv.py)
    _venv.ensure()

import argparse
import fcntl
import json
import os
import re
import signal
import struct
import subprocess
import sys
import termios
import threading
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sessions  # noqa: E402

HERE = Path(__file__).resolve().parent
TYPE_DELAY = 0.04       # detik per karakter saat "mengetik"
PROMPT_TIMEOUT = 60     # detik menunggu prompt kembali setelah satu command


class Shell:
    """Satu lab-shell di dalam pseudo-terminal, seperti satu tab ttyd."""

    def __init__(self, problem_dir, node):
        self.node = node
        self.buf = b""
        self.lock = threading.Lock()
        master, slave = os.openpty()
        # Ukuran terminal tetap supaya rekaman tty konsisten antar-run.
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 140, 0, 0))
        self.proc = subprocess.Popen(
            [str(HERE / "lab-shell"), str(problem_dir), node],
            stdin=slave, stdout=slave, stderr=slave, start_new_session=True, close_fds=True)
        os.close(slave)
        self.master = master
        # PS1 dari lab-rc.sh: \e[1;32m<node>\e[0m:<cwd>#, atau prompt ros.py shell: [admin@<node>] /menu>
        self.prompt = re.compile(re.escape(f"{node}\x1b[0m:").encode() + rb"[^\n]*# |"
                                 + re.escape(f"@{node}] ").encode() + rb"[^\n>]*> ")
        threading.Thread(target=self._reader, daemon=True).start()
        self.wait_prompt(0)

    def _reader(self):
        while True:
            try:
                data = os.read(self.master, 4096)
            except OSError:
                return
            if not data:
                return
            with self.lock:
                self.buf += data

    def prompts(self):
        with self.lock:
            return len(self.prompt.findall(self.buf))

    def wait_prompt(self, seen):
        """Tunggu sampai jumlah prompt > seen (command sebelumnya selesai)."""
        deadline = time.monotonic() + PROMPT_TIMEOUT
        while time.monotonic() < deadline:
            if self.prompts() > seen:
                return
            if self.proc.poll() is not None:
                raise RuntimeError(f"lab-shell {self.node} berhenti:\n{self.buf[-500:].decode(errors='replace')}")
            time.sleep(0.05)
        raise RuntimeError(f"{self.node}: prompt tidak kembali dalam {PROMPT_TIMEOUT}s:\n"
                           f"{self.buf[-500:].decode(errors='replace')}")

    def type(self, cmd):
        seen = self.prompts()
        for ch in cmd:
            os.write(self.master, ch.encode())
            time.sleep(TYPE_DELAY)
        os.write(self.master, b"\r")
        self.wait_prompt(seen)

    def close(self):
        try:
            os.write(self.master, b"exit\r")
            self.proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
        os.close(self.master)


def rearm(problem_dir):
    try:
        sessions.rearm(problem_dir)
    except sessions.SessionError as error:
        sys.exit(f"--rearm: {error}")


def capture(problem_dir, scenario, scenario_file):
    state = problem_dir / ".state"
    session = (state / "session_id").read_text().strip()
    (state / "verify.json").write_text(json.dumps(sessions.verify(problem_dir)) + "\n")
    dest = sessions.archive(problem_dir, "golden")
    notes = (f"# Golden transcript: {session}\n\n"
             f"**Tipe:** {scenario.get('label', '')}\n"
             f"**Sumber:** sesi otomatis (`platform/autoplay.py`, skenario `{scenario_file.name}`), "
             "bukan playtest manusia. Command dan jeda berpikir ditulis tangan; "
             "rekaman, events, dan checkpoint asli dari lab.\n\n"
             + scenario.get("notes", ""))
    (dest / "notes.md").write_text(notes)
    return dest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("problem_dir", type=Path)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--rearm", action="store_true")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--capture-only", action="store_true")
    args = parser.parse_args()
    problem_dir = args.problem_dir.resolve()
    scenario = yaml.safe_load(args.scenario.read_text())

    if args.capture_only:
        print(f"golden: {capture(problem_dir, scenario, args.scenario)}")
        return
    if args.rearm:
        rearm(problem_dir)
    session = (problem_dir / ".state" / "session_id").read_text().strip()
    total = sum(step.get("think", 0) for step in scenario["steps"]) * args.speed
    print(f"autoplay {args.scenario.name}: sesi {session}, {len(scenario['steps'])} command, "
          f"±{total / 60:.1f} menit jeda berpikir", flush=True)

    # Watcher checkpoint, sama seperti yang dijalankan platform/serve.
    watch_log = (problem_dir / ".state" / "watch.log").open("a")
    watcher = subprocess.Popen([sys.executable, str(HERE / "checkpoints.py"), "watch", str(problem_dir)],
                               stdout=watch_log, stderr=subprocess.STDOUT, start_new_session=True)
    shells = {}
    try:
        time.sleep(1)
        for i, step in enumerate(scenario["steps"], 1):
            time.sleep(step.get("think", 0) * args.speed)
            if "hint" in step:
                out = subprocess.run([str(HERE / "lab-hint"), str(problem_dir), str(step["hint"])],
                                     capture_output=True, text=True, check=True).stdout.strip()
                print(f"  [{i:>2}/{len(scenario['steps'])}] {time.strftime('%H:%M:%S')} hint   {out.splitlines()[0]}", flush=True)
                continue
            node = step["node"]
            if node not in shells:
                shells[node] = Shell(problem_dir, node)
            started = time.monotonic()
            shells[node].type(step["cmd"])
            print(f"  [{i:>2}/{len(scenario['steps'])}] {time.strftime('%H:%M:%S')} "
                  f"{node:<6} $ {step['cmd']}  ({time.monotonic() - started:.1f}s)", flush=True)
        time.sleep(3)  # beri watcher waktu memproses event terakhir
    finally:
        for shell in shells.values():
            shell.close()
        time.sleep(1)
        os.killpg(watcher.pid, signal.SIGTERM)
        watch_log.close()

    print((problem_dir / ".state" / "watch.log").read_text(), end="")
    if args.capture:
        print(f"golden: {capture(problem_dir, scenario, args.scenario)}")


if __name__ == "__main__":
    main()
