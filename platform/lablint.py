#!/usr/bin/env python3
"""Periksa sebuah lab sebelum dimainkan: problem.yaml, topologi, dan script soal.

  lablint.py <lab_dir> [<lab_dir> ...]     # exit 1 kalau ada error

Hanya pemeriksaan statis (tanpa docker). Yang dicek adalah kesalahan yang
biasanya baru ketahuan di tengah sesi: field wajib hilang, {{parameter}} yang
tidak didefinisikan, regex yang tidak valid, script tidak executable, bind
perekaman lupa dipasang, label link yang tidak cocok dengan topologi, dan
teks yang bisa membocorkan fault ke pemain. Referensi field: docs/membuat-lab.md.
"""

if __name__ == "__main__":
    import _venv  # noqa: E402  (Python venv, lihat _venv.py)
    _venv.ensure()

import os
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CATEGORIES = {"network-engineer", "network-admin", "cybersecurity"}
DIFFICULTIES = {"beginner", "intermediate", "advanced"}
MATCHERS = {"command_match", "state_check", "llm_judge"}
SEVERITIES = {"minor", "major"}
DIMENSIONS = {"correctness", "efficiency", "methodology", "safety"}
PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class Report:
    def __init__(self, lab_dir):
        self.lab_dir = lab_dir
        self.errors, self.warnings = [], []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def placeholders(value):
    """Semua nama {{x}} di dalam nilai YAML (rekursif)."""
    if isinstance(value, str):
        return set(PLACEHOLDER.findall(value))
    if isinstance(value, list):
        return set().union(*map(placeholders, value)) if value else set()
    if isinstance(value, dict):
        return set().union(*map(placeholders, value.values())) if value else set()
    return set()


def check_regex(report, where, pattern, params):
    # Regex dicek setelah {{parameter}} diganti, sama seperti saat sesi.
    rendered = PLACEHOLDER.sub(lambda m: str(params.get(m.group(1), "x")), pattern)
    try:
        re.compile(rendered)
    except re.error as error:
        report.error(f"{where}: regex tidak valid ({error}): {pattern}")


def check_script(report, lab_dir, name, role):
    path = lab_dir / name
    if not path.exists():
        report.error(f"{role} '{name}' tidak ada")
    elif not os.access(path, os.X_OK):
        report.error(f"{role} '{name}' tidak executable (chmod +x {name})")


