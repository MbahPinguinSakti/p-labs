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
# Mode Server (satu server, banyak user lewat browser; akun dibuat admin). Bertahap,
# sengaja tidak satu klik:
#   ./install.sh --server         1. pasang: user `plab`, data_dir, unit systemd; BERHENTI
#                                    minta config /etc/p-lab/server.yaml diisi admin
#   ./install.sh --server --check 2. cek kesiapan (config, RAM, KVM, port, container, admin)
#   ./install.sh --server --migrate 3. peralihan dari Pribadi: konfirmasi ketik `server`
#   ./install.sh --revert-pribadi    kembali ke mode Pribadi (data server tidak dihapus)
#
# Aman dijalankan berulang, misalnya setelah `git pull` untuk update.
# Panduan lengkap: docs/instalasi.md
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"

CHECK=0 YES=0 DEPS=1 SERVICE=1 SUDOLESS=ask SERVER=0 MIGRATE=0 REVERT=0 UNDERSTAND=0
for arg in "$@"; do
  case $arg in
    --check) CHECK=1 ;;
    --yes|-y) YES=1 ;;
    --no-deps) DEPS=0 ;;
    --no-service) SERVICE=0 ;;
    --sudoless) SUDOLESS=yes ;;
    --no-sudoless) SUDOLESS=no ;;
    --server) SERVER=1 ;;
    --migrate) MIGRATE=1 ;;
    --revert-pribadi) REVERT=1 ;;
    --yes-i-understand) UNDERSTAND=1 ;;   # lewati ketik-ulang `server` (skrip); --yes TIDAK mewakili ini
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opsi tidak dikenal: $arg (lihat --help)" >&2; exit 1 ;;
  esac
done
if (( MIGRATE )) && ! (( SERVER )); then echo "--migrate dipakai bersama --server: ./install.sh --server --migrate" >&2; exit 1; fi

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
die()  { bad "$*"; exit 1; }
ask() {  # ask "pertanyaan" -> 0 kalau ya
  (( YES )) && return 0
  [[ -t 0 ]] || return 1
  local reply
  read -r -p "  $1 [y/N] " reply
  [[ $reply =~ ^[yYiI] ]]
}
NOTES=()
NEED_RELOGIN=0
USER=${USER:-$(id -un)}

# Installer berjalan sebagai user biasa; sudo dipanggil sendiri untuk langkah yang
# butuh root. `sudo ./install.sh` membuat .venv dan node_modules milik root, lalu
# semua run berikutnya (dan service user) gagal "Permission denied".
if (( EUID == 0 )); then
  echo "Jangan jalankan installer dengan sudo/root. Jalankan sebagai user biasa: ./install.sh" >&2
  echo "(installer meminta password sudo sendiri saat perlu)" >&2
  exit 1
fi

# Sisa run lama dengan sudo: folder hasil build milik root tidak bisa ditimpa.
FOREIGN=()
for path in .venv web/node_modules web/dist "$HOME/.npm"; do
  [[ -e $path ]] && [[ -n $(find "$path" ! -user "$USER" -print -quit 2>/dev/null) ]] && FOREIGN+=("$path")
done

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

# --- mode Server -------------------------------------------------------------------------
# Asumsi (mode Server berjalan sebagai user sistem `plab`, bukan user yang login):
#  - repo ini dan .venv dibaca/dieksekusi `plab`: semua folder induk repo harus bisa
#    dilewati (o+x). Repo di /home/<user> dengan mode 700 TIDAK akan jalan; pindahkan ke
#    /opt/p-lab atau `chmod o+x ~`. Repo tidak ditulis plab; semua state ada di data_dir.
#  - `plab` anggota grup docker (jalankan container lab), clab_admins (containerlab
#    setuid, lewat setup-sudoless.sh) dan kvm (VM RouterOS). Ketiganya setara akses
#    root di mesin ini, jadi server ini sebaiknya mesin khusus.
#  - Build (venv, npm, web/dist) tetap dilakukan user yang menjalankan install.sh.
#  - Langkah root hanya lewat sudo di bawah ini: useradd/usermod, /etc/p-lab, data_dir,
#    unit systemd, dan `migrate-server migrate` (membuat data_dir milik plab).
SERVER_CONF=${LAB_CONFIG:-/etc/p-lab/server.yaml}
PY=$ROOT/.venv/bin/python
mig() { "$PY" platform/migrate-server "$@"; }
user_svc_active() { systemctl --user is-active -q p-lab 2>/dev/null; }
# Unit user ada (aktif, gagal berulang, atau hanya ter-enable). is-active saja tidak cukup:
# unit yang ExecStart-nya hilang (repo dipindah) berstatus "activating" terus-menerus.
user_svc_present() { systemctl --user cat p-lab >/dev/null 2>&1; }

