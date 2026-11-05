#!/usr/bin/env bash
# Reset lab __ID__: destroy, deploy ulang, lalu inject fault. Jalankan tanpa sudo.
# Logikanya ada di platform/reset-lab (sama untuk semua lab).
# Usage: reset.sh [argumen inject.sh...]
exec "$(dirname "$0")/../../platform/reset-lab" "$(dirname "$0")" "$@"
