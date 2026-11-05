#!/usr/bin/env bash
# Inject fault __ID__: lepas sebuah port dari bridge.
# Usage: inject.sh [switch] [port]   (default dari problem.yaml: parameters)
#
# Kontrak (docs/membuat-lab.md):
# - dipanggil reset-lab setelah verify.sh menyatakan lab sehat;
# - menulis .state/ground_truth.json berisi nilai fault yang SEBENARNYA dipakai;
# - output-nya tidak ditampilkan ke pemain, tapi tetap jangan mencetak lokasi fault.
set -euo pipefail

LAB=__CLAB_NAME__
SW=${1:-sw1}
PORT=${2:-eth2}

docker exec "clab-${LAB}-${SW}" ip link set "$PORT" nomaster

mkdir -p "$(dirname "$0")/.state"
cat > "$(dirname "$0")/.state/ground_truth.json" <<JSON
{"problem": "__ID__", "switch": "${SW}", "port": "${PORT}", "injected_at": "$(date -Is)"}
JSON

echo "Fault injected."