path_traversable_by_others() {  # semua folder induk $1 punya bit o+x
  local d=$1
  while [[ $d != / ]]; do
    [[ $(stat -c %a "$d") =~ [1357]$ ]] || { echo "$d"; return 1; }
    d=$(dirname "$d")
  done
}

server_check() {
  step "Mode Server: cek kesiapan"
  local rc=0 blocked
  if getent passwd plab >/dev/null; then
    ok "user sistem plab"
    for g in docker kvm clab_admins; do
      getent group "$g" >/dev/null || continue
      id -nG plab | tr ' ' '\n' | grep -qx "$g" && ok "plab di grup $g" || { bad "plab belum di grup $g (./install.sh --server)"; rc=1; }
    done
  else bad "user plab belum ada (./install.sh --server)"; rc=1; fi
  if blocked=$(path_traversable_by_others "$ROOT"); then ok "repo bisa dilewati user plab"
  else bad "folder $blocked tidak bisa dilewati user lain: plab tidak bisa menjalankan P-lab (chmod o+x $blocked, atau pindahkan repo ke /opt)"; rc=1; fi
  [[ -f /etc/systemd/system/p-lab.service ]] && ok "unit systemd p-lab terpasang" || { bad "unit systemd belum terpasang (./install.sh --server)"; rc=1; }
  if [[ -f $SERVER_CONF ]]; then ok "config $SERVER_CONF"
  else bad "config belum ada: $SERVER_CONF (./install.sh --server membuatnya dari template)"; rc=1; fi
  if [[ -x $PY && -f $SERVER_CONF ]]; then
    echo; LAB_CONFIG=$SERVER_CONF mig check $( user_svc_active && echo --own-service-active ) || rc=1
  fi
  return $rc
}

