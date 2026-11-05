"""Bangun timeline sesi dari event JSONL + transcript tty.

Timeline = daftar command berurutan waktu, tiap entri diberi ID stabil (E1, E2,
...) yang dipakai evaluator LLM sebagai rujukan bukti. Output yang dilihat
pemain diambil dari log `script` (lab-shell): stream O dipisahkan dari stream I
memakai file timing format advanced, dibersihkan dari escape terminal, dipotong
per prompt, lalu dicocokkan ke event berdasarkan teks command.
"""

import json
import re
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

import yaml

from checkpoints import SEGMENT_SPLIT

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
MAX_OUTPUT_LINES = 30
MAX_OUTPUT_CHARS = 2500


def load_events(events_dir, session):
    events = []
    for path in sorted(Path(events_dir).glob("*.jsonl")):
        for line in path.read_text(errors="replace").splitlines():
            if line.strip():
                ev = json.loads(line, strict=False)
                if ev.get("session") == session:
                    events.append(ev)
    events.sort(key=lambda e: e["ts"])
    return events


# --- tty log -------------------------------------------------------------------

def read_output_stream(log_path, timing_path):
    """Stream yang dilihat pemain (O saja), plus waktu tiap potongannya.

    Kembalikan (start_time, text, marks): marks = [(offset_char, detik_sejak_start)].
    """
    raw = Path(log_path).read_bytes()
    body = raw[raw.index(b"\n") + 1:]  # lewati baris "Script started on ..."
    start, elapsed, pos = None, 0.0, 0
    text, marks = [], []
    length = 0
    for line in Path(timing_path).read_text().splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 3:
            continue
        kind, delay, rest = parts
        if kind == "H" and rest.startswith("START_TIME "):
            start = datetime.fromisoformat(rest.split(" ", 1)[1].replace(" ", "T")).timestamp()
        # Delay relatif ke entri sebelumnya, termasuk entri S (sinyal, mis.
        # resize terminal); kalau dilewati, waktu bergeser.
        elapsed += float(delay)
        if kind not in ("I", "O"):
            continue
        size = int(rest)
        if kind == "O":
            chunk = body[pos:pos + size].decode("utf-8", errors="replace")
            marks.append((length, elapsed))
            text.append(chunk)
            length += len(chunk)
        pos += size
    return start, "".join(text), marks


def clean_terminal(text):
    text = ANSI.sub("", text).replace("\r\n", "\n")
    lines = []
    for line in text.split("\n"):
        line = line.rsplit("\r", 1)[-1]  # carriage return: teks terakhir menang
        buf = []
        for ch in line:
            if ch == "\b":
                if buf:
                    buf.pop()
            elif ch == "\x07" or (ch < " " and ch != "\t"):
                continue
            else:
                buf.append(ch)
        lines.append("".join(buf))
    return "\n".join(lines)


def split_by_prompt(start, text, marks, node):
    """Potong stream mentah per prompt PS1 lab-rc.sh.

    Tiap segmen = echo command + output-nya, dan berakhir saat prompt berikutnya
    muncul. Kembalikan [(waktu_prompt_penutup, output_bersih)]; waktu ini
    hampir sama dengan ts event command (PROMPT_COMMAND jalan tepat sebelum
    prompt dicetak).
    """
    prompt = re.compile(rf"\x1b\[1;32m{re.escape(node)}\x1b\[0m:[^\n#]*# ")
    offsets = [m.start() for m in prompt.finditer(text)]
    times = [o for o, _ in marks]

    def time_at(offset):
        i = max(0, bisect_right(times, offset) - 1)
        return start + marks[i][1] if marks else start

    segments = []
    for a, b in zip(offsets, offsets[1:]):
        piece = clean_terminal(text[a:b])
        _, _, output = piece.partition("\n")  # baris pertama = prompt + echo
        segments.append((time_at(b), output.rstrip("\n")))
    return segments


def truncate(output):
    lines = output.splitlines()
    cut = False
    if len(lines) > MAX_OUTPUT_LINES:
        lines, cut = lines[:MAX_OUTPUT_LINES], True
    text = "\n".join(lines)
    if len(text) > MAX_OUTPUT_CHARS:
        text, cut = text[:MAX_OUTPUT_CHARS], True
    return text + ("\n[... output dipotong ...]" if cut else "")


