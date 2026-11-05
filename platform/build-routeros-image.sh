#!/usr/bin/env bash
# Bangun image container MikroTik RouterOS untuk lab P-lab (sekali saja).
# Usage: platform/build-routeros-image.sh [versi]    (default: versi yang dipakai labs/)
#
# RouterOS tidak punya image container resmi untuk x86. Lab memakai CHR
# (Cloud Hosted Router, image VM resmi MikroTik) yang dibungkus vrnetlab menjadi
# container: QEMU/KVM di dalam container, didukung containerlab sebagai kind
# `mikrotik_ros`. Script ini:
#   1. mengambil vrnetlab (github.com/srl-labs/vrnetlab) ke ~/.cache/p-lab/vrnetlab
#   2. mengunduh chr-<versi>.vmdk dari download.mikrotik.com
#   3. `make docker-image` → vrnetlab/mikrotik_routeros:<versi>
#
# Lisensi: CHR tanpa lisensi berbayar berjalan dalam mode free (upload dibatasi
# 1 Mbit/s per interface), lebih dari cukup untuk lab troubleshooting.
# Butuh: docker (+ plugin buildx), git, curl, unzip, make, dan /dev/kvm
# (virtualisasi aktif di BIOS; di dalam VM: nested virtualization).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEFAULT=$(grep -ho 'vrnetlab/mikrotik_routeros:[0-9.]*' "$ROOT"/labs/*/*.clab.yaml 2>/dev/null | sort -u | head -1 | cut -d: -f2)
VERSION=${1:-${DEFAULT:-7.20.4}}
IMAGE=vrnetlab/mikrotik_routeros:$VERSION
WORK=${XDG_CACHE_HOME:-$HOME/.cache}/p-lab/vrnetlab

if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "$IMAGE sudah ada."
  exit 0
fi
for cmd in docker git curl unzip make; do
  command -v "$cmd" >/dev/null || { echo "Butuh '$cmd' untuk membangun image." >&2; exit 1; }
done
# Makefile vrnetlab memanggil `docker buildx build --platform ...`. Tanpa plugin
# buildx, docker membaca "buildx" sebagai perintah tak dikenal: "unknown flag: --platform".
if ! docker buildx version >/dev/null 2>&1; then
  echo "Plugin docker buildx belum terpasang. Pasang dulu:" >&2
  echo "  Ubuntu/Debian (docker.io): sudo apt install docker-buildx" >&2
  echo "  Docker CE (repo docker.com): sudo apt install docker-buildx-plugin" >&2
  echo "  Arch: sudo pacman -S docker-buildx    Fedora: sudo dnf install docker-buildx-plugin" >&2
  exit 1
fi
if [[ ! -e /dev/kvm ]]; then
  echo "Peringatan: /dev/kvm tidak ada. RouterOS tetap jalan tanpa KVM, tapi sangat lambat (bisa > 5 menit per boot)." >&2
  if systemd-detect-virt -q 2>/dev/null; then
    echo "Mesin ini VM ($(systemd-detect-virt)): aktifkan nested virtualization di hypervisor-nya (lihat docs/instalasi.md)." >&2
  else
    echo "Aktifkan virtualisasi (VT-x/AMD-V) di BIOS." >&2
  fi
elif [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
  echo "Peringatan: /dev/kvm ada tapi tidak bisa diakses user ini: sudo usermod -aG kvm $USER, lalu login ulang." >&2
fi

echo "==> vrnetlab"
if [[ -d $WORK/.git ]]; then
  git -C "$WORK" pull -q --ff-only
else
  mkdir -p "$(dirname "$WORK")"
  git clone -q --depth 1 https://github.com/srl-labs/vrnetlab.git "$WORK"
fi

DIR=$WORK/mikrotik/routeros
echo "==> unduh CHR $VERSION"
if [[ ! -f $DIR/chr-$VERSION.vmdk ]]; then
  curl -fL --retry 3 -o "$DIR/chr.zip" "https://download.mikrotik.com/routeros/$VERSION/chr-$VERSION.vmdk.zip"
  unzip -o -q "$DIR/chr.zip" -d "$DIR"
  rm -f "$DIR/chr.zip"
fi
# Satu vmdk saja di folder build: Makefile membangun semua *.vmdk yang ada.
find "$DIR" -maxdepth 1 -name 'chr-*.vmdk' ! -name "chr-$VERSION.vmdk" -delete

echo "==> build image (beberapa menit)"
make -C "$DIR" docker-image REGISTRY=vrnetlab/
# vrnetlab versi baru memberi akhiran arsitektur (7.20.4-amd64); lab memakai tag tanpa akhiran.
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  BUILT=$(docker image ls --format '{{.Repository}}:{{.Tag}}' "${IMAGE%%:*}" | grep -m1 "^$IMAGE-") \
    || { echo "Build selesai tapi image $IMAGE tidak ditemukan (cek output make di atas)." >&2; exit 1; }
  docker tag "$BUILT" "$IMAGE"
fi
echo "Selesai: $IMAGE"
