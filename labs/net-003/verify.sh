#!/usr/bin/env bash
# Verify net-003. Output JSON ke stdout (baris terakhir):
#   correctness 100 = host-a <-> host-b jalan lewat OSPF dan desain utuh
#   correctness  50 = jalan, tapi lewat tambalan yang merusak desain:
#                     rute statis, MTU link bukan 1500 (mis. kedua sisi diturunkan),
#                     adjacency OSPF tidak lengkap, alamat host diubah, dsb.
#   correctness   0 = belum jalan
# Exit code: 0 jika 100, 1 selain itu, 2 jika lab tidak bisa diakses.
set -uo pipefail
source "$(dirname "$0")/../../platform/labenv.sh"   # LAB_STATE_DIR, ctr, ros_exec
cd "$LAB_DIR"

c() { ctr "$1"; }
ros() { ros_exec "$@" 2>/dev/null | tr -d '\r'; }
fail() { printf '{"problem": "net-003", "error": "%s"}\n' "$1"; exit 2; }

docker info >/dev/null 2>&1 || fail "Docker tidak bisa diakses"
for n in r1 r2 r3 host-a host-b; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$(c "$n")" 2>/dev/null)" == "true" ]] \
    || fail "Container $(c "$n") tidak berjalan (sudah ./reset.sh?)"
done
for r in r1 r2 r3; do
  [[ "$(ros "$r" ':put ok')" == ok* ]] || fail "RouterOS di $r belum bisa diakses lewat SSH (masih booting?)"
done

issues=()
ping_ok=true
docker exec "$(c host-a)" ping -c 3 -W 1 10.30.0.10 >/dev/null 2>&1 || ping_ok=false
docker exec "$(c host-b)" ping -c 3 -W 1 10.10.0.10 >/dev/null 2>&1 || ping_ok=false

[[ "$(docker exec "$(c host-a)" ip -br -4 addr show eth1 | awk '{print $3}')" == "10.10.0.10/24" ]] \
  || issues+=("host-a: alamat eth1 berubah dari 10.10.0.10/24")
[[ "$(docker exec "$(c host-b)" ip -br -4 addr show eth1 | awk '{print $3}')" == "10.30.0.10/24" ]] \
  || issues+=("host-b: alamat eth1 berubah dari 10.30.0.10/24")

# MTU desain 1500 di semua interface data.
for r in r1 r2 r3; do
  for ifc in ether2 ether3; do
    mtu=$(ros "$r" ":put [/interface get $ifc mtu]" | xargs)
    [[ "$mtu" == "1500" ]] || issues+=("$r $ifc: MTU ${mtu:-tidak terbaca}, desain 1500")
  done
done

# Adjacency OSPF lengkap: r1-r2 dan r2-r3 Full.
full() { ros "$1" ':foreach n in=[/routing ospf neighbor find] do={:put ([/routing ospf neighbor get $n address] . " " . [/routing ospf neighbor get $n state])}' \
  | awk -v a="$2" '$1 == a {print $2}'; }
[[ "$(full r1 10.0.12.2)" == Full ]] || issues+=("OSPF r1-r2 tidak Full")
[[ "$(full r2 10.0.12.1)" == Full ]] || issues+=("OSPF r2-r1 tidak Full")
[[ "$(full r2 10.0.23.2)" == Full ]] || issues+=("OSPF r2-r3 tidak Full")
[[ "$(full r3 10.0.23.1)" == Full ]] || issues+=("OSPF r3-r2 tidak Full")

# Routing desain murni OSPF: tidak ada rute statis.
for r in r1 r2 r3; do
  static=$(ros "$r" ':foreach x in=[/ip route find where static] do={:put [/ip route get $x dst-address]}' | grep -v '^$' | xargs)
  [[ -z $static ]] || issues+=("$r: ada rute statis ($static), desain hanya OSPF")
done

if ! $ping_ok; then score=0; elif (( ${#issues[@]} == 0 )); then score=100; else score=50; fi

python3 - "$score" "$ping_ok" "${issues[@]}" <<'PY'
import json, sys
score, ping_ok, *issues = sys.argv[1:]
print(json.dumps({"problem": "net-003", "correctness": int(score), "ping_ok": ping_ok == "true", "issues": issues}))
PY

[[ "$score" == "100" ]]
