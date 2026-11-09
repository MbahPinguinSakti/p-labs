#!/usr/bin/env bash
# Inject fault net-003: MTU interface di satu sisi link OSPF diturunkan, sehingga
# adjacency macet di ExStart/Exchange (MTU di paket DBD tidak cocok).
# Usage: inject.sh [router] [port] [mtu] [peer]
set -euo pipefail
source "$(dirname "$0")/../../platform/labenv.sh"   # LAB_STATE_DIR, ctr, ros_exec
cd "$LAB_DIR"

ROUTER=${1:-r2}
PORT=${2:-ether3}
MTU=${3:-1400}
PEER=${4:-r3}      # router di ujung lain link (hanya dicatat untuk evaluator)
ros() { ros_exec "$@" | tr -d '\r'; }

ros "$ROUTER" "/interface ethernet set $PORT mtu=$MTU" >/dev/null
# Adjacency yang sudah Full tidak otomatis putus saat MTU berubah: flap interface
# supaya OSPF membangun ulang adjacency dengan MTU baru.
ros "$ROUTER" "/interface ethernet disable $PORT" >/dev/null
sleep 2
ros "$ROUTER" "/interface ethernet enable $PORT" >/dev/null

# Pastikan fault efektif: rute ke LAN-C hilang dari r1 dan host-b tak terjangkau.
for _ in $(seq 1 30); do
  if ! docker exec "$(ctr host-a)" ping -c 1 -W 1 10.30.0.10 >/dev/null 2>&1; then
    broken=1
    break
  fi
  sleep 2
done
if [[ -z ${broken:-} ]]; then
  echo "Fault tidak efektif: adjacency tetap terbentuk dengan MTU berbeda." >&2
  ros "$ROUTER" ':foreach n in=[/routing ospf neighbor find] do={:put ([/routing ospf neighbor get $n address] . " " . [/routing ospf neighbor get $n state])}' >&2 || true
  exit 1
fi

mkdir -p "$LAB_STATE_DIR"
cat > "$LAB_STATE_DIR/ground_truth.json" <<JSON
{"problem": "net-003", "router": "${ROUTER}", "port": "${PORT}", "mtu": ${MTU}, "peer": "${PEER}", "injected_at": "$(date -Is)"}
JSON
echo "Fault injected."
