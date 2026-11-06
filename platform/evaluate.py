#!/usr/bin/env python3
"""Evaluator sesi lab (Fase 2).

  evaluate.py run   <dir> [--provider P] [--dry-run] [--repeat N]
  evaluate.py check <golden_dir> [--provider P] [--rules-only] [--repeat N]
  evaluate.py providers                     # daftar provider LLM + env yang belum diset
  evaluate.py llm-test [--provider P]       # uji koneksi + structured output, request kecil

Provider dan model: --provider/--model, atau env LAB_LLM_PROVIDER/LAB_LLM_MODEL.

<dir> bisa direktori soal (sesi live di .state/, verify.sh dijalankan) atau
direktori golden transcript (golden/<sesi>/, memakai verify.json yang tersimpan).

Pembagian kerja:
  deterministik  correctness (verify.sh), efficiency, safety, hint, checkpoint rule-based
  LLM            methodology, checkpoint llm_judge, narasi feedback

Hasil: evaluation.json + evaluation.md di direktori sesi.
--dry-run menulis prompt ke evaluator_prompt.md tanpa memanggil LLM.
"""

if __name__ == "__main__":
    import _venv  # noqa: E402  (Python venv, lihat _venv.py)
    _venv.ensure()

import argparse
import json
import re
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml



    

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import scoring  # noqa: E402
from checkpoints import Lab, render as render_template, replay_hits  # noqa: E402
from llm import LLMError, get_backend, list_providers  # noqa: E402
from report import report_md  # noqa: E402
from transcript import NosRules, attach_outputs, build_timeline, load_events, render_timeline  # noqa: E402

BANDS = ["sistematis", "baik", "campuran", "trial_and_error", "tanpa_metode"]
EVIDENCE = {
    "type": "object",
    "properties": {"event": {"type": "string"}, "note": {"type": "string"}},
    "required": ["event", "note"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "methodology": {
            "type": "object",
            "properties": {
                "band": {"type": "string", "enum": BANDS},
                "score": {"type": "integer"},
                "rationale": {"type": "string"},
                "evidence": {"type": "array", "items": EVIDENCE},
            },
            "required": ["band", "score", "rationale", "evidence"],
            "additionalProperties": False,
        },
        "llm_checkpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "hit": {"type": "boolean"},
                    "rationale": {"type": "string"},
                    "evidence": {"type": "array", "items": EVIDENCE},
                },
                "required": ["id", "hit", "rationale", "evidence"],
                "additionalProperties": False,
            },
        },
        "feedback": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "improvements": {"type": "array", "items": {"type": "string"}},
                "technical_lessons": {"type": "array", "items": {"type": "string"}},
                "key_moments": {"type": "array", "items": EVIDENCE},
                "next_practice": {"type": "string"},
            },
            "required": ["summary", "strengths", "improvements", "technical_lessons",
                         "key_moments", "next_practice"],
            "additionalProperties": False,
        },
    },
    "required": ["methodology", "llm_checkpoints", "feedback"],
    "additionalProperties": False,
}


# --- memuat sesi ----------------------------------------------------------------

# TODO(human): definisikan class error (mis. EvaluatorError) di sini, lalu ganti sys.exit di
# resolve, run_verify, Session.__init__, dan cmd_check dengan raise; tangkap di main().
class EvaluatorError(Exception):
    """Error fatal evaluator yang harus ditangkap di main() dan diterjemahkan ke sys.exit."""


def resolve(path):
    """Kembalikan (problem_dir, state_dir, live)."""
    path = Path(path).resolve()
    if (path / "problem.yaml").exists():
        return path, path / ".state", True
    for parent in path.parents:
        if (parent / "problem.yaml").exists():
            return parent, path, False
    raise EvaluatorError(f"Tidak menemukan problem.yaml untuk {path}")


