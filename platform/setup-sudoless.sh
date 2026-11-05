#!/usr/bin/env bash
# Setup sekali: containerlab tanpa sudo, supaya web UI bisa deploy/reset lab.
# Jalankan dengan sudo:  sudo platform/setup-sudoless.sh [user]
#
# Mekanisme bawaan containerlab (>= 0.62): binary setuid root yang hanya boleh
# dieksekusi anggota grup clab_admins. containerlab sendiri menolak user di luar
# grup itu. Konsekuensinya: anggota clab_admins praktis setara root lewat
# containerlab (sama seperti grup docker). Wajar untuk mesin pribadi satu user.
#
# Pacman hook memasang ulang izinnya setiap containerlab di-update, karena
# paket (containerlab-bin dari AUR) mengembalikan mode 755 root:root.
# Batalkan: sudo platform/setup-sudoless.sh --undo
set -euo pipefail

CLAB=$(command -v containerlab || true)
HOOK=/etc/pacman.d/hooks/containerlab-sudoless.hook

if (( EUID != 0 )); then
  echo "Jalankan dengan sudo: sudo $0 ${*:-}" >&2
  exit 1
fi

if [[ ${1:-} == --undo ]]; then
  chown root:root "$CLAB" && chmod 755 "$CLAB"
  rm -f "$HOOK"
  echo "containerlab kembali butuh sudo. Grup clab_admins dibiarkan (hapus: groupdel clab_admins)."
  exit 0
fi

[[ -n $CLAB ]] || { echo "containerlab belum terinstall." >&2; exit 1; }

TARGET_USER=${1:-${SUDO_USER:-}}
if [[ -z $TARGET_USER ]]; then
  echo "User tidak diketahui. Usage: sudo $0 <user>" >&2
  exit 1
fi

getent group clab_admins >/dev/null || groupadd -r clab_admins
usermod -aG clab_admins "$TARGET_USER"
chown root:clab_admins "$CLAB"
chmod 4750 "$CLAB"

if [[ -d /etc/pacman.d ]]; then
  mkdir -p "$(dirname "$HOOK")"
  cat > "$HOOK" <<EOF
[Trigger]
Operation = Install
Operation = Upgrade
Type = Path
Target = ${CLAB#/}

[Action]
Description = containerlab: setuid + grup clab_admins (P-lab)
When = PostTransaction
Exec = /bin/sh -c 'chown root:clab_admins $CLAB && chmod 4750 $CLAB'
EOF
fi

ls -l "$CLAB"
echo "Selesai. $TARGET_USER masuk grup clab_admins: logout lalu login lagi supaya grupnya aktif"
echo "(atau restart service: systemctl --user restart p-lab, setelah login ulang)."
