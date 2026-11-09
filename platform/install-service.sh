#!/usr/bin/env bash
# Pasang web UI P-lab sebagai service systemd user (jalan otomatis saat login)
# dan ikon "P-lab" di menu aplikasi. Tidak butuh sudo.
# Usage: platform/install-service.sh [--uninstall]
#        sudo platform/install-service.sh --system [--uninstall]   (mode Server)
#
#   ~/.config/systemd/user/p-lab.service   menjalankan platform/web
#   ~/.config/p-lab/web.env                env LLM (tidak ditimpa kalau sudah ada)
#   ~/.local/share/applications/p-lab.desktop
# Log server: journalctl --user -u p-lab -f
#
# --system (mode Server, butuh root, dipanggil install.sh --server):
#   /etc/systemd/system/p-lab.service   User=plab, LAB_CONFIG=/etc/p-lab/server.yaml
# Hanya menulis unit + daemon-reload; TIDAK enable dan TIDAK menyalakan (kalau di-enable,
# setelah reboot server terbuka di 0.0.0.0 sebelum check/migrate). install.sh --server
# --migrate yang menjalankan `enable --now`, setelah config diisi dan pre-flight lolos. Alamat/port dibaca dari
# config. Env LLM server: /etc/p-lab/web.env (opsional, mode 600, milik root).
# Untuk test: P_LAB_UNIT_DIR=<folder> menulis unit ke folder itu tanpa systemctl.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# Nilai di baris unit systemd: % dan $ digandakan, \ dan " di-escape, lalu dikutip
# (path dengan spasi tidak pecah jadi beberapa argumen).
unit_quote() { local v=${1//\\/\\\\}; v=${v//\"/\\\"}; v=${v//%/%%}; v=${v//\$/\$\$}; printf '"%s"' "$v"; }
UNIT=~/.config/systemd/user/p-lab.service
ENVFILE=~/.config/p-lab/web.env
DESKTOP=~/.local/share/applications/p-lab.desktop

if [[ ${1:-} == --system ]]; then
  SYS_UNIT_DIR=${P_LAB_UNIT_DIR:-/etc/systemd/system}
  SYS_UNIT=$SYS_UNIT_DIR/p-lab.service
  CONF=${LAB_CONFIG:-/etc/p-lab/server.yaml}
  USE_SYSTEMCTL=1; [[ -n ${P_LAB_UNIT_DIR:-} ]] && USE_SYSTEMCTL=0
  if [[ ${2:-} == --uninstall ]]; then
    (( USE_SYSTEMCTL )) && systemctl disable --now p-lab.service 2>/dev/null || true
    rm -f "$SYS_UNIT"
    (( USE_SYSTEMCTL )) && systemctl daemon-reload
    echo "Unit system p-lab dihapus ($CONF dan data_dir dibiarkan)."
    exit 0
  fi
  (( USE_SYSTEMCTL )) && (( EUID != 0 )) && { echo "Jalankan dengan sudo: sudo $0 --system" >&2; exit 1; }
  PY=$ROOT/.venv/bin/python
  # host/port dari config; config tidak valid = berhenti, jangan menulis unit yang gagal start
  LISTEN=$(LAB_CONFIG=$CONF PYTHONDONTWRITEBYTECODE=1 "$PY" -c \
    'import sys; sys.path.insert(0, sys.argv[1]); import config; c = config.load(); print(c.host, c.port)' \
    "$ROOT/platform") || { echo "Config tidak valid: $CONF" >&2; exit 1; }
  read -r HOST PORT <<<"$LISTEN"
  # Grup tambahan hanya yang ada (nama grup yang tidak ada membuat unit gagal start).
  GROUPS_OK=()
  for g in docker clab_admins kvm; do getent group "$g" >/dev/null && GROUPS_OK+=("$g"); done
  mkdir -p "$SYS_UNIT_DIR"
  cat > "$SYS_UNIT" <<UNIT
[Unit]
Description=P-lab web UI (mode Server, $HOST:$PORT)
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
User=plab
Group=plab
SupplementaryGroups=${GROUPS_OK[*]}
Environment=$(unit_quote "LAB_CONFIG=$CONF")
Environment=HOME=/var/lib/p-lab
EnvironmentFile=-/etc/p-lab/web.env
ExecStart=$(unit_quote "$ROOT/platform/web") --host $HOST --port $PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
  if (( USE_SYSTEMCTL )); then
    systemctl daemon-reload
  fi
  echo "Unit system ditulis: $SYS_UNIT (belum di-enable/dinyalakan)."
  exit 0
fi

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
ExecStart=$(unit_quote "$ROOT/platform/web") --port 8000
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
