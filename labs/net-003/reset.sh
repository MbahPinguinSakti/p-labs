#!/usr/bin/env bash
# Reset lab net-003: destroy, deploy ulang, lalu inject fault. Jalankan tanpa sudo.
# Logikanya ada di platform/reset-lab. Tiga router RouterOS + konvergensi OSPF: 2-4 menit.
# Usage: reset.sh [router] [port] [mtu] [peer]
exec "$(dirname "$0")/../../platform/reset-lab" "$(dirname "$0")" "$@"
