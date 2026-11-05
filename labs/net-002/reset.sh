#!/usr/bin/env bash
# Reset lab net-002: destroy, deploy ulang, lalu inject fault. Jalankan tanpa sudo.
# Logikanya ada di platform/reset-lab. Router RouterOS butuh 1-3 menit untuk boot.
# Usage: reset.sh [router] [port] [prefix]
exec "$(dirname "$0")/../../platform/reset-lab" "$(dirname "$0")" "$@"
