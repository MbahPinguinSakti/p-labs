#!/usr/bin/env bash
# Inject fault __ID__: lepas sebuah port dari bridge.
# Usage: inject.sh [switch] [port]   (default dari problem.yaml: parameters)
#
# Kontrak (docs/membuat-lab.md):
# - dipanggil reset-lab setelah verify.sh menyatakan lab sehat;
# - menulis $LAB_STATE_DIR/ground_truth.json berisi nilai fault yang SEBENARNYA dipakai;
# - menunjuk container lewat `ctr <node>` (labenv.sh), bukan clab-<nama>-<node>:
#   tiap instance (user) punya nama lab sendiri;
# - output-nya tidak ditampilkan ke pemain, tapi tetap jangan mencetak lokasi fault.
set -euo pipefail
source "$(dirname "$0")/../../platform/labenv.sh"   # LAB_STATE_DIR, ctr <node>

SW=${1:-sw1}
PORT=${2:-eth2}

docker exec "$(ctr "$SW")" ip link set "$PORT" nomaster

mkdir -p "$LAB_STATE_DIR"
cat > "$LAB_STATE_DIR/ground_truth.json" <<JSON
{"problem": "__ID__", "switch": "${SW}", "port": "${PORT}", "injected_at": "$(date -Is)"}
JSON

echo "Fault injected."
