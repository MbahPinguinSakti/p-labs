#!/usr/bin/env bash
# Verify net-001. Output JSON ke stdout:
#   correctness 100 = ping jalan dan desain VLAN tetap utuh
#   correctness  50 = ping jalan tapi lewat "fix" yang merusak desain
#                     (vlan_filtering dimatikan, VLAN 10 hilang dari trunk,
#                     management VLAN 10 antar-switch putus, VLAN lain bocor
#                     ke port akses host, dsb.)
#   correctness   0 = ping masih gagal
# Exit code: 0 jika correctness 100, 1 selain itu, 2 jika lab tidak bisa diakses.
set -uo pipefail
source "$(dirname "$0")/../../platform/labenv.sh"   # LAB_STATE_DIR, ctr <node>
c() { ctr "$1"; }

# Preflight: jangan keluarkan skor jika lab tidak bisa diakses sama sekali.
# Exit code 2 = error lingkungan, bukan hasil penilaian.
fail() { printf '{"problem": "net-001", "error": "%s"}\n' "$1"; exit 2; }
docker info >/dev/null 2>&1 \
  || fail "Docker tidak bisa diakses (cek grup docker atau jalankan dengan sudo)"
for n in host-a host-b sw1 sw2 sw3; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$(c "$n")" 2>/dev/null)" == "true" ]] \
    || fail "Container $(c "$n") tidak berjalan (sudah ./reset.sh?)"
done

issues=()

if docker exec "$(c host-a)" ping -c 3 -W 1 10.20.0.2 >/dev/null 2>&1; then
  ping_ok=true
else
  ping_ok=false
fi

for sw in sw1 sw2 sw3; do
  vf=$(docker exec "$(c "$sw")" cat /sys/class/net/br0/bridge/vlan_filtering 2>/dev/null || echo missing)
  [[ "$vf" == "1" ]] || issues+=("${sw}: vlan_filtering=${vf}")
done

# Trunk harus tetap membawa VLAN 10 dan 20, tanpa VLAN 1.
trunks=("sw1 eth2" "sw2 eth1" "sw2 eth2" "sw3 eth1")
for t in "${trunks[@]}"; do
  read -r sw port <<<"$t"
  vids=$(docker exec "$(c "$sw")" bridge -j vlan show dev "$port" 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(" ".join(str(v["vlan"]) for e in d for v in e.get("vlans",[])))' 2>/dev/null || echo "")
  for need in 10 20; do
    [[ " $vids " == *" $need "* ]] || issues+=("${sw}:${port} tidak membawa VLAN ${need}")
  done
  [[ " $vids " == *" 1 "* ]] && issues+=("${sw}:${port} membawa VLAN 1")
done

# Port akses ke host: tepat VLAN 20 saja, sebagai PVID dan untagged.
# VLAN lain di port akses (mis. VLAN 10 management) = bocor ke sisi user.
access=("sw1 eth1" "sw3 eth2")
for a in "${access[@]}"; do
  read -r sw port <<<"$a"
  state=$(docker exec "$(c "$sw")" bridge -j vlan show dev "$port" 2>/dev/null \
    | python3 -c '
import json, sys
vlans = [v for e in json.load(sys.stdin) for v in e.get("vlans", [])]
ids = sorted(v["vlan"] for v in vlans)
flags = set(next((v.get("flags", []) for v in vlans if v["vlan"] == 20), []))
print("ok" if ids == [20] and {"PVID", "Egress Untagged"} <= flags else "vlans=%s flags20=%s" % (ids, sorted(flags)))
' 2>/dev/null || echo "tidak terbaca")
  [[ "$state" == "ok" ]] || issues+=("${sw}:${port} (port akses) bukan access VLAN 20 murni: ${state}")
done

# VLAN management (10) harus tetap jalan ujung ke ujung, lewat sw2.
for target in 10.10.0.12 10.10.0.13; do
  docker exec "$(c sw1)" ping -c 2 -W 1 "$target" >/dev/null 2>&1 \
    || issues+=("mgmt VLAN 10: sw1 tidak bisa menjangkau ${target}")
done

if ! $ping_ok; then
  score=0
elif (( ${#issues[@]} == 0 )); then
  score=100
else
  score=50
fi

python3 - "$score" "$ping_ok" "${issues[@]}" <<'EOF'
import json, sys
score, ping_ok, *issues = sys.argv[1:]
print(json.dumps({"problem": "net-001", "correctness": int(score),
                  "ping_ok": ping_ok == "true", "issues": issues}))
EOF

[[ "$score" == "100" ]]
