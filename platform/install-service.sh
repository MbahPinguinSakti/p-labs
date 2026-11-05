#!/usr/bin/env bash
# Pasang web UI P-lab sebagai service systemd user (jalan otomatis saat login)
# dan ikon "P-lab" di menu aplikasi. Tidak butuh sudo.
# Usage: platform/install-service.sh [--uninstall]
#
#   ~/.config/systemd/user/p-lab.service   menjalankan platform/web
#   ~/.config/p-lab/web.env                env LLM (tidak ditimpa kalau sudah ada)
#   ~/.local/share/applications/p-lab.desktop
# Log server: journalctl --user -u p-lab -f
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
UNIT=~/.config/systemd/user/p-lab.service
ENVFILE=~/.config/p-lab/web.env
DESKTOP=~/.local/share/applications/p-lab.desktop

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now p-lab.service 2>/dev/null || true
  rm -f "$UNIT" "$DESKTOP"
  systemctl --user daemon-reload
  echo "Service dan ikon dihapus ($ENVFILE dibiarkan)."
  exit 0
fi

mkdir -p "$(dirname "$UNIT")" "$(dirname "$ENVFILE")" "$(dirname "$DESKTOP")"

cat > "$UNIT" <<UNIT
[Unit]
Description=P-lab web UI (http://localhost:8000)

[Service]
EnvironmentFile=-$ENVFILE
ExecStart=$ROOT/platform/web --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
UNIT

# Hanya path ke file key yang ditulis, bukan isi key-nya.
if [[ ! -f $ENVFILE ]]; then
  if [[ -r ~/.config/lab/9router.key ]]; then
    cat > "$ENVFILE" <<ENV
LAB_LLM_PROVIDER=9router
LAB_LLM_MODEL=ag/claude-sonnet-4-6
LAB_LLM_API_KEY_FILE=$HOME/.config/lab/9router.key
ENV
  else
    cat > "$ENVFILE" <<'ENV'
# Provider LLM untuk "Nilai dengan AI" (lihat platform/llm/README.md), contoh:
# LAB_LLM_PROVIDER=anthropic
# LAB_LLM_API_KEY_FILE=/home/<user>/.config/lab/anthropic.key
ENV
  fi
  chmod 600 "$ENVFILE"
fi

cat > "$DESKTOP" <<DESKTOP
[Desktop Entry]
Type=Application
Name=P-lab
Comment=Lab troubleshooting jaringan
Exec=sh -c 'systemctl --user start p-lab.service; sleep 1; xdg-open http://localhost:8000'
Icon=$ROOT/web/public/favicon.svg
Terminal=false
Categories=Education;Network;
DESKTOP

systemctl --user daemon-reload
systemctl --user enable p-lab.service
systemctl --user restart p-lab.service   # restart: update kode ikut terpakai
echo "P-lab jalan di http://localhost:8000 dan akan start otomatis saat login."
echo "Env LLM: $ENVFILE · log: journalctl --user -u p-lab -f"