server_install() {
  step "Mode Server: pasang"
  have containerlab || die "containerlab belum terpasang; jalankan dulu ./install.sh (tanpa --server) atau pasang manual"
  if getent passwd plab >/dev/null; then ok "user plab sudah ada"
  elif ask "Buat user sistem 'plab' (menjalankan P-lab server)? (butuh sudo)"; then
    sudo useradd -r -m -d /var/lib/p-lab -s "$(command -v nologin || echo /usr/sbin/nologin)" -U plab && ok "user plab dibuat"
  else die "Tanpa user plab, mode Server tidak bisa dipasang."; fi
  for g in docker kvm; do
    getent group "$g" >/dev/null && sudo usermod -aG "$g" plab && ok "plab masuk grup $g"
  done
  sudo "$ROOT/platform/setup-sudoless.sh" plab | sed 's/^/  /'   # grup clab_admins + containerlab setuid
  if blocked=$(path_traversable_by_others "$ROOT"); then ok "repo bisa dilewati user plab"
  else warn "folder $blocked tidak bisa dilewati user lain: plab tidak bisa menjalankan P-lab. Perbaiki: chmod o+x $blocked (atau pindahkan repo ke /opt/p-lab)"; fi
  sudo install -d -m 755 "$(dirname "$SERVER_CONF")"
  if [[ ! -f $SERVER_CONF ]]; then
    sudo install -m 644 platform/templates/server.yaml "$SERVER_CONF"
    ok "config dibuat dari template: $SERVER_CONF"
  else ok "config sudah ada: $SERVER_CONF (tidak ditimpa)"; fi
  local data
  data=$(LAB_CONFIG=$SERVER_CONF PYTHONDONTWRITEBYTECODE=1 "$PY" -c \
    'import sys; sys.path.insert(0, "platform"); import config; print(config.load().data_dir)') \
    || die "config tidak valid; perbaiki $SERVER_CONF lalu ulangi ./install.sh --server"
  sudo install -d -o plab -g plab -m 750 "$data" && ok "data_dir $data (milik plab)"
  sudo env LAB_CONFIG="$SERVER_CONF" "$ROOT/platform/install-service.sh" --system | sed 's/^/  /'
  # update kode (git pull + install.sh --server): service yang sudah jalan dimuat ulang
  systemctl is-active -q p-lab 2>/dev/null && sudo systemctl restart p-lab && ok "service p-lab dimuat ulang"
  # Sisa mode Pribadi setelah peralihan (mis. migrate versi lama melewatkan unit yang gagal berulang).
  if systemctl is-enabled -q p-lab 2>/dev/null && user_svc_present; then
    systemctl --user disable --now p-lab 2>/dev/null
    systemctl --user reset-failed p-lab 2>/dev/null
    ok "service user p-lab sisa mode Pribadi dihentikan dan di-disable"
  fi
  step "Selesai (belum dinyalakan, belum di-enable)"
  echo "  Langkah berikutnya, dilakukan admin:"
  echo "   1. Isi $SERVER_CONF (alamat, data_dir, style, capacity, allowed_hosts; ada penjelasan di dalamnya)"
  echo "   2. ./install.sh --server --check     cek kesiapan"
  echo "   3. ./install.sh --server --migrate   membuat admin pertama dan menyalakan service"
  echo "                                        (instalasi baru maupun peralihan; ketik ulang 'server')"
  echo "  Akun lain: sudo platform/p-lab-admin create-user ... (lihat docs/server.md)"
  echo "  Key LLM (opsional): /etc/p-lab/web.env (lihat docs/server.md)"
  echo "  Batal kapan saja: ./install.sh --revert-pribadi"
}

server_migrate() {
  step "Mode Server: peralihan Pribadi -> Server"
  [[ -x $PY ]] || die "venv belum ada: jalankan ./install.sh dulu"
  [[ -f $SERVER_CONF ]] || die "config belum ada: $SERVER_CONF (./install.sh --server)"
  getent passwd plab >/dev/null || die "user plab belum ada (./install.sh --server)"
  local flags=()
  user_svc_active && flags+=(--own-service-active)
  (( UNDERSTAND )) && flags+=(--yes-i-understand)
  # root hanya untuk data_dir milik plab; sudo menjaga terminal sehingga konfirmasi bisa diketik.
  # Pre-flight dijalankan ulang di dalamnya; gagal = berhenti sebelum ada yang diubah.
  sudo env PYTHONDONTWRITEBYTECODE=1 LAB_CONFIG="$SERVER_CONF" "$PY" platform/migrate-server migrate \
    --owner plab "${flags[@]}" || die "peralihan dibatalkan; tidak ada service yang diubah"
  step "Mengganti service"
  sudo env LAB_CONFIG="$SERVER_CONF" "$ROOT/platform/install-service.sh" --system | sed 's/^/  /'   # alamat dari config final
  if user_svc_present; then
    systemctl --user disable --now p-lab 2>/dev/null
    systemctl --user reset-failed p-lab 2>/dev/null
    ok "service user p-lab (mode Pribadi) dihentikan dan di-disable"
  fi
  sudo systemctl enable --now p-lab
  sleep 2
  if systemctl is-active -q p-lab; then ok "service system p-lab berjalan"
  else die "service system p-lab gagal start: journalctl -u p-lab -e. Kembali: ./install.sh --revert-pribadi"; fi
  echo "  Akun siswa: sudo platform/p-lab-admin create-user / import-csv (DB di data_dir)."
}

