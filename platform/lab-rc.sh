# Rcfile bash untuk shell pemain di dalam node lab.
# Dimuat oleh platform/lab-shell lewat `bash --rcfile /etc/lab/rc`.
# Setiap command yang selesai dieksekusi ditulis sebagai satu baris JSON ke
# /var/log/lab/<node>.jsonl (bind mount ke .state/events/ di host).

[ -f /etc/bash/bashrc ] && . /etc/bash/bashrc

LAB_NODE=${LAB_NODE:-$(hostname)}
LAB_SESSION=${LAB_SESSION:-unknown}
__lab_log_file=/var/log/lab/${LAB_NODE}.jsonl

# History hanya di memori: tidak ada command basi dari sesi sebelumnya,
# dan command yang sama berturut-turut tetap tercatat.
unset HISTFILE
HISTCONTROL=
HISTIGNORE=
__lab_last_num=

__lab_json() {
  local s=$1
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\r'/\\r}
  s=${s//$'\t'/\\t}
  printf '%s' "$s"
}

__lab_log() {
  local ec=$? entry num cmd ts
  entry=$(HISTTIMEFORMAT= builtin history 1)
  if [[ $entry =~ ^\ *([0-9]+)\*?\ +(.*)$ ]]; then
    num=${BASH_REMATCH[1]}
    cmd=${BASH_REMATCH[2]}
    # Enter kosong tidak menambah history; jangan catat ulang command terakhir.
    if [[ $num != "$__lab_last_num" ]]; then
      __lab_last_num=$num
      ts=${EPOCHREALTIME/,/.}
      printf '{"ts":%s,"session":"%s","node":"%s","type":"command","data":"%s","exit":%d}\n' \
        "$ts" "$(__lab_json "$LAB_SESSION")" "$(__lab_json "$LAB_NODE")" "$(__lab_json "$cmd")" "$ec" \
        >> "$__lab_log_file" 2>/dev/null
    fi
  fi
  return $ec
}

PROMPT_COMMAND=__lab_log
readonly PROMPT_COMMAND HISTCONTROL HISTIGNORE
PS1="\[\e[1;32m\]${LAB_NODE}\[\e[0m\]:\w# "
