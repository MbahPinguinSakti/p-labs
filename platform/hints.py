"""Hint berjenjang untuk sesi yang sedang berjalan (dipakai lab-hint dan web UI).

Setiap hint yang dibuka dicatat sebagai event `hint` di .state/events/host.jsonl,
sehingga penaltinya masuk ke skor akhir dan evaluator tahu kapan pemain
memakai hint. Level harus dibuka berurutan; membuka ulang tidak menambah penalti.
"""

import json
import time

from checkpoints import render


class HintError(Exception):
    pass


def hint_list(lab):
    return sorted(render(lab.problem.get("hints", []), lab.params), key=lambda h: h["level"])


def used_levels(lab):
    path = lab.events_dir / "host.jsonl"
    levels = set()
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("type") == "hint" and event.get("session") == lab.session:
                levels.add(event["level"])
    return levels


def open_hint(lab, level=None):
    """Buka hint `level` (default: level berikutnya). Kembalikan (hint, baru_dibuka)."""
    if not lab.session:
        raise HintError("Belum ada sesi (.state/session_id). Jalankan ./reset.sh dulu.")
    hints = hint_list(lab)
    if not hints:
        raise HintError("Soal ini tidak punya hint.")
    used = used_levels(lab)
    next_level = next((h["level"] for h in hints if h["level"] not in used), None)
    if level is None:
        level = next_level or max(used)
    hint = next((h for h in hints if h["level"] == level), None)
    if hint is None:
        raise HintError(f"Tidak ada hint level {level}. Tersedia: {[h['level'] for h in hints]}")
    if level not in used and level != next_level:
        raise HintError(f"Buka hint level {next_level} dulu.")
    if level in used:
        return hint, False
    lab.events_dir.mkdir(parents=True, exist_ok=True)
    with (lab.events_dir / "host.jsonl").open("a") as f:
        f.write(json.dumps({"ts": time.time(), "session": lab.session, "node": "host",
                            "type": "hint", "level": level}) + "\n")
    return hint, True
