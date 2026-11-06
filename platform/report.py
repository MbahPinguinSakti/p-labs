"""Laporan markdown hasil evaluasi (evaluation.md).

Hanya memformat: semua angka sudah dihitung di evaluate.py dan scoring.py.
"""

from functools import partial

DIMENSIONS = ("correctness", "efficiency", "methodology", "safety")


def describe_event(by_id, event_id):
    """Rujukan event yang enak dibaca: `E12` sw2: `bridge vlan show`."""
    e = by_id.get(event_id)
    return f"`{event_id}` {e['node']}: `{e['command']}`" if e else f"`{event_id}`"


def dimension_basis(result):
    """Kolom 'Dasar' di tabel skor: alasan singkat di balik tiap angka."""
    rule_based = result["rule_based"]
    verify, eff = rule_based["verify"], rule_based["efficiency"]
    violations = rule_based["safety"]["violations"]
    return {
        "correctness": "; ".join(verify["issues"]) or ("ping OK" if verify["ping_ok"] else "ping gagal"),
        "efficiency": f"{eff['state_changes']} perubahan (baseline {eff['baseline_changes']}), {eff['rework_changes']} rework",
        "methodology": result["llm"]["methodology"]["band"] if result["llm"] else "-",
        "safety": ", ".join(f"{v['id']} ({v['severity']})" for v in violations) or "tidak ada pelanggaran",
    }


def score_lines(result):
    final = result["final_score"]
    lines = [f"# Evaluasi {result['problem']} · sesi {result['session']}", ""]
    lines.append(f"**Skor akhir: {final}**" if final is not None
                 else "**Skor akhir: belum ada** (methodology butuh evaluator LLM)")
    lines += ["", "| Dimensi | Skor | Bobot | Dasar |", "|---|---|---|---|"]
    basis = dimension_basis(result)
    credited = result.get("credited", result["scores"])
    for dim in DIMENSIONS:
        score, given = result["scores"][dim], credited[dim]
        shown = "-" if score is None else (f"{score} → {given}" if given != score else f"{score}")
        lines.append(f"| {dim} | {shown} | {result['weights'][dim]:.0%} | {basis[dim]} |")
    gate = result["rule_based"].get("process_gate")
    if gate and gate["factor"] < 1:
        lines.append(f"\nProcess gate ×{gate['factor']}: {', '.join(gate['applies_to'])} hanya dikreditkan sebagian, "
                     f"karena checkpoint proses {gate['missing']} tidak tercapai sebelum `{gate['before']}`.")
    if gate and gate.get("waived"):
        lines.append(f"\nProcess gate tidak diterapkan: {gate['waived']}. Diagnosis di GUI tidak terekam, "
                     f"jadi checkpoint proses {gate['missing']} tidak bisa diperiksa.")
    gui = result["rule_based"].get("gui")
    if gui and gui["used"]:
        lines.append(f"\nMode GUI ({', '.join(gui['via']) or 'luar terminal'}): {len(gui['changes'])} perubahan "
                     "direkam dari konfigurasi router; aktivitas membaca di GUI tidak terekam.")
    hints = result["rule_based"]["hints"]
    if hints["levels_used"]:
        lines.append(f"\nPenalti hint: -{hints['penalty']} (level {hints['levels_used']})")
    return lines


def checkpoint_lines(result, describe):
    lines = ["", "## Checkpoint", ""]
    for cp in result["rule_based"]["checkpoints"]:
        lines.append(f"- {'✓' if cp['hit'] else '·'} `{cp['id']}`" + (f" pada {describe(cp['event'])}" if cp["event"] else ""))
    if result["llm"]:
        for cp in result["llm"]["llm_checkpoints"]:
            lines.append(f"- {'✓' if cp['hit'] else '·'} `{cp['id']}` (LLM): {cp['rationale']}")
    return lines


def feedback_lines(result, describe):
    feedback, methodology = result["llm"]["feedback"], result["llm"]["methodology"]
    lines = ["", "## Feedback", "", feedback["summary"], ""]
    if feedback["strengths"]:
        lines += ["**Yang sudah bagus**", ""] + [f"- {x}" for x in feedback["strengths"]] + [""]
    if feedback["improvements"]:
        lines += ["**Yang perlu diperbaiki**", ""] + [f"{i}. {x}" for i, x in enumerate(feedback["improvements"], 1)] + [""]
    if feedback["technical_lessons"]:
        lines += ["**Pelajaran teknis**", ""] + [f"- {x}" for x in feedback["technical_lessons"]] + [""]
    lines += ["**Momen penting**", ""] + [f"- {describe(k['event'])}: {k['note']}" for k in feedback["key_moments"]]
    lines += ["", f"**Latihan berikutnya:** {feedback['next_practice']}", "",
              "## Penilaian methodology", "", f"{methodology['band']} · {methodology['score']}", "", methodology["rationale"], ""]
    lines += [f"- {describe(x['event'])}: {x['note']}" for x in methodology["evidence"]]
    return lines


def report_md(session, result):
    describe = partial(describe_event, {e["id"]: e for e in session.timeline})
    lines = score_lines(result) + checkpoint_lines(result, describe)
    if result["llm"]:
        lines += feedback_lines(result, describe)
    if result.get("methodology_spread"):
        sp = result["methodology_spread"]
        lines += ["", f"_Methodology dari {len(sp['scores'])} run: {sp['scores']} (median {sp['median']})_"]
    if result["warnings"]:
        lines += ["", "## Peringatan evaluator", ""] + [f"- {x}" for x in result["warnings"]]
    return "\n".join(lines) + "\n"
