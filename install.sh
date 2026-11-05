#!/usr/bin/env bash
# Installer P-lab: cek dan pasang semua yang dibutuhkan, lalu jalankan web UI.
#
#   ./install.sh              pasang semuanya (package sistem minta konfirmasi + sudo)
#   ./install.sh --check      hanya cek, tidak mengubah apa pun
#   ./install.sh --yes        jangan bertanya (jawab "ya" untuk semua)
#   ./install.sh --no-deps    jangan memasang package sistem (docker, containerlab, ...)
#   ./install.sh --no-service jangan pasang service systemd (jalankan manual: platform/web)
#   ./install.sh --sudoless   langsung aktifkan deploy lab dari web (setup-sudoless.sh)
#
# Aman dijalankan berulang, misalnya setelah `git pull` untuk update.
# Panduan lengkap: docs/instalasi.md
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"

CHECK=0 YES=0 DEPS=1 SERVICE=1 SUDOLESS=ask
for arg in "$@"; do
  case $arg in
    --check) CHECK=1 ;;
    --yes|-y) YES=1 ;;
    --no-deps) DEPS=0 ;;
    --no-service) SERVICE=0 ;;
    --sudoless) SUDOLESS=yes ;;
    --no-sudoless) SUDOLESS=no ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opsi tidak dikenal: $arg (lihat --help)" >&2; exit 1 ;;
  esac
done

# --- tampilan ----------------------------------------------------------------------
if [[ -t 1 ]]; then
  G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' B=$'\e[1m' D=$'\e[2m' N=$'\e[0m'
else
  G= Y= R= B= D= N=
fi
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$*"; NOTES+=("$*"); }
bad()  { printf '  %s✗%s %s\n' "$R" "$N" "$*"; }
step() { printf '\n%s%s%s\n' "$B" "$*" "$N"; }
ask() {  # ask "pertanyaan" -> 0 kalau ya
  (( YES )) && return 0
  [[ -t 0 ]] || return 1
  local reply
  read -r -p "  $1 [y/N] " reply
  [[ $reply =~ ^[yYiI] ]]
}
NOTES=()
NEED_RELOGIN=0

# --- distro --------------------------------------------------------------------------
. /etc/os-release 2>/dev/null || true
case " ${ID:-} ${ID_LIKE:-} " in
  *" arch "*) DISTRO=arch ;;
  *" debian "*|*" ubuntu "*) DISTRO=debian ;;
  *" fedora "*|*" rhel "*) DISTRO=fedora ;;
  *) DISTRO=other ;;
esac

version_ge() {  # version_ge 3.10.2 3.10 -> 0
  [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]
}

# --- 1. cek dependensi sistem ----------------------------------------------------------
step "1/6 Dependensi sistem (${PRETTY_NAME:-$DISTRO})"
MISSING=()   # nama logis: docker containerlab ttyd python node script
have() { command -v "$1" >/dev/null 2>&1; }

if have docker; then ok "docker $(docker --version 2>/dev/null | sed 's/Docker version \([^,]*\).*/\1/')"
else bad "docker belum terinstall"; MISSING+=(docker); fi

if have containerlab; then ok "containerlab $(containerlab version 2>/dev/null | sed -n 's/^ *version: *//p' | head -1)"
else bad "containerlab belum terinstall"; MISSING+=(containerlab); fi

if have ttyd; then ok "ttyd"; else bad "ttyd belum terinstall (terminal di browser)"; MISSING+=(ttyd); fi

PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0)
if version_ge "$PYV" 3.10 && python3 -c 'import venv, ensurepip' 2>/dev/null; then ok "python $PYV (+ venv)"
else bad "python >= 3.10 dengan modul venv belum ada (sekarang: $PYV)"; MISSING+=(python); fi

NODEV=$(node --version 2>/dev/null | tr -d v || echo 0)
if version_ge "$NODEV" 20.19 && have npm; then ok "node $NODEV + npm"
else bad "node >= 20.19 + npm belum ada (sekarang: ${NODEV}); dipakai untuk build web UI"; MISSING+=(node); fi

if have script && script --help 2>&1 | grep -q -- '--log-timing\|-T'; then ok "script (util-linux, perekam terminal)"
else bad "script dari util-linux belum ada"; MISSING+=(script); fi

