#!/usr/bin/env bash
# Inject fault net-001: hapus VLAN dari allowed list sebuah trunk port.
# Usage: inject.sh [faulty_switch] [trunk_port] [vlan_id]
set -euo pipefail

LAB=net001
SW=${1:-sw2}
PORT=${2:-eth2}
VLAN=${3:-20}

docker exec "clab-${LAB}-${SW}" bridge vlan del dev "$PORT" vid "$VLAN"

# Ground truth untuk evaluator. Jangan ditunjukkan ke user.
mkdir -p "$(dirname "$0")/.state"
cat > "$(dirname "$0")/.state/ground_truth.json" <<EOF
{"problem": "net-001", "faulty_switch": "${SW}", "trunk_port": "${PORT}", "vlan_id": ${VLAN}, "injected_at": "$(date -Is)"}
EOF

echo "Fault injected."
