#!/usr/bin/env bash
# Reset lab net-001: destroy, deploy ulang, lalu inject fault.
# Jalankan tanpa sudo. Logikanya ada di platform/reset-lab (sama untuk semua lab).
# Usage: reset.sh [faulty_switch] [trunk_port] [vlan_id]
exec "$(dirname "$0")/../../platform/reset-lab" "$(dirname "$0")" "$@"