def run_verify(problem_dir, state_dir):
    process = subprocess.run(["./verify.sh"], cwd=problem_dir, capture_output=True, text=True)
    try:
        result = json.loads(process.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise EvaluatorError(f"verify.sh tidak mengeluarkan JSON:\n{process.stdout}{process.stderr}")
    if process.returncode == 2 or "error" in result:
        raise EvaluatorError(f"verify.sh gagal: {result.get('error', process.stderr)}")
    (state_dir / "verify.json").write_text(json.dumps(result) + "\n")
    return result


class Session:
    def __init__(self, path, live_verify=True):
        self.problem_dir, self.state_dir, self.live = resolve(path)
        self.lab = Lab(self.problem_dir, self.state_dir)
        if not self.lab.session:
            raise EvaluatorError(f"Tidak ada session_id di {self.state_dir}")
        self.problem = self.lab.problem
        truth = self.state_dir / "ground_truth.json"
        if not truth.exists():
            raise EvaluatorError("Sesi ini tidak punya ground truth: deploy atau inject.sh gagal sebelum "
                                 "sesi siap. Mulai sesi baru (Deploy ulang lab, atau ./reset.sh).")
        self.ground_truth = json.loads(truth.read_text())

        if self.live and live_verify:
            self.verify_result = run_verify(self.problem_dir, self.state_dir)
        else:
            self.verify_result = json.loads((self.state_dir / "verify.json").read_text())

        self.events = attach_outputs(load_events(self.state_dir / "events", self.lab.session),
                                     self.state_dir / "tty")
        nos_rules = NosRules(self.problem.get("nos", "linux-bridge"), HERE)
        self.timeline = build_timeline(self.events, nos_rules)
        self.event_ids = {entry["id"] for entry in self.timeline}
        # command_match dihitung ulang dari events (pattern terbaru); state_check dari rekaman.
        self.hits, self.hit_diffs = replay_hits(self.lab)

    def event_id_at(self, timestamp, node):
        return next((entry["id"] for entry in self.timeline
                     if entry["ts"] == timestamp and entry["node"] == node), None)


# --- penilaian deterministik ---------------------------------------------------

def deterministic_scores(session):
    problem = session.problem
    scoring_config = problem.get("scoring", {})
    efficiency = scoring.efficiency(session.timeline, problem.get("expert_baseline", {}).get("state_changes", 1))
    safety = scoring.safety(session.timeline, scoring_config.get("safety", []))
    hints = scoring.hint_penalty(session.events, problem.get("hints", []))
    checkpoints = []
    for checkpoint in session.lab.checkpoints:
        if checkpoint["type"] == "llm_judge":
            continue
        hit = session.hits.get(checkpoint["id"])
        checkpoints.append({
            "id": checkpoint["id"], "type": checkpoint["type"], "hit": bool(hit),
            "event": session.event_id_at(hit["ts"], hit["node"]) if hit else None,
            "ts": hit["ts"] if hit else None,
        })
    gate = scoring.process_gate(checkpoints, scoring_config.get("process_gate"))
    gui = gui_usage(session, checkpoints, gate)
    if gate["factor"] < 1 and gui["fix_event"]:
        gate = scoring.waive_gate(gate, f"fix dilakukan lewat {gui['fix_source']} ({gui['fix_event']})")
    return {"correctness": session.verify_result["correctness"], "verify": session.verify_result,
            "efficiency": efficiency, "safety": safety, "hints": hints, "checkpoints": checkpoints,
            "process_gate": gate, "gui": gui, "checkpoints_rescored": session.hit_diffs}


def gui_usage(session, checkpoints, gate):
    """Apakah pemain bekerja di luar terminal (Winbox/WebFig/API, lihat guiwatch.py)?

    fix_event: event fix (checkpoint `before` di process gate) kalau fix itu
    sendiri dibuat dari luar terminal. Hanya kasus ini yang membebaskan process
    gate: login Winbox lalu memperbaiki dari terminal tanpa diagnosis tetap kena gate.
    """
    by_id = {entry["id"]: entry for entry in session.timeline}
    logins = sorted({event["via"] for event in session.events if event["type"] == "gui_login"})
    changes = [entry["id"] for entry in session.timeline if entry.get("source")]
    fix = next((c for c in checkpoints if c["id"] == gate.get("before") and c["event"]), None)
    fix_entry = by_id.get(fix["event"]) if fix else None
    external_fix = bool(fix_entry and fix_entry.get("source"))
    return {"used": bool(logins or changes), "via": logins, "changes": changes,
            "fix_event": fix_entry["id"] if external_fix else None,
            "fix_source": fix_entry["source"] if external_fix else None}


# --- prompt LLM ------------------------------------------------------------------

def design_doc(problem_dir, problem):
    """Komentar di kepala file topologi = dokumentasi desain (bukan state)."""
    lines = []
    for line in (problem_dir / problem["lab_topology"]).read_text().splitlines():
        if not line.startswith("#"):
            break
        lines.append(line[1:].removeprefix(" "))
    return "\n".join(lines).strip()


def to_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_prompt(session, rule_based):
    problem, lab = session.problem, session.lab
    fault = problem.get("fault_injection", {})
    llm_checkpoints = [checkpoint for checkpoint in lab.checkpoints if checkpoint["type"] == "llm_judge"]
    duration = session.timeline[-1]["t"] if session.timeline else 0
    n_commands = sum(1 for entry in session.timeline if not entry.get("hint_level"))
    hint_text = {h["level"]: h["text"] for h in render_template(problem.get("hints", []), lab.params)}
    used_hints = [entry for entry in session.timeline if entry.get("hint_level")]
    parameters = {key: value for key, value in session.ground_truth.items() if key != "injected_at"}

    parts = [
        f"# Soal {problem['id']}: {problem['title']}",
        f"Kategori: {problem.get('category')} · Difficulty: {problem.get('difficulty')} · NOS: {problem.get('nos')}",
        "## Tiket yang dibaca pemain\n" + (session.problem_dir / problem.get("brief", "brief.md")).read_text().strip(),
        "## Dokumentasi desain topologi\n" + design_doc(session.problem_dir, problem),
        "## Ground truth (rahasia selama sesi, boleh dibahas di feedback)\n" + "\n".join([
            "- Fault: " + render_template(fault.get("description", ""), lab.params),
            "- Fix yang diharapkan: " + render_template(fault.get("expected_fix", ""), lab.params),
            "- Parameter: " + json.dumps(parameters),
            f"- Baseline expert: {problem.get('expert_baseline', {})}",
        ]),
        "## Hasil penilaian otomatis (jangan dinilai ulang)",
        "verify.sh:\n" + to_json(rule_based["verify"]),
        "Efficiency:\n" + to_json(rule_based["efficiency"]),
        "Safety:\n" + to_json(rule_based["safety"]),
        "Checkpoint rule-based (event = saat tercapai):\n" + to_json(rule_based["checkpoints"]),
        "Process gate (bukti proses sebelum fix; dihitung deterministik, jangan dinilai ulang):\n"
        + to_json(rule_based["process_gate"]),
        "## Checkpoint yang harus kamu nilai (llm_judge)\n" + ("\n".join(
            f"- id `{checkpoint['id']}`: {checkpoint['criteria']}" for checkpoint in llm_checkpoints) or "(tidak ada)"),
        "## Hint yang dibuka pemain (penalti sudah dihitung otomatis)\n" + ("\n".join(
            f"- {entry['id']}: level {entry['hint_level']}, \"{hint_text.get(entry['hint_level'], '')}\""
            for entry in used_hints) or "(tidak ada)"),
        gui_note(rule_based["gui"]),
        f"## Timeline sesi\n{n_commands} command, durasi ~{duration // 60} menit. "
        "Format: `ID +mm:ss node exit=<kode> $ command`, baris `|` = output yang dilihat pemain. "
        "Tag [UBAH STATE] dan [REWORK] dihitung otomatis.",
        render_timeline(session.timeline),
    ]
    return "\n\n".join(part for part in parts if part)


def gui_note(gui):
    """Konteks untuk LLM kalau pemain memakai GUI: aktivitas membaca tidak terekam."""
    if not gui["used"]:
        return ""
    via = ", ".join(gui["via"]) or "di luar terminal P-lab"
    return "\n".join([
        f"## Pemain memakai GUI ({via})",
        "Event bertanda [WINBOX]/[WEB]/[API]/[LUAR-TERMINAL] bukan diketik pemain: itu terjemahan otomatis "
        "selisih konfigurasi router menjadi command RouterOS, dan waktunya bisa terlambat beberapa detik. "
        "Aktivitas MEMBACA di GUI (membuka tabel address/route) tidak terekam sama sekali.",
        "Jadi: jangan simpulkan pemain tidak mendiagnosis hanya karena tidak ada command baca. Nilai methodology "
        "dari yang teramati: perubahan tepat sasaran, sedikit perubahan percobaan/rework, dan tidak menyentuh "
        "bagian yang sehat. Karena proses diagnosisnya tidak teramati, jangan beri band `sistematis`; "
        "sebutkan keterbatasan ini di rationale. Checkpoint llm_judge yang butuh bukti proses dinilai dari "
        "bukti yang ada saja.",
    ])


def system_prompt():
    return (HERE / "prompts" / "evaluator-system.md").read_text()


# --- validasi output LLM ---------------------------------------------------------

EVENT_RANGE = re.compile(r"^E(\d+)\s*[-–]\s*E?(\d+)$")


def clean_evidence(items, location, known_ids):
    """Pisahkan bukti yang merujuk event nyata; kembalikan (kept, dropped).

    Rentang seperti "E2-E3" (model kadang menulis begitu) dipecah menjadi satu
    bukti per event, asalkan semua event di rentang itu ada.
    """
    kept = []
    dropped = []
    for evidence in items:
        event = str(evidence.get("event", "")).strip()
        span = EVENT_RANGE.match(event)
        if span and int(span.group(1)) <= int(span.group(2)) <= int(span.group(1)) + 20:
            ids = [f"E{n}" for n in range(int(span.group(1)), int(span.group(2)) + 1)]
            if all(i in known_ids for i in ids):
                kept += [{**evidence, "event": i} for i in ids]
                continue
        if event in known_ids:
            kept.append({**evidence, "event": event})
        else:
            dropped.append(f"{location}: event tidak dikenal {evidence.get('event')!r} dibuang")
    return kept, dropped


def validate(raw, session):
    """Rapikan output LLM; kembalikan (hasil, warnings)."""
    warnings = []
    known_ids = session.event_ids

    methodology = raw["methodology"]
    if methodology["band"] not in BANDS:
        warnings.append(f"band tidak valid: {methodology['band']}")
    if not 0 <= methodology["score"] <= 100:
        warnings.append(f"skor methodology {methodology['score']} di-clamp")
    methodology["score"] = scoring.clamp(int(methodology["score"]))
    methodology["evidence"], dropped = clean_evidence(methodology["evidence"], "methodology", known_ids)
    warnings.extend(dropped)
    if not methodology["evidence"]:
        warnings.append("methodology tanpa bukti yang valid")

    expected_ids = {checkpoint["id"] for checkpoint in session.lab.checkpoints if checkpoint["type"] == "llm_judge"}
    judged = {}
    for checkpoint in raw["llm_checkpoints"]:
        if checkpoint["id"] not in expected_ids:
            warnings.append(f"checkpoint llm_judge tidak dikenal: {checkpoint['id']}")
            continue
        checkpoint["evidence"], dropped = clean_evidence(checkpoint["evidence"], f"checkpoint {checkpoint['id']}", known_ids)
        warnings.extend(dropped)
        judged[checkpoint["id"]] = checkpoint
    for missing in expected_ids - judged.keys():
        warnings.append(f"checkpoint {missing} tidak dinilai LLM")
    raw["llm_checkpoints"] = [judged[checkpoint_id] for checkpoint_id in sorted(judged)]

    feedback = raw["feedback"]
    feedback["key_moments"], dropped = clean_evidence(feedback["key_moments"], "key_moments", known_ids)
    warnings.extend(dropped)
    return raw, warnings


# --- progres real-time -------------------------------------------------------------

class Progress:
    """Tampilkan progres tiap run LLM ke stderr (stdout tetap bersih).

    Di terminal: satu baris yang diperbarui tiap detik (timer berjalan).
    Di file/pipe (mis. `2> log` lalu `tail -f log`): satu baris per kejadian.
    """

    def __init__(self, label, total):
        self.label, self.total = label, total
        self.tty = sys.stderr.isatty()

    def _write(self, text, final=False):
        if self.tty:
            sys.stderr.write("\r\033[K" + text + ("\n" if final else ""))
        else:
            sys.stderr.write(text + "\n")
        sys.stderr.flush()

    def run(self, index, fn):
        prefix = f"[{self.label}] run {index}/{self.total}"
        started = time.monotonic()
        stop = threading.Event()

        def tick():
            while not stop.wait(1):
                self._write(f"{prefix} menunggu model... {time.monotonic() - started:.0f}s")

        if self.tty:
            threading.Thread(target=tick, daemon=True).start()
        else:
            self._write(f"{prefix} mulai {time.strftime('%H:%M:%S')}")
        try:
            result = fn()
        except Exception as error:
            stop.set()
            self._write(f"{prefix} GAGAL setelah {time.monotonic() - started:.0f}s: {error}", final=True)
            raise
        stop.set()
        return result, time.monotonic() - started

    def done(self, index, elapsed, output, meta, warnings):
        methodology = output["methodology"]
        usage = meta.get("usage") or {}
        tokens = usage.get("total_tokens") or (usage.get("input_tokens", 0) + usage.get("output_tokens", 0))
        if meta.get("usage_first"):
            tokens += meta["usage_first"].get("total_tokens", 0)
        checkpoints = " ".join(f"{c['id']}={'ya' if c['hit'] else 'tidak'}" for c in output["llm_checkpoints"])
        self._write(
            f"[{self.label}] run {index}/{self.total} selesai {elapsed:.0f}s | "
            f"methodology {methodology['score']} ({methodology['band']}) | {checkpoints} | "
            f"schema {'retry' if meta.get('schema_retry') else 'ok'} | "
            f"{tokens} token | {len(warnings)} warning", final=True)


# --- run -------------------------------------------------------------------------

def evaluate(session, provider=None, dry_run=False, repeat=1, model=None, write_prompt=True):
    rule_based = deterministic_scores(session)
    system_text, user_text = system_prompt(), build_prompt(session, rule_based)
    weights = {**scoring.DEFAULT_WEIGHTS, **session.problem.get("scoring", {}).get("weights", {})}

    result = {
        "problem": session.problem["id"], "session": session.lab.session,
        "weights": weights, "rule_based": rule_based,
        "llm": None, "llm_runs": [], "warnings": [],
    }
    if dry_run:
        if write_prompt:
            (session.state_dir / "evaluator_prompt.md").write_text(
            f"<!-- SYSTEM -->\n{system_text}\n\n<!-- USER -->\n{user_text}\n")
    else:
        backend = get_backend(provider, model)
        progress = Progress(f"{backend.name}:{backend.model}", repeat)
        for index in range(1, repeat + 1):
            (raw, meta), elapsed = progress.run(
                index, lambda: backend.complete_json(system_text, user_text, SCHEMA))
            output, run_warnings = validate(raw, session)
            meta["elapsed_s"] = round(elapsed, 1)
            progress.done(index, elapsed, output, meta, run_warnings)
            result["llm_runs"].append({"output": output, "meta": meta, "warnings": run_warnings})
        # Beberapa run: pakai run dengan skor methodology median sebagai hasil utama.
        # Skor sama: utamakan run dengan warning paling sedikit.
        sorted_runs = sorted(result["llm_runs"],
                             key=lambda run: (run["output"]["methodology"]["score"], len(run["warnings"])))
        median_run = sorted_runs[len(sorted_runs) // 2]
        result["llm"], result["warnings"] = median_run["output"], median_run["warnings"]

    methodology_score = result["llm"]["methodology"]["score"] if result["llm"] else None
    scores = {"correctness": rule_based["correctness"], "efficiency": rule_based["efficiency"]["score"],
              "methodology": methodology_score, "safety": rule_based["safety"]["score"]}
    result["scores"] = scores  # skor mentah per dimensi
    # Skor yang dikreditkan: correctness/efficiency dikali faktor process gate.
    result["credited"] = scoring.credited(scores, rule_based["process_gate"])
    result["final_score"] = scoring.final_score(result["credited"], weights, rule_based["hints"]["penalty"])
    if len(result["llm_runs"]) > 1:
        run_scores = [run["output"]["methodology"]["score"] for run in result["llm_runs"]]
        result["methodology_spread"] = {"scores": run_scores, "min": min(run_scores), "max": max(run_scores),
                                        "median": statistics.median(run_scores)}
    return result


# --- check golden ------------------------------------------------------------------

def check_range(name, value, rule):
    """Periksa satu nilai terhadap aturannya di expected.yaml; kembalikan (passed, pesan).

    rule    angka (nilai harus persis sama) atau {min, max} (rentang, default 0-100)
    passed  True = lolos, False = gagal, None = dilewati (value None, mis. methodology tanpa LLM)
    """
    if value is None:
        return None, f"{name}: dilewati (tidak ada nilai)"
    if isinstance(rule, (int, float)):
        passed, rule_text = value == rule, f"= {rule}"
    else:
        lower, upper = rule.get("min", 0), rule.get("max", 100)
        passed, rule_text = lower <= value <= upper, f"dalam [{lower}, {upper}]"
    return passed, f"{name} = {value}, harus {rule_text}"


def check_golden(result, expected):
    """Bandingkan hasil evaluasi dengan expected.yaml; kembalikan daftar (passed, pesan)."""
    checks = []
    scores, rule_based = result["scores"], result["rule_based"]
    for dimension in ("correctness", "efficiency", "safety", "methodology"):
        if dimension in expected:
            checks.append(check_range(dimension, scores[dimension], expected[dimension]))
    if "final" in expected:
        checks.append(check_range("final", result["final_score"], expected["final"]))

    # {id pelanggaran: severity} yang terdeteksi di sesi
    violations = {violation["id"]: violation["severity"] for violation in rule_based["safety"]["violations"]}
    for violation_id in expected.get("safety_violations", {}).get("include", []):
        checks.append((violation_id in violations, f"pelanggaran safety `{violation_id}` terdeteksi"))
    for severity in expected.get("safety_violations", {}).get("exclude_severity", []):
        offenders = [found_id for found_id, level in violations.items() if level == severity]
        checks.append((not offenders, f"tidak ada pelanggaran {severity}" + (f" (ada: {offenders})" if offenders else "")))

    if "hint_levels" in expected:
        used = rule_based["hints"]["levels_used"]
        checks.append((used == expected["hint_levels"], f"hint dipakai = {used}, harus {expected['hint_levels']}"))
    if "process_gate" in expected:
        factor = rule_based.get("process_gate", {}).get("factor", 1.0)
        checks.append((factor == expected["process_gate"], f"process gate = {factor}, harus {expected['process_gate']}"))

    hit_ids = {checkpoint["id"] for checkpoint in rule_based["checkpoints"] if checkpoint["hit"]}
    for checkpoint_id in expected.get("checkpoints_hit", []):
        checks.append((checkpoint_id in hit_ids, f"checkpoint `{checkpoint_id}` tercapai"))
    for checkpoint_id in expected.get("checkpoints_miss", []):
        checks.append((checkpoint_id not in hit_ids, f"checkpoint `{checkpoint_id}` tidak tercapai"))
    if result["llm"]:
        llm_hits = {checkpoint["id"]: checkpoint["hit"] for checkpoint in result["llm"]["llm_checkpoints"]}
        for checkpoint_id, expected_hit in (expected.get("llm_checkpoints") or {}).items():
            actual_hit = llm_hits.get(checkpoint_id)
            checks.append((actual_hit == expected_hit, f"llm checkpoint `{checkpoint_id}` = {actual_hit}, harus {expected_hit}"))
        if "methodology_band" in expected:
            band = result["llm"]["methodology"]["band"]
            checks.append((band in expected["methodology_band"], f"band methodology `{band}` ∈ {expected['methodology_band']}"))
    if result.get("methodology_spread") and "max_spread" in expected:
        run_scores = result["methodology_spread"]
        spread = run_scores["max"] - run_scores["min"]
        checks.append((spread <= expected["max_spread"], f"selisih methodology antar-run = {spread}, maks {expected['max_spread']}"))
    if result["llm"]:
        warnings = result["warnings"]
        checks.append((not warnings, "output LLM tanpa peringatan" + (f": {warnings}" if warnings else "")))
    return checks


# --- CLI -------------------------------------------------------------------------

def write_outputs(session, result):
    (session.state_dir / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (session.state_dir / "evaluation.md").write_text(report_md(session, result))


def cmd_run(args):
    session = Session(args.dir)
    try:
        result = evaluate(session, args.provider, args.dry_run, args.repeat, args.model)
    except LLMError as error:
        raise EvaluatorError(f"Evaluator LLM gagal: {error}\n(Pakai --dry-run untuk melihat prompt tanpa LLM.)")
    write_outputs(session, result)
    print(report_md(session, result))
    if args.dry_run:
        print(f"Prompt ditulis ke {session.state_dir / 'evaluator_prompt.md'}")


def golden_checks(golden_dir, provider=None, rules_only=False, repeat=1, model=None):
    """Nilai satu golden transcript dan bandingkan dengan expected.yaml.

    Kembalikan (expected, result, checks). Mode rules_only tidak menulis apa
    pun ke direktori golden; mode LLM memperbarui evaluation.json/.md di sana.
    """
    session = Session(golden_dir, live_verify=False)
    expected_file = session.state_dir / "expected.yaml"
    if not expected_file.exists():
        raise EvaluatorError(f"Tidak ada {expected_file}")
    expected = yaml.safe_load(expected_file.read_text())
    try:
        result = evaluate(session, provider, dry_run=rules_only, repeat=repeat, model=model,
                          write_prompt=False)
    except LLMError as error:
        raise EvaluatorError(f"Evaluator LLM gagal: {error}\n(Pakai --rules-only untuk cek bagian deterministik saja.)")
    if not rules_only:
        write_outputs(session, result)
    return expected, result, check_golden(result, expected)


def print_checks(name, expected, checks):
    print(f"golden {name}: {expected.get('label', '')}")
    for passed, message in checks:
        print(f"  {'·' if passed is None else '✓' if passed else '✗'} {message}")
    failed = [message for passed, message in checks if passed is False]
    print(f"{len(checks) - len(failed)}/{len(checks)} lolos")
    return failed


def cmd_check(args):
    expected, _, checks = golden_checks(args.dir, args.provider, args.rules_only, args.repeat, args.model)
    failed = print_checks(Path(args.dir).resolve().name, expected, checks)
    sys.exit(1 if failed else 0)


def cmd_check_all(args):
    """Semua golden satu soal: cek masing-masing, lalu tampilkan urutan skor akhirnya."""
    problem_dir = Path(args.problem_dir).resolve()
    goldens = sorted(path.parent for path in problem_dir.glob("golden/*/expected.yaml"))
    if not goldens:
        raise EvaluatorError(f"Tidak ada golden/*/expected.yaml di {problem_dir}")
    summary, any_failed = [], False
    for golden in goldens:
        expected, result, checks = golden_checks(golden, args.provider, args.rules_only, args.repeat, args.model)
        failed = print_checks(golden.name, expected, checks)
        any_failed |= bool(failed)
        label = expected.get("label", "").split(":")[0][:28]
        summary.append((result["final_score"], golden.name, label, len(checks) - len(failed), len(checks)))
        print()
    print("Ringkasan (urut skor akhir):")
    for final, name, label, ok, total in sorted(summary, key=lambda row: -(row[0] if row[0] is not None else -1)):
        print(f"  {'-' if final is None else final:>6}  {name}  {label:<28} {ok}/{total}")
    sys.exit(1 if any_failed else 0)



def cmd_providers(args):
    print(f"{'provider':<18} {'keterangan':<56} status")
    for name, description, missing in list_providers():
        status = "siap" if not missing else "belum diset: " + ", ".join(missing)
        print(f"{name:<18} {description:<56} {status}")
    print("\nPilih dengan --provider <nama> atau LAB_LLM_PROVIDER. Panduan: platform/llm/README.md")


PING_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}, "model_says": {"type": "string"}},
    "required": ["ok", "model_says"],
    "additionalProperties": False,
}


