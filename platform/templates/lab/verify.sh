#!/usr/bin/env bash
# Verify __ID__. Kontrak (docs/membuat-lab.md):
#   stdout baris terakhir = JSON {"problem", "correctness": 0|50|100, ...}
#   correctness 100 = masalah selesai dan desain utuh
#   correctness  50 = masalah selesai lewat "fix" yang merusak desain
#   correctness   0 = masalah belum selesai
#   exit 0 jika 100, 1 selain itu, 2 jika lab tidak bisa diakses (bukan hasil penilaian)
set -uo pipefail

LAB=__CLAB_NAME__
c() { echo "clab-${LAB}-$1"; }
fail() { printf '{"problem": "__ID__", "error": "%s"}\n' "$1"; exit 2; }

docker info >/dev/null 2>&1 || fail "Docker tidak bisa diakses"
for n in host-a host-b sw1; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$(c "$n")" 2>/dev/null)" == "true" ]] \
    || fail "Container $(c "$n") tidak berjalan (sudah ./reset.sh?)"
done

issues=()
if docker exec "$(c host-a)" ping -c 3 -W 1 10.0.0.2 >/dev/null 2>&1; then ping_ok=true; else ping_ok=false; fi

# Desain: kedua port tetap anggota br0 (fix lewat menghubungkan kabel lain = merusak desain).
members=$(docker exec "$(c sw1)" ip -br link show master br0 2>/dev/null | awk '{print $1}' | cut -d@ -f1 | sort | tr '\n' ' ')
[[ "$members" == "eth1 eth2 " ]] || issues+=("sw1: anggota br0 = ${members:-kosong}")

if ! $ping_ok; then score=0; elif (( ${#issues[@]} == 0 )); then score=100; else score=50; fi

python3 - "$score" "$ping_ok" "${issues[@]}" <<'PY'
import json, sys
score, ping_ok, *issues = sys.argv[1:]
print(json.dumps({"problem": "__ID__", "correctness": int(score), "ping_ok": ping_ok == "true", "issues": issues}))
PY

[[ "$score" == "100" ]]