install_deps() {
  local pkgs=() clab=0 m
  for m in "${MISSING[@]}"; do
    case $DISTRO:$m in
      arch:docker) pkgs+=(docker) ;;
      arch:ttyd) pkgs+=(ttyd) ;;
      arch:python) pkgs+=(python) ;;
      arch:node) pkgs+=(nodejs npm) ;;
      arch:script) pkgs+=(util-linux) ;;
      debian:docker) pkgs+=(docker.io) ;;
      debian:ttyd) pkgs+=(ttyd) ;;
      debian:python) pkgs+=(python3 python3-venv) ;;
      debian:node) pkgs+=(nodejs npm) ;;
      debian:script) pkgs+=(util-linux) ;;
      fedora:docker) pkgs+=(moby-engine) ;;
      fedora:ttyd) pkgs+=(ttyd) ;;
      fedora:python) pkgs+=(python3) ;;
      fedora:node) pkgs+=(nodejs npm) ;;
      fedora:script) pkgs+=(util-linux) ;;
      *:containerlab) clab=1 ;;
    esac
  done
  if (( ${#pkgs[@]} )); then
    case $DISTRO in
      arch) sudo pacman -S --needed --noconfirm "${pkgs[@]}" ;;
      debian) sudo apt-get update && sudo apt-get install -y "${pkgs[@]}" ;;
      fedora) sudo dnf install -y "${pkgs[@]}" ;;
    esac
  fi
  if (( clab )); then
    if [[ $DISTRO == arch ]] && have paru; then paru -S --needed --noconfirm containerlab-bin
    elif [[ $DISTRO == arch ]] && have yay; then yay -S --needed --noconfirm containerlab-bin
    else
      # Installer resmi containerlab (menambahkan repo deb/rpm atau memasang binary).
      bash -c "$(curl -sL https://get.containerlab.dev)"
    fi
  fi
  if [[ " ${MISSING[*]} " == *" docker "* ]]; then
    sudo systemctl enable --now docker
  fi
}

