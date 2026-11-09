# Kontrak env script soal (inject.sh, verify.sh). Di-source di awal script:
#   source "$(dirname "$0")/../../platform/labenv.sh"
#
# reset-lab, sessions.py, dan evaluate.py meng-export env instance yang dituju:
#   LAB_INSTANCE   pemilik instance (default local)
#   LAB_PROBLEM_DIR  soal pemilik env ini; kalau bukan soal script ini (env sisa
#                  dari lab lain), tiga nilai di bawah dihitung ulang
#   LAB_STATE_DIR  direktori state sesi (.state/ instance); ground_truth.json ditulis di sini
#   LAB_CLAB_NAME  nama lab containerlab instance (container: clab-<nama>-<node>)
#   LAB_TOPO       file topologi instance
# Kalau kosong (script dijalankan manual, mis. ./inject.sh), nilainya dihitung
# dari LAB_INSTANCE: local = layout lama (labs/<id>/.state, nama lab asli),
# instance lain lewat platform/instance.py.
#
# Juga disediakan:
#   LAB_DIR        direktori soal (absolut)
#   LAB_PY         python venv P-lab (fallback python3)
#   ctr <node>     nama container node di instance ini
#   ros_exec <node> <command...>   satu command RouterOS (ros.py exec) di instance ini
#
# Jangan menulis clab-<nama>-<node> atau .state/ secara langsung: keduanya
# berbeda untuk tiap instance.

LAB_DIR=$(cd "$(dirname "$0")" && pwd -P)
LAB_PLATFORM=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAB_PY="$(dirname "$LAB_PLATFORM")/.venv/bin/python"
[[ -x $LAB_PY ]] || LAB_PY=python3

if [[ ${LAB_PROBLEM_DIR:-} != "$LAB_DIR" ]]; then
  unset LAB_STATE_DIR LAB_CLAB_NAME LAB_TOPO
fi
if [[ -z ${LAB_STATE_DIR:-} || -z ${LAB_CLAB_NAME:-} || -z ${LAB_TOPO:-} ]]; then
  if [[ ${LAB_INSTANCE:-local} == local ]]; then
    # Layout lama tanpa python (sama dengan Instance(dir, "local")).
    LAB_INSTANCE=local
    LAB_STATE_DIR="$LAB_DIR/.state"
    LAB_TOPO="$LAB_DIR/$(sed -n 's/^lab_topology:[[:space:]]*//p' "$LAB_DIR/problem.yaml" | sed 's/[[:space:]]*#.*//; s/^["'\'']//; s/["'\'']$//')"
    LAB_CLAB_NAME=$(sed -n 's/^name:[[:space:]]*//p' "$LAB_TOPO" | sed 's/[[:space:]]*#.*//; s/^["'\'']//; s/["'\'']$//')
  else
    _lab_env=$("$LAB_PY" "$LAB_PLATFORM/instance.py" env "$LAB_DIR") || exit 2
    eval "$_lab_env"
    unset _lab_env
  fi
fi
LAB_PROBLEM_DIR=$LAB_DIR
export LAB_INSTANCE LAB_PROBLEM_DIR LAB_STATE_DIR LAB_CLAB_NAME LAB_TOPO

ctr() { printf 'clab-%s-%s\n' "$LAB_CLAB_NAME" "$1"; }
ros_exec() { "$LAB_PY" "$LAB_PLATFORM/ros.py" exec "$LAB_DIR" "$@"; }
