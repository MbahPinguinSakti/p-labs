#!/usr/bin/env bash
# Inject fault net-002: prefix alamat LAN-B di router dipersempit (mis. /24 → /25),
# sehingga server dengan alamat di paruh atas subnet tidak lagi "terhubung langsung".
# Usage: inject.sh [router] [port] [prefix]
set -euo pipefail
source "$(dirname "$0")/../../platform/labenv.sh"   # LAB_STATE_DIR, ctr, ros_exec
cd "$LAB_DIR"

ROUTER=${1:-r2}
PORT=${2:-ether3}
PREFIX=${3:-25}
ros() { ros_exec "$@" >/dev/null; }

ros "$ROUTER" "/ip address set [find interface=$PORT] address=10.20.0.1/$PREFIX"

# Pastikan fault benar-benar efektif: jalur host-a → host-b harus putus.
# RouterOS memperbarui rute connected sesaat setelah `set` selesai, jadi ping
# pertama bisa masih lolos: ulangi beberapa kali sebelum menyatakan gagal.
for _ in $(seq 1 10); do
  if ! docker exec "$(ctr host-a)" ping -c 1 -W 1 10.20.0.130 >/dev/null 2>&1; then
    broken=1
    break
  fi
  sleep 1
done
if [[ -z ${broken:-} ]]; then
  echo "Fault tidak efektif: host-b masih terjangkau setelah inject." >&2
  exit 1
fi

mkdir -p "$LAB_STATE_DIR"
cat > "$LAB_STATE_DIR/ground_truth.json" <<JSON
{"problem": "net-002", "router": "${ROUTER}", "port": "${PORT}", "prefix": ${PREFIX}, "injected_at": "$(date -Is)"}
JSON
echo "Fault injected."