def attach_outputs(events, tty_dir, tolerance=1.5):
    """Isi event['output'] dari log tty, dicocokkan per node berdasarkan waktu.

    Teks echo command tidak bisa diandalkan (redraw readline, recall history
    dengan panah atas), jadi pencocokan memakai waktu: command E dipasangkan
    dengan segmen yang prompt penutupnya muncul paling dekat dengan ts E.
    START_TIME di timing file hanya presisi detik; kalau ada event shell_open
    dari lab-shell yang dekat, itu dipakai sebagai titik nol yang lebih presisi.
    """
    tty_dir = Path(tty_dir)
    opens = {}
    for ev in events:
        if ev["type"] == "shell_open":
            opens.setdefault(ev["node"], []).append(ev["ts"])

    by_node = {}
    for ev in events:
        if ev["type"] == "command":
            by_node.setdefault(ev["node"], []).append(ev)

    for node, node_events in by_node.items():
        segments = []
        for log in sorted(tty_dir.glob(f"{node}-*.log")):
            timing = log.with_suffix(".timing")
            if not timing.exists():
                continue
            start, text, marks = read_output_stream(log, timing)
            if start is None:
                continue
            near = [t for t in opens.get(node, []) if 0 <= t - start < 2]
            if near:
                start = near[0]
            segments += split_by_prompt(start, text, marks, node)

        used = set()
        for ev in node_events:
            best = None
            for j, (t, _) in enumerate(segments):
                gap = abs(t - ev["ts"])
                if j not in used and gap <= tolerance and (best is None or gap < best[0]):
                    best = (gap, j)
            if best:
                used.add(best[1])
                ev["output"] = truncate(segments[best[1]][1])
    return events


# --- klasifikasi command ------------------------------------------------------

class NosRules:
    def __init__(self, nos, platform_dir):
        spec = yaml.safe_load((Path(platform_dir) / "nos" / f"{nos}.yaml").read_text())
        self.rules = [(re.compile(r["pattern"]), r["key"]) for r in spec["state_change"]]

    def changes(self, command):
        """Daftar key objek yang diubah oleh command (kosong = read-only)."""
        keys = []
        for seg in SEGMENT_SPLIT.split(command.strip()):
            for rx, key in self.rules:
                m = rx.search(seg)
                if m:
                    keys.append(key.format(**{k: v for k, v in m.groupdict().items() if v}))
                    break
        return keys


def build_timeline(events, rules):
    """Beri ID E<n> ke tiap command dan tandai perubahan state + rework."""
    timeline, seen = [], {}
    t0 = events[0]["ts"] if events else 0
    n = 0
    hints = 0
    for ev in events:
        if ev["type"] == "hint":
            # Hint ikut di timeline (ID H<n>) supaya evaluator tahu kapan dipakai.
            hints += 1
            timeline.append({
                "id": f"H{hints}", "ts": ev["ts"], "t": round(ev["ts"] - t0), "node": "host",
                "command": f"(hint level {ev['level']} dibuka)", "exit": None, "hint_level": ev["level"],
                "state_change": [], "rework": [], "output": None,
            })
            continue
        if ev["type"] != "command":
            continue
        n += 1
        keys = rules.changes(ev["data"]) if ev.get("exit") == 0 else []
        rework = []
        for k in keys:
            if (ev["node"], k) in seen:
                rework.append(k)
            seen.setdefault((ev["node"], k), []).append(f"E{n}")
        timeline.append({
            "id": f"E{n}", "ts": ev["ts"], "t": round(ev["ts"] - t0), "node": ev["node"],
            "command": ev["data"], "exit": ev.get("exit"),
            "state_change": keys, "rework": rework, "output": ev.get("output"),
        })
    return timeline


def render_timeline(timeline, with_output=True):
    """Teks timeline untuk prompt LLM."""
    out = []
    for e in timeline:
        mm, ss = divmod(e["t"], 60)
        if e.get("hint_level"):
            out.append(f"{e['id']} +{mm:02d}:{ss:02d} [HINT] pemain membuka hint level {e['hint_level']}")
            continue
        tag = ""
        if e["state_change"]:
            tag = "  [UBAH STATE: " + ", ".join(e["state_change"]) + "]"
            if e["rework"]:
                tag += " [REWORK]"
        out.append(f"{e['id']} +{mm:02d}:{ss:02d} {e['node']} exit={e['exit']} $ {e['command']}{tag}")
        if with_output and e.get("output"):
            out.extend("    | " + line for line in e["output"].splitlines())
    return "\n".join(out)