if (( ${#MISSING[@]} )); then
  if (( CHECK )) || (( ! DEPS )); then
    warn "Pasang dulu: ${MISSING[*]} (lihat docs/instalasi.md)"
  elif [[ $DISTRO == other ]]; then
    warn "Distro tidak dikenali: pasang manual ${MISSING[*]} (lihat docs/instalasi.md), lalu jalankan ulang."
  elif ask "Pasang ${MISSING[*]} sekarang? (butuh sudo)"; then
    install_deps
    hash -r
    NODEV=$(node --version 2>/dev/null | tr -d v || echo 0)
    version_ge "$NODEV" 20.19 || warn "node $NODEV dari repo distro terlalu lama untuk web UI; pasang node >= 20.19 (mis. lewat nodesource atau fnm)."
  else
    warn "Dependensi belum lengkap: ${MISSING[*]}"
  fi
fi

# docker harus bisa dipakai tanpa sudo (lab-shell, verify.sh, server).
if have docker; then
  if docker info >/dev/null 2>&1; then ok "docker bisa diakses tanpa sudo"
  elif id -nG | tr ' ' '\n' | grep -qx docker; then
    warn "user sudah di grup docker tapi daemon belum bisa diakses: jalankan 'sudo systemctl enable --now docker' atau login ulang."
  elif (( CHECK )); then
    warn "user belum di grup docker (sudo usermod -aG docker $USER, lalu login ulang)"
  elif ask "Tambahkan $USER ke grup docker? (butuh sudo, lalu login ulang)"; then
    sudo usermod -aG docker "$USER"; NEED_RELOGIN=1
    warn "Grup docker aktif setelah logout/login."
  else
    warn "docker belum bisa diakses tanpa sudo."
  fi
fi

if (( CHECK )); then
  step "Mode --check"
  [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import fastapi, yaml' 2>/dev/null && ok "venv Python siap" || bad "venv Python belum siap (.venv)"
  [[ -f web/dist/index.html ]] && ok "web UI sudah di-build" || bad "web UI belum di-build (web/dist)"
  systemctl --user is-active -q p-lab 2>/dev/null && ok "service p-lab berjalan" || bad "service p-lab tidak berjalan"
  CLAB_BIN=$(command -v containerlab || true)
  [[ -n $CLAB_BIN && -u $CLAB_BIN ]] && ok "containerlab sudo-less (deploy dari web)" || bad "containerlab masih butuh sudo (deploy hanya lewat terminal)"
  [[ -x .venv/bin/python ]] && { .venv/bin/python platform/lablint.py labs/*/ | sed 's/^/  /'; } || true
  exit 0
fi

# --- 2. Python -------------------------------------------------------------------------
step "2/6 Lingkungan Python (.venv)"
# venv menyimpan path absolut: kalau folder project dipindah, venv rusak dan dibuat ulang.
if [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import sys' 2>/dev/null \
   && grep -q "$ROOT/.venv" .venv/bin/pip 2>/dev/null; then
  ok "venv sudah ada"
else
  python3 -m venv --clear .venv && ok "venv dibuat"
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r platform/requirements.txt && ok "paket Python terpasang (platform/requirements.txt)"

# --- 3. Web UI -------------------------------------------------------------------------
step "3/6 Web UI (web/)"
if have npm; then
  (cd web && npm ci --no-audit --no-fund --loglevel=error) && ok "dependensi npm terpasang"
  (cd web && npm run build >/dev/null) && ok "web UI di-build ke web/dist"
else
  warn "npm tidak ada: web UI belum bisa di-build."
fi

# --- 4. Image container ------------------------------------------------------------------
step "4/6 Image container untuk lab"
IMAGES=$(.venv/bin/python - <<'EOF'
import glob, yaml
images = set()
for path in glob.glob("labs/*/*.clab.yaml"):
    topo = (yaml.safe_load(open(path)) or {}).get("topology") or {}
    if (topo.get("defaults") or {}).get("image"):
        images.add(topo["defaults"]["image"])
    for node in (topo.get("nodes") or {}).values():
        if (node or {}).get("image"):
            images.add(node["image"])
print("\n".join(sorted(images)))
EOF
)
if docker info >/dev/null 2>&1; then
  for image in $IMAGES; do
    if docker image inspect "$image" >/dev/null 2>&1; then ok "$image"
    else docker pull -q "$image" >/dev/null && ok "$image (diunduh)"; fi
  done
else
  warn "docker belum bisa diakses: image (${IMAGES//$'\n'/, }) diunduh saat deploy pertama."
fi
.venv/bin/python platform/lablint.py labs/*/ | sed 's/^/  /' || warn "Ada lab yang tidak lolos lab-lint."

# --- 5. Service ------------------------------------------------------------------------
step "5/6 Service web UI"
if (( SERVICE )) && systemctl --user show-environment >/dev/null 2>&1; then
  platform/install-service.sh | sed 's/^/  /'
elif (( SERVICE )); then
  warn "systemd user tidak tersedia: jalankan web UI manual dengan platform/web"
else
  ok "dilewati (--no-service). Jalankan: platform/web"
fi

# --- 6. Deploy dari web (opsional) ------------------------------------------------------
step "6/6 Deploy lab dari web (opsional)"
CLAB_BIN=$(command -v containerlab || true)
if [[ -z $CLAB_BIN ]]; then
  warn "containerlab belum ada; lewati."
elif [[ -u $CLAB_BIN ]]; then
  ok "containerlab sudah sudo-less"
else
  echo "  ${D}Tanpa ini, lab di-deploy dari terminal dengan ./reset.sh (minta password sudo)."
  echo "  Dengan ini, tombol Deploy/Reset di web langsung jalan. Konsekuensi: anggota grup"
  echo "  clab_admins praktis setara root lewat containerlab (sama seperti grup docker).${N}"
  if [[ $SUDOLESS == yes ]] || { [[ $SUDOLESS == ask ]] && ask "Aktifkan deploy dari web? (butuh sudo, lalu login ulang)"; }; then
    sudo platform/setup-sudoless.sh "$USER" | sed 's/^/  /'
    NEED_RELOGIN=1
  else
    ok "dilewati. Aktifkan nanti: sudo platform/setup-sudoless.sh"
  fi
fi

# --- ringkasan ---------------------------------------------------------------------------
step "Selesai"
if (( ${#NOTES[@]} )); then
  echo "  Perlu perhatian:"
  for note in "${NOTES[@]}"; do echo "   - $note"; done
fi
if (( NEED_RELOGIN )); then
  echo "  ${Y}Logout lalu login lagi${N} supaya grup baru aktif (docker / clab_admins)."
fi
echo "  Buka ${B}http://localhost:8000${N} (atau ikon P-lab di menu aplikasi)."
echo "  Cek ulang kapan saja: ./install.sh --check · Panduan: docs/penggunaan.md"
