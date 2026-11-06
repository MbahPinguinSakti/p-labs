#!/usr/bin/env python3
"""Checkpoint matcher untuk lab.

Membaca event JSONL di <problem_dir>/.state/events/, mencocokkan dengan
checkpoint di problem.yaml, dan mencatat checkpoint yang tercapai ke
.state/checkpoints.jsonl.

  checkpoints.py watch  <problem_dir>   # jalan selama sesi, event-driven
  checkpoints.py status <problem_dir>   # ringkasan checkpoint sesi ini

Tipe matcher:
  command_match  regex atas tiap segmen command (dipecah di ; && || |)
                 opsi: node, after, expect_exit, any_of (daftar {node, pattern})
  state_check    jalankan command read-only di node, cocokkan output dengan
                 expect_regex. Dievaluasi setiap ada command di node itu,
                 karena state hanya berubah lewat command.
  llm_judge      dinilai evaluator LLM (Fase 2); di sini selalu pending.

Untuk lab RouterOS, watch juga menjalankan guiwatch.py: perubahan konfigurasi
dari Winbox/WebFig/API ditulis sebagai event dengan field `source`, sehingga
ikut dicocokkan di sini seperti command terminal.
"""

if __name__ == "__main__":
    import _venv  # noqa: E402  (Python venv, lihat _venv.py)
    _venv.ensure()

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

SEGMENT_SPLIT = re.compile(r"\s*(?:;|&&|\|\||\||\n)\s*")
STATE_CHECK_TIMEOUT = 5


def render(value, params):
    """Ganti {{nama}} dengan nilai parameter, rekursif."""
    if isinstance(value, str):
        return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(params[m.group(1)]), value)
    if isinstance(value, list):
        return [render(v, params) for v in value]
    if isinstance(value, dict):
        return {k: render(v, params) for k, v in value.items()}
    return value


class Lab:
    def __init__(self, problem_dir, state_dir=None):
        # state_dir: default .state/ (sesi live); bisa diarahkan ke golden/<sesi>/.
        self.dir = Path(problem_dir).resolve()
        self.state = Path(state_dir).resolve() if state_dir else self.dir / ".state"
        self.events_dir = self.state / "events"
        self.hits_file = self.state / "checkpoints.jsonl"

        problem = yaml.safe_load((self.dir / "problem.yaml").read_text())
        topo = yaml.safe_load((self.dir / problem["lab_topology"]).read_text())
        self.lab_name = topo["name"]
        body = topo.get("topology") or {}
        default_kind = (body.get("defaults") or {}).get("kind", "linux")
        self.kinds = {n: (s or {}).get("kind", default_kind) for n, s in (body.get("nodes") or {}).items()}

        self.problem = problem
        params = dict(problem.get("parameters", {}))
        truth_file = self.state / "ground_truth.json"
        if truth_file.exists():
            truth = json.loads(truth_file.read_text())
            params.update({k: v for k, v in truth.items() if k in params})
        self.params = params
        self.problem_id = problem["id"]
        self.checkpoints = render(problem.get("checkpoints", []), params)

        session_file = self.state / "session_id"
        self.session = session_file.read_text().strip() if session_file.exists() else None

    def container(self, node):
        return f"clab-{self.lab_name}-{node}"

    def run_on(self, node, command):
        if self.kinds.get(node) == "mikrotik_ros":
            import ros  # command state_check untuk RouterOS ditulis dalam sintaks RouterOS
            try:
                output, ok = ros.exec_once(self.dir, node, command, timeout=STATE_CHECK_TIMEOUT)
            except (ConnectionError, OSError, subprocess.TimeoutExpired):
                return None
            return output if ok else None
        try:
            proc = subprocess.run(
                ["docker", "exec", self.container(node), "sh", "-c", command],
                capture_output=True, text=True, timeout=STATE_CHECK_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return None
        return proc.stdout if proc.returncode == 0 else None

    def load_hits(self):
        hits = {}
        if self.hits_file.exists():
            for line in self.hits_file.read_text().splitlines():
                hit = json.loads(line)
                if hit.get("session") == self.session:
                    hits.setdefault(hit["id"], hit)
        return hits


class Matcher:
    def __init__(self, lab, hits=None):
        self.lab = lab
        self.hits = dict(hits or {})

    def _node_ok(self, cp, node):
        want = cp.get("node", "any")
        return want == "any" or want == node

    def _after_ok(self, cp, ts):
        dep = cp.get("after")
        return dep is None or (dep in self.hits and self.hits[dep]["ts"] <= ts)

    def feed(self, event, live=True):
        """Proses satu event, kembalikan daftar checkpoint yang baru tercapai."""
        if event.get("type") != "command" or event.get("session") != self.lab.session:
            return []
        new = []
        node, ts = event["node"], event["ts"]
        segments = [s for s in SEGMENT_SPLIT.split(event["data"].strip()) if s]

        for cp in self.lab.checkpoints:
            if cp["id"] in self.hits or not self._node_ok(cp, node):
                continue
            kind = cp["type"]
            evidence = None

            if kind == "command_match":
                if "expect_exit" in cp and event.get("exit") != cp["expect_exit"]:
                    continue
                if not self._after_ok(cp, ts):
                    continue
                rules = cp.get("any_of") or [cp]
                if any(self._node_ok(r, node) and re.search(r["pattern"], seg)
                       for r in rules for seg in segments):
                    evidence = event["data"]

            elif kind == "state_check" and live:
                # Node state_check selalu spesifik; "any" tidak didukung.
                if cp.get("node", "any") == "any" or not self._after_ok(cp, ts):
                    continue
                out = self.lab.run_on(cp["node"], cp["command"])
                if out is not None and re.search(cp["expect_regex"], out):
                    evidence = f"setelah `{event['data']}`: {cp['command']}"

            if evidence is not None:
                hit = {"session": self.lab.session, "id": cp["id"], "type": kind,
                       "ts": ts, "node": node, "evidence": evidence}
                self.hits[cp["id"]] = hit
                new.append(hit)
        return new


class EventTail:
    """Baca baris baru dari semua file *.jsonl di direktori events."""

    def __init__(self, events_dir):
        self.dir = events_dir
        self.offsets = {}
        self.partial = {}

    def poll(self):
        events = []
        for path in sorted(self.dir.glob("*.jsonl")):
            with path.open("rb") as f:
                f.seek(self.offsets.get(path, 0))
                chunk = f.read()
                self.offsets[path] = f.tell()
            buf = self.partial.pop(path, b"") + chunk
            lines = buf.split(b"\n")
            if lines[-1]:
                self.partial[path] = lines[-1]  # baris belum lengkap
            for raw in lines[:-1]:
                if not raw.strip():
                    continue
                try:
                    events.append(json.loads(raw, strict=False))
                except json.JSONDecodeError:
                    print(f"! event rusak di {path.name}: {raw[:80]!r}", file=sys.stderr)
        events.sort(key=lambda e: e.get("ts", 0))
        return events


def replay_hits(lab):
    """Hitung ulang hit checkpoint dari events dengan problem.yaml yang berlaku.

    command_match di-replay dari events, jadi perbaikan pattern langsung
    berlaku untuk sesi lama/golden tanpa merekam ulang. state_check diambil
    dari checkpoints.jsonl rekaman, karena state masa lalu tidak bisa
    diperiksa ulang. Kembalikan (hits, perbedaan_dengan_rekaman).
    """
    recorded = lab.load_hits()
    kinds = {cp["id"]: cp["type"] for cp in lab.checkpoints}
    matcher = Matcher(lab, {cid: hit for cid, hit in recorded.items() if kinds.get(cid) == "state_check"})
    for event in EventTail(lab.events_dir).poll():
        matcher.feed(event, live=False)
    diffs = []
    for cid in sorted(set(recorded) | set(matcher.hits)):
        before, after = recorded.get(cid), matcher.hits.get(cid)
        if (before or {}).get("ts") != (after or {}).get("ts"):
            def show(h):
                return f"{h['node']}: `{h['evidence']}`" if h else "tidak tercapai"
            diffs.append(f"{cid}: rekaman {show(before)} → dihitung ulang {show(after)}")
    return matcher.hits, diffs


def fmt_ts(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts))