def lint(lab_dir):
    lab_dir = Path(lab_dir).resolve()
    report = Report(lab_dir)
    problem_file = lab_dir / "problem.yaml"
    if not problem_file.exists():
        report.error("problem.yaml tidak ada")
        return report
    try:
        problem = yaml.safe_load(problem_file.read_text()) or {}
    except yaml.YAMLError as error:
        report.error(f"problem.yaml bukan YAML valid: {error}")
        return report

    # --- field utama
    for key in ("id", "title", "lab_topology", "checkpoints"):
        if not problem.get(key):
            report.error(f"field wajib '{key}' kosong atau tidak ada")
    lab_id = str(problem.get("id", ""))
    if lab_id and not re.fullmatch(r"[a-z0-9-]+", lab_id):
        report.error(f"id '{lab_id}' hanya boleh huruf kecil, angka, dan '-'")
    if problem.get("category") not in CATEGORIES:
        report.warn(f"category '{problem.get('category')}' bukan salah satu dari {sorted(CATEGORIES)}")
    if problem.get("difficulty") not in DIFFICULTIES:
        report.warn(f"difficulty '{problem.get('difficulty')}' bukan salah satu dari {sorted(DIFFICULTIES)}")
    nos = problem.get("nos", "linux-bridge")
    if not (HERE / "nos" / f"{nos}.yaml").exists():
        report.error(f"nos '{nos}' tidak punya aturan di platform/nos/{nos}.yaml")

    # --- {{parameter}}: semua yang dipakai harus didefinisikan
    params = problem.get("parameters") or {}
    used = placeholders({k: v for k, v in problem.items() if k != "parameters"})
    for name in sorted(used - set(params)):
        report.error(f"{{{{{name}}}}} dipakai tapi tidak ada di parameters")

    # --- file soal
    check_script(report, lab_dir, (problem.get("fault_injection") or {}).get("script", "inject.sh"), "inject script")
    check_script(report, lab_dir, (problem.get("goal_state") or {}).get("verify_script", "verify.sh"), "verify script")
    check_script(report, lab_dir, "reset.sh", "reset.sh")

    # --- topologi
    nodes, links = [], []
    topo_file = lab_dir / str(problem.get("lab_topology", ""))
    if problem.get("lab_topology") and not topo_file.is_file():
        report.error(f"lab_topology '{problem['lab_topology']}' tidak ada")
    elif topo_file.is_file():
        topo = yaml.safe_load(topo_file.read_text()) or {}
        if not topo_file.name.endswith(".clab.yaml"):
            report.error("file topologi harus berakhiran .clab.yaml (dicari lab-shell dan web UI)")
        if not topo.get("name"):
            report.error("topologi tidak punya 'name'")
        body = topo.get("topology") or {}
        nodes = list((body.get("nodes") or {}).keys())
        links = [tuple(l.get("endpoints", [])) for l in body.get("links") or []]
        binds = " ".join((body.get("defaults") or {}).get("binds") or [])
        if "/etc/lab/rc" not in binds:
            report.error("defaults.binds tidak memasang platform/lab-rc.sh:/etc/lab/rc (command tidak terekam)")
        if ".state/events:/var/log/lab" not in binds:
            report.error("defaults.binds tidak memasang .state/events:/var/log/lab (event tidak sampai ke host)")
        if (body.get("defaults") or {}).get("network-mode") != "none":
            report.warn("defaults.network-mode bukan 'none': node bisa saling menjangkau lewat jaringan management docker")
        for node in nodes:
            if not re.fullmatch(r"[a-z0-9-]+", node):
                report.error(f"nama node '{node}' hanya boleh huruf kecil, angka, dan '-' (lab-shell menolak)")

    brief = lab_dir / problem.get("brief", "brief.md")
    if not brief.exists():
        report.error(f"brief '{brief.name}' tidak ada")
    else:
        text = brief.read_text()
        if not text.lstrip().startswith("#"):
            report.warn("brief.md sebaiknya diawali judul '# Tiket ...: <judul>' (dipakai web UI)")
        visible = text.split("<!-- cli", 1)[0]
        for name, value in params.items():
            # Nilai parameter yang muncul di brief = petunjuk lokasi fault.
            # Nama node dikecualikan: daftar perangkat di brief itu wajar.
            if isinstance(value, str) and len(value) > 2 and value not in nodes and re.search(rf"\b{re.escape(value)}\b", visible):
                report.warn(f"brief menyebut nilai parameter {name}={value!r}; pastikan tidak membocorkan fault")

    # --- checkpoints
    ids = []
    checkpoints = problem.get("checkpoints") or []
    for i, cp in enumerate(checkpoints):
        where = f"checkpoint #{i + 1} ({cp.get('id', '?')})"
        cid = cp.get("id")
        if not cid:
            report.error(f"{where}: tidak punya id")
        elif cid in ids:
            report.error(f"{where}: id duplikat")
        ids.append(cid)
        kind = cp.get("type")
        if kind not in MATCHERS:
            report.error(f"{where}: type '{kind}' bukan salah satu dari {sorted(MATCHERS)}")
            continue
        if not cp.get("label"):
            report.warn(f"{where}: tidak punya label (web UI menampilkan id)")
        targets = [cp.get("node")] + [alt.get("node") for alt in cp.get("any_of") or []]
        for node in targets:
            if node and node != "any" and not PLACEHOLDER.search(str(node)) and nodes and node not in nodes:
                report.error(f"{where}: node '{node}' tidak ada di topologi")
        if kind == "command_match":
            patterns = [cp.get("pattern")] + [alt.get("pattern") for alt in cp.get("any_of") or []]
            if not any(patterns):
                report.error(f"{where}: command_match butuh pattern atau any_of")
            for pattern in filter(None, patterns):
                check_regex(report, where, pattern, params)
        elif kind == "state_check":
            if not cp.get("command") or not cp.get("expect_regex"):
                report.error(f"{where}: state_check butuh command dan expect_regex")
            else:
                check_regex(report, where, cp["expect_regex"], params)
            if not cp.get("node") or cp.get("node") == "any":
                report.error(f"{where}: state_check butuh satu node tertentu")
        elif kind == "llm_judge" and not cp.get("criteria"):
            report.error(f"{where}: llm_judge butuh criteria")
        if cp.get("after") and cp["after"] not in ids:
            report.error(f"{where}: after '{cp['after']}' harus checkpoint yang didefinisikan sebelumnya")

    # --- scoring
    scoring = problem.get("scoring") or {}
    weights = scoring.get("weights") or {}
    if weights:
        unknown = set(weights) - DIMENSIONS
        if unknown:
            report.error(f"scoring.weights punya dimensi tidak dikenal: {sorted(unknown)}")
        total = sum(weights.values())
        if abs(total - 1) > 0.001:
            report.error(f"scoring.weights berjumlah {total:g}, harus 1")
    gate = scoring.get("process_gate")
    if gate:
        for cid in list(gate.get("requires") or []) + [gate.get("before")]:
            if cid not in ids:
                report.error(f"process_gate menyebut checkpoint '{cid}' yang tidak ada")
    for rule in scoring.get("safety") or []:
        where = f"safety '{rule.get('id', '?')}'"
        if rule.get("severity") not in SEVERITIES:
            report.error(f"{where}: severity harus minor atau major")
        if not rule.get("pattern") and not rule.get("any_of"):
            report.error(f"{where}: butuh pattern dan/atau any_of")
        for pattern in [rule.get("pattern")] + [alt.get("key") for alt in rule.get("any_of") or []]:
            if pattern:
                check_regex(report, where, pattern, params)

    # --- hints
    levels = [h.get("level") for h in problem.get("hints") or []]
    if levels != list(range(1, len(levels) + 1)):
        report.error(f"hints: level harus berurutan mulai 1, ditemukan {levels}")
    for hint in problem.get("hints") or []:
        if not hint.get("text"):
            report.error(f"hint level {hint.get('level')}: text kosong")

    # --- desain (label link)
    link_keys = {" ".join(l) for l in links} | {" ".join(reversed(l)) for l in links}
    for key in ((problem.get("design") or {}).get("links") or {}):
        if links and key not in link_keys:
            report.error(f"design.links '{key}' tidak cocok dengan endpoints link mana pun di topologi")

    if not ((problem.get("ui") or {}).get("summary")):
        report.warn("ui.summary kosong (kartu lab di web UI tanpa deskripsi)")
    if not (lab_dir / "autoplay").is_dir() and not (lab_dir / "golden").is_dir():
        report.warn("belum ada autoplay/ atau golden/: evaluator belum bisa diuji untuk soal ini")
    return report


def main(argv):
    if not argv:
        sys.exit(__doc__.strip())
    failed = False
    for lab_dir in argv:
        report = lint(lab_dir)
        name = report.lab_dir.name
        for msg in report.errors:
            print(f"{name}: error: {msg}")
        for msg in report.warnings:
            print(f"{name}: peringatan: {msg}")
        if not report.errors:
            print(f"{name}: OK" + (f" ({len(report.warnings)} peringatan)" if report.warnings else ""))
        failed |= bool(report.errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
