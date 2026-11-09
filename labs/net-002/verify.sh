#!/usr/bin/env bash
# Verify net-002. Output JSON ke stdout (baris terakhir):
#   correctness 100 = host-a <-> host-b jalan dan desain utuh
#   correctness  50 = jalan, tapi lewat tambalan yang merusak desain:
#                     IP server diubah, rute host /32, prefix LAN-B bukan /24, dsb.
#   correctness   0 = belum jalan
# Exit code: 0 jika 100, 1 selain itu, 2 jika lab tidak bisa diakses.
set -uo pipefail
source "$(dirname "$0")/../../platform/labenv.sh"   # LAB_STATE_DIR, ctr, ros_exec
cd "$LAB_DIR"

c() { ctr "$1"; }
ros() { ros_exec "$@" 2>/dev/null | tr -d '\r'; }
fail() { printf '{"problem": "net-002", "error": "%s"}\n' "$1"; exit 2; }

docker info >/dev/null 2>&1 || fail "Docker tidak bisa diakses"
for n in r1 r2 host-a host-b; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$(c "$n")" 2>/dev/null)" == "true" ]] \
    || fail "Container $(c "$n") tidak berjalan (sudah ./reset.sh?)"
done
for r in r1 r2; do
  [[ "$(ros "$r" ':put ok')" == ok* ]] || fail "RouterOS di $r belum bisa diakses lewat SSH (masih booting?)"
done

issues=()
ping_ok=true
docker exec "$(c host-a)" ping -c 3 -W 1 10.20.0.130 >/dev/null 2>&1 || ping_ok=false
docker exec "$(c host-b)" ping -c 3 -W 1 10.10.0.10 >/dev/null 2>&1 || ping_ok=false

# Alamat host tidak boleh diubah (server sudah sesuai desain).
[[ "$(docker exec "$(c host-a)" ip -br -4 addr show eth1 | awk '{print $3}')" == "10.10.0.10/24" ]] \
  || issues+=("host-a: alamat eth1 berubah dari 10.10.0.10/24")
[[ "$(docker exec "$(c host-b)" ip -br -4 addr show eth1 | awk '{print $3}')" == "10.20.0.130/24" ]] \
  || issues+=("host-b: alamat eth1 berubah dari 10.20.0.130/24")

# Alamat router per interface: tepat satu alamat, sesuai desain.
addrs() { ros "$1" ":foreach a in=[/ip address find where interface=$2] do={:put [/ip address get \$a address]}" | xargs; }
check_addr() {
  local got; got=$(addrs "$1" "$2")
  [[ "$got" == "$3" ]] || issues+=("$1 $2: alamat '${got:-kosong}', desain $3")
}
check_addr r1 ether2 10.10.0.1/24
check_addr r1 ether3 10.0.12.1/30
check_addr r2 ether2 10.0.12.2/30
check_addr r2 ether3 10.20.0.1/24

# Rute statis tetap persis desain: tidak ada tambalan /32 atau default route.
routes() { ros "$1" ':foreach r in=[/ip route find where static] do={:put [/ip route get $r dst-address]}' | grep -v '^$' | sort | xargs; }
[[ "$(routes r1)" == "10.20.0.0/24" ]] || issues+=("r1: rute statis '$(routes r1)', desain hanya 10.20.0.0/24")
[[ "$(routes r2)" == "10.10.0.0/24" ]] || issues+=("r2: rute statis '$(routes r2)', desain hanya 10.10.0.0/24")

if ! $ping_ok; then score=0; elif (( ${#issues[@]} == 0 )); then score=100; else score=50; fi

python3 - "$score" "$ping_ok" "${issues[@]}" <<'PY'
import json, sys
score, ping_ok, *issues = sys.argv[1:]
print(json.dumps({"problem": "net-002", "correctness": int(score), "ping_ok": ping_ok == "true", "issues": issues}))
PY

[[ "$score" == "100" ]]