revert_pribadi() {
  step "Kembali ke mode Pribadi"
  ask "Matikan mode Server dan hidupkan lagi service pribadi? (data di data_dir tidak dihapus)" || die "dibatalkan"
  sudo env LAB_CONFIG="$SERVER_CONF" "$ROOT/platform/install-service.sh" --system --uninstall | sed 's/^/  /'
  [[ -x $PY ]] && sudo env PYTHONDONTWRITEBYTECODE=1 "$PY" platform/migrate-server revert --config "$SERVER_CONF" | sed 's/^/  /'
  platform/install-service.sh | sed 's/^/  /'
  ok "mode Pribadi aktif: http://localhost:8000"
}

if (( REVERT )); then revert_pribadi; exit 0; fi
if (( MIGRATE )); then server_migrate; exit 0; fi
if (( SERVER && CHECK )); then have() { command -v "$1" >/dev/null 2>&1; }; server_check; exit $?; fi

# --- 1. cek dependensi sistem ----------------------------------------------------------
step "1/6 Dependensi sistem (${PRETTY_NAME:-$DISTRO})"
MISSING=()   # nama logis: docker containerlab python node script
have() { command -v "$1" >/dev/null 2>&1; }

if have docker; then ok "docker $(docker --version 2>/dev/null | sed 's/Docker version \([^,]*\).*/\1/')"
else bad "docker belum terinstall"; MISSING+=(docker); fi

if have containerlab; then ok "containerlab $(containerlab version 2>/dev/null | sed -n 's/^ *version: *//p' | head -1)"
else bad "containerlab belum terinstall"; MISSING+=(containerlab); fi

# Terminal web lewat server (platform/termbridge.py); ttyd hanya untuk platform/serve (mode terminal tanpa web).
if have ttyd; then ok "ttyd (opsional, untuk platform/serve)"; else warn "ttyd tidak ada: opsional, hanya untuk platform/serve (mode terminal tanpa web UI)"; fi

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

