"""Penilaian deterministik (tanpa LLM): efficiency, safety, hint, skor akhir.

Rumus mengikuti rencana.md bagian 4. Konfigurasi per soal ada di problem.yaml
bagian `scoring`; nilai default di sini.
"""

import re

DEFAULT_WEIGHTS = {"correctness": 0.4, "efficiency": 0.2, "methodology": 0.3, "safety": 0.1}
EXTRA_CHANGE_PENALTY = 15
REWORK_PENALTY = 10
SAFETY_PENALTY = {"minor": 25, "major": 50}


def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def efficiency(timeline, baseline_changes):
    changes = [e for e in timeline if e["state_change"]]
    n_changes = sum(len(e["state_change"]) for e in changes)
    n_rework = sum(len(e["rework"]) for e in changes)
    extra = max(0, n_changes - baseline_changes)
    return {
        "score": clamp(100 - EXTRA_CHANGE_PENALTY * extra - REWORK_PENALTY * n_rework),
        "state_changes": n_changes,
        "baseline_changes": baseline_changes,
        "extra_changes": extra,
        "rework_changes": n_rework,
        "change_events": [e["id"] for e in changes],
    }


def _rule_hits(rule, entry):
    """Apakah satu perubahan state di timeline melanggar rule?"""
    if rule.get("node") not in (None, "any", entry["node"]):
        return False
    if "pattern" in rule and not re.search(rule["pattern"], entry["command"]):
        return False
    if "key" in rule and not any(re.search(rule["key"], k) for k in entry["state_change"]):
        return False
    return True


def safety(timeline, rules):
    """Pelanggaran dihitung per rule unik: mengulang kesalahan yang sama tidak
    menambah penalti, tapi semua event pemicunya dicatat sebagai bukti."""
    violations = []
    for rule in rules:
        # Syarat di level rule (node/pattern/key) berlaku untuk semua alternatif any_of.
        alts = rule.get("any_of") or [{}]
        events = [e["id"] for e in timeline if e["state_change"] and _rule_hits(rule, e)
                  and any(_rule_hits(alt, e) for alt in alts)]
        if events:
            violations.append({"id": rule["id"], "severity": rule["severity"],
                               "reason": rule["reason"], "events": events})
    penalty = sum(SAFETY_PENALTY[v["severity"]] for v in violations)
    return {"score": clamp(100 - penalty), "violations": violations}


def hint_penalty(events, hints):
    by_level = {h["level"]: h.get("penalty", 0) for h in hints}
    used = sorted({ev["level"] for ev in events if ev.get("type") == "hint"})
    return {"levels_used": used, "penalty": sum(by_level.get(lvl, 0) for lvl in used)}


def process_gate(checkpoints, config):
    """Kredit hasil sebanding dengan bukti proses SEBELUM fix.

    Tanpa gate, sesi "nyontek" (langsung fix tanpa diagnosis) mendapat
    correctness + efficiency sempurna dan mengalahkan pemain jujur yang
    berantakan. Di lab belajar, hasil tanpa proses yang teramati bukan bukti
    kemampuan.

    checkpoints: [{id, hit, ts}] dari checkpoint rule-based.
    config (problem.yaml scoring.process_gate):
      requires:   checkpoint proses yang harus tercapai
      before:     checkpoint fix; proses harus terjadi sebelum ini (opsional)
      applies_to: dimensi yang dikalikan faktor (default correctness, efficiency)
    factor = jumlah `requires` yang terpenuhi / jumlah `requires`.
    """
    if not config or not config.get("requires"):
        return {"factor": 1.0, "required": [], "met": [], "missing": [], "applies_to": []}
    by_id = {c["id"]: c for c in checkpoints}
    fix = by_id.get(config.get("before"))
    deadline = fix["ts"] if fix and fix["hit"] else float("inf")
    met = [cid for cid in config["requires"]
           if by_id.get(cid, {}).get("hit") and by_id[cid]["ts"] <= deadline]
    return {
        "factor": round(len(met) / len(config["requires"]), 3),
        "required": list(config["requires"]),
        "before": config.get("before"),
        "met": met,
        "missing": [cid for cid in config["requires"] if cid not in met],
        "applies_to": list(config.get("applies_to", ["correctness", "efficiency"])),
    }


def credited(dimensions, gate):
    """Skor yang masuk ke skor akhir: dimensi di applies_to dikali faktor gate."""
    return {k: (None if v is None else
                round(v * gate["factor"], 1) if k in gate["applies_to"] else v)
            for k, v in dimensions.items()}


def final_score(dimensions, weights, hint_pen):
    """dimensions: {nama: skor atau None}. None (mis. methodology tanpa LLM) =
    skor akhir belum bisa dihitung."""
    if any(dimensions.get(k) is None for k in weights):
        return None
    raw = sum(weights[k] * dimensions[k] for k in weights)
    return round(max(0, raw - hint_pen), 1)
