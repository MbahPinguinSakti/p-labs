#!/usr/bin/env bash
# Inject fault net-002: prefix alamat LAN-B di router dipersempit (mis. /24 → /25),
# sehingga server dengan alamat di paruh atas subnet tidak lagi "terhubung langsung".
# Usage: inject.sh [router] [port] [prefix]
set -euo pipefail
cd "$(dirname "$0")"

ROUTER=${1:-r2}
PORT=${2:-ether3}
PREFIX=${3:-25}
PY=../../.venv/bin/python; [[ -x $PY ]] || PY=python3
ros() { "$PY" ../../platform/ros.py exec . "$@" >/dev/null; }

ros "$ROUTER" "/ip address set [find interface=$PORT] address=10.20.0.1/$PREFIX"

# Pastikan fault benar-benar efektif: jalur host-a → host-b harus putus.
if docker exec clab-net002-host-a ping -c 2 -W 1 10.20.0.130 >/dev/null 2>&1; then
  echo "Fault tidak efektif: host-b masih terjangkau setelah inject." >&2
  exit 1
fi

mkdir -p .state
cat > .state/ground_truth.json <<JSON
{"problem": "net-002", "router": "${ROUTER}", "port": "${PORT}", "prefix": ${PREFIX}, "injected_at": "$(date -Is)"}
JSON
echo "Fault injected."
