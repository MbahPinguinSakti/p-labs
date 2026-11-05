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
# Butuh: docker, git, curl, unzip, make, dan /dev/kvm (virtualisasi aktif di BIOS).
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
if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
  echo "Peringatan: /dev/kvm tidak bisa diakses. RouterOS tetap jalan tanpa KVM, tapi sangat lambat." >&2
  echo "Aktifkan virtualisasi (VT-x/AMD-V) di BIOS, atau tambahkan user ke grup kvm." >&2
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
docker image inspect "$IMAGE" >/dev/null
echo "Selesai: $IMAGE"