# Paket ttyd di Debian/Ubuntu memasang service systemd `ttyd` (login read-only di
# port 7681). Web UI tidak memakai ttyd sama sekali (terminal lewat server), dan
# platform/serve memakai port 7681 sendiri, jadi service bawaan ini tidak perlu.
if systemctl is-active -q ttyd 2>/dev/null; then
  if (( CHECK )); then
    warn "service systemd 'ttyd' bawaan distro aktif (login di port 7681); tidak dipakai P-lab: sudo systemctl disable --now ttyd"
  elif ask "Matikan service 'ttyd' bawaan distro (login di port 7681, tidak dipakai P-lab)? (butuh sudo)"; then
    sudo systemctl disable --now ttyd && ok "service ttyd bawaan dimatikan"
  else
    warn "service ttyd bawaan tetap aktif; hanya bentrok dengan platform/serve (port 7681)."
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
  (( ${#FOREIGN[@]} )) && bad "bukan milikmu (sisa run dengan sudo?): ${FOREIGN[*]} → sudo chown -R $USER: ${FOREIGN[*]}"
  [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import fastapi, yaml' 2>/dev/null && ok "venv Python siap" || bad "venv Python belum siap (.venv)"
  [[ -f web/dist/index.html ]] && ok "web UI sudah di-build" || bad "web UI belum di-build (web/dist)"
  systemctl --user is-active -q p-lab 2>/dev/null && ok "service p-lab berjalan" || bad "service p-lab tidak berjalan"
  CLAB_BIN=$(command -v containerlab || true)
  [[ -n $CLAB_BIN && -u $CLAB_BIN ]] && ok "containerlab sudo-less (deploy dari web)" || bad "containerlab masih butuh sudo (deploy hanya lewat terminal)"
  for image in $(grep -ho 'vrnetlab/mikrotik_routeros:[0-9.]*' labs/*/*.clab.yaml 2>/dev/null | sort -u); do
    docker image inspect "$image" >/dev/null 2>&1 && ok "image $image" \
      || bad "image $image belum dibangun (lab RouterOS): platform/build-routeros-image.sh"
  done
  if [[ -r /dev/kvm && -w /dev/kvm ]]; then ok "KVM tersedia (/dev/kvm)"
  elif [[ -e /dev/kvm ]]; then bad "/dev/kvm tidak bisa diakses user ini: sudo usermod -aG kvm $USER (lab RouterOS)"
  elif systemd-detect-virt -q 2>/dev/null; then bad "tidak ada /dev/kvm di VM ini: aktifkan nested virtualization di hypervisor (lab RouterOS)"
  else bad "tidak ada /dev/kvm: aktifkan VT-x/AMD-V di BIOS (lab RouterOS akan sangat lambat)"; fi
  [[ -x .venv/bin/python ]] && { .venv/bin/python platform/lablint.py labs/*/ | sed 's/^/  /'; } || true
  exit 0
fi

# --- 1b. kepemilikan file ---------------------------------------------------------------
if (( ${#FOREIGN[@]} )); then
  step "Kepemilikan file"
  bad "bukan milikmu (sisa run dengan sudo?): ${FOREIGN[*]}"
  if ask "Kembalikan kepemilikan ke $USER? (sudo chown -R $USER: ...)"; then
    sudo chown -R "$USER:" "${FOREIGN[@]}" && ok "kepemilikan diperbaiki"
  else
    die "Perbaiki dulu: sudo chown -R $USER: ${FOREIGN[*]}"
  fi
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
.venv/bin/python -m pip install -q --upgrade pip || die "gagal meng-upgrade pip di .venv"
.venv/bin/python -m pip install -q -r platform/requirements.txt || die "gagal memasang platform/requirements.txt"
ok "paket Python terpasang (platform/requirements.txt)"

# --- 3. Web UI -------------------------------------------------------------------------
step "3/6 Web UI (web/)"
if have npm; then
  (cd web && npm ci --no-audit --no-fund --loglevel=error) || die "npm ci gagal (lihat pesan di atas)"
  ok "dependensi npm terpasang"
  (cd web && npm run build >/dev/null) || die "build web UI gagal"
  ok "web UI di-build ke web/dist"
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
    elif [[ $image == vrnetlab/mikrotik_routeros:* ]]; then
      # Tidak ada di registry: dibangun lokal dari CHR (image VM resmi MikroTik).
      echo "  ${D}$image dipakai lab MikroTik RouterOS dan harus dibangun lokal"
      echo "  (unduh CHR ±50 MB dari mikrotik.com + vrnetlab, beberapa menit).${N}"
      if ask "Bangun $image sekarang?"; then
        platform/build-routeros-image.sh "${image##*:}" | sed 's/^/  /' && ok "$image (dibangun)"
      else
        warn "$image belum ada: lab RouterOS belum bisa di-deploy (platform/build-routeros-image.sh)."
      fi
    else docker pull -q "$image" >/dev/null && ok "$image (diunduh)"; fi
  done
else
  warn "docker belum bisa diakses: image (${IMAGES//$'\n'/, }) diunduh saat deploy pertama."
fi
.venv/bin/python platform/lablint.py labs/*/ | sed 's/^/  /' || warn "Ada lab yang tidak lolos lab-lint."

if (( SERVER )); then server_install; exit 0; fi

# --- 5. Service ------------------------------------------------------------------------
step "5/6 Service web UI"
# Config mode Server di mesin ini: service user ikut membacanya (default /etc/p-lab/server.yaml)
# dan akan start sebagai Server. Jangan dipasang; arahkan admin ke jalur yang benar.
SERVER_CFG_MODE=$(PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c \
  'import sys; sys.path.insert(0, "platform"); import config; print(config.load().mode)' 2>/dev/null || echo rusak)
if (( SERVICE )) && [[ $SERVER_CFG_MODE != pribadi ]]; then
  warn "config ${LAB_CONFIG:-/etc/p-lab/server.yaml} bermode server (atau rusak): service Pribadi tidak dipasang. Lanjutkan mode Server dengan ./install.sh --server, atau kembali ke Pribadi dengan ./install.sh --revert-pribadi"
elif (( SERVICE )) && systemctl --user show-environment >/dev/null 2>&1; then
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