def cmd_watch(args):
    lab = Lab(args.problem_dir)
    if not lab.session:
        sys.exit("Belum ada sesi (.state/session_id). Jalankan ./reset.sh dulu.")
    lab.events_dir.mkdir(parents=True, exist_ok=True)

    matcher = Matcher(lab, lab.load_hits())
    tail = EventTail(lab.events_dir)
    print(f"watch {lab.problem_id} sesi {lab.session} "
          f"({len(matcher.hits)}/{len(lab.checkpoints)} checkpoint sudah tercapai)", flush=True)
    if not args.no_gui:
        import guiwatch  # perubahan RouterOS dari Winbox/WebFig/API ikut jadi event
        for watcher in guiwatch.start(lab):
            print(f"guiwatch {watcher.node}: memantau perubahan di luar terminal", flush=True)

    # Event lama (mis. watcher restart): command_match di-replay, state_check
    # tidak, karena state masa lalu tidak bisa diperiksa ulang.
    for event in tail.poll():
        record(lab, matcher.feed(event, live=False))

    while True:
        for event in tail.poll():
            record(lab, matcher.feed(event, live=True))
        time.sleep(args.interval)


def record(lab, hits):
    if not hits:
        return
    with lab.hits_file.open("a") as f:
        for hit in hits:
            f.write(json.dumps(hit) + "\n")
            print(f"[{fmt_ts(hit['ts'])}] ✓ {hit['id']:<14} {hit['node']}: {hit['evidence']}", flush=True)


def cmd_status(args):
    lab = Lab(args.problem_dir)
    hits = lab.load_hits()
    result = []
    for cp in lab.checkpoints:
        hit = hits.get(cp["id"])
        if cp["type"] == "llm_judge":
            status = "pending_llm"
        else:
            status = "hit" if hit else "miss"
        result.append({"id": cp["id"], "type": cp["type"], "status": status, "hit": hit})

    if args.json:
        print(json.dumps({"problem": lab.problem_id, "session": lab.session,
                          "checkpoints": result}, indent=2))
        return
    print(f"{lab.problem_id}  sesi {lab.session}")
    mark = {"hit": "✓", "miss": "·", "pending_llm": "?"}
    for r in result:
        extra = ""
        if r["hit"]:
            extra = f"  [{fmt_ts(r['hit']['ts'])}] {r['hit']['node']}: {r['hit']['evidence']}"
        print(f"  {mark[r['status']]} {r['id']:<14}{extra}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch")
    w.add_argument("problem_dir")
    w.add_argument("--interval", type=float, default=0.5)
    w.add_argument("--no-gui", action="store_true", help="jangan pantau perubahan RouterOS di luar terminal")
    w.set_defaults(func=cmd_watch)
    s = sub.add_parser("status")
    s.add_argument("problem_dir")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)
    args = ap.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