def cmd_llm_test(args):
    try:
        backend = get_backend(args.provider, args.model)
        data, meta = backend.complete_json(
            "Kamu adalah endpoint uji. Balas sesuai schema.",
            'Isi ok=true dan model_says dengan kalimat pendek "halo dari <nama model>".',
            PING_SCHEMA)
    except LLMError as error:
        raise EvaluatorError(f"Gagal: {error}")
    print(json.dumps({"response": data, "meta": meta}, ensure_ascii=False, indent=2))
    if not meta.get("structured_output"):
        print("Catatan: server tidak mendukung structured output; dipakai mode instruksi (JSON di prompt).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    def add_llm_args(subparser):
        subparser.add_argument("--provider", help="nama provider (lihat: evaluate.py providers)")
        subparser.add_argument("--model", help="nama model, override LAB_LLM_MODEL")

    run_parser = subparsers.add_parser("run", help="evaluasi satu sesi")
    run_parser.add_argument("dir")
    add_llm_args(run_parser)
    run_parser.add_argument("--dry-run", action="store_true", help="tulis prompt, jangan panggil LLM")
    run_parser.add_argument("--repeat", type=int, default=1)
    run_parser.set_defaults(func=cmd_run)
    check_parser = subparsers.add_parser("check", help="uji evaluator terhadap golden transcript")
    check_parser.add_argument("dir")
    add_llm_args(check_parser)
    check_parser.add_argument("--rules-only", action="store_true", help="hanya bagian deterministik")
    check_parser.add_argument("--repeat", type=int, default=1)
    check_parser.set_defaults(func=cmd_check)
    all_parser = subparsers.add_parser("check-all", help="uji semua golden transcript sebuah soal")
    all_parser.add_argument("problem_dir")
    add_llm_args(all_parser)
    all_parser.add_argument("--rules-only", action="store_true", help="hanya bagian deterministik")
    all_parser.add_argument("--repeat", type=int, default=1)
    all_parser.set_defaults(func=cmd_check_all)
    providers_parser = subparsers.add_parser("providers", help="daftar provider LLM")
    providers_parser.set_defaults(func=cmd_providers)
    test_parser = subparsers.add_parser("llm-test", help="uji koneksi ke provider LLM")
    add_llm_args(test_parser)
    test_parser.set_defaults(func=cmd_llm_test)
    args = parser.parse_args()
    try:
        args.func(args)
    except EvaluatorError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
