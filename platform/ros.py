#!/usr/bin/env python3
"""Akses MikroTik RouterOS di lab (node containerlab kind `mikrotik_ros`).

  ros.py shell <lab_dir> <node>          # shell pemain (dipanggil lab-shell)
  ros.py exec  <lab_dir> <node> <cmd>    # satu command, untuk inject/verify/state_check

RouterOS bukan bash, jadi hook perekaman lab-rc.sh tidak bisa dipasang di
dalamnya. Gantinya, shell pemain dijalankan di host: proxy kecil yang meniru
CLI RouterOS (prompt, konteks menu, `..`, `/`), mengirim setiap command lewat
SSH, lalu mencatatnya ke .state/events/<node>.jsonl dalam format yang sama
dengan lab-rc.sh. Bonusnya, command selalu tercatat dalam bentuk lengkap
(`/ip address print`, bukan `print` di dalam konteks /ip address), sehingga
regex checkpoint dan aturan NOS cukup mencocokkan satu bentuk.

Exit code command ditentukan dari pesan error RouterOS (ERROR_RX), karena exec
lewat SSH di RouterOS selalu selesai dengan status 0.
"""

if __name__ == "__main__":
    import _venv  # noqa: E402  (Python venv, lihat _venv.py)
    _venv.ensure()

import json
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROS_KIND = "mikrotik_ros"
USERNAME, PASSWORD = "admin", "admin"   # default containerlab untuk mikrotik_ros
EXEC_TIMEOUT = 15

# Pesan error RouterOS. Output yang cocok = command gagal (exit 1).
ERROR_RX = re.compile(
    r"^\s*(failure:|syntax error|expected (end of command|command name)|bad command name|"
    r"input does not match|no such item|invalid value|ambiguous value|value of \S+ out of range|"
    r"not enough permissions|missing value)", re.I | re.M)

# Kata kerja RouterOS: token pertama yang termasuk di sini mengakhiri path menu.
VERBS = {
    "print", "add", "set", "remove", "enable", "disable", "export", "find", "get", "edit",
    "comment", "move", "reset", "unset", "monitor", "monitor-traffic", "ping", "traceroute",
    "flush", "reset-counters", "torch", "blink", "make-static", "release", "renew",
    "check-for-updates", "reboot", "shutdown",
}
# Command interaktif yang tidak pernah selesai lewat exec: dibuat berhenti sendiri.
FINITE = {"ping": "count=4", "traceroute": "count=1", "monitor": "once",
          "monitor-traffic": "once", "torch": "duration=3"}
TOKEN = re.compile(r'"(?:\\.|[^"])*"|\[[^\]]*\]|\S+')

# Menu untuk tab completion (bukan daftar lengkap, cukup untuk lab jaringan).
MENUS = {
    "": ["interface", "ip", "ipv6", "routing", "system", "tool", "log", "ping"],
    "interface": ["ethernet", "bridge", "vlan", "list", "print", "set", "enable", "disable", "monitor-traffic"],
    "interface ethernet": ["print", "set", "monitor", "reset-counters"],
    "interface bridge": ["port", "vlan", "print", "add", "set"],
    "ip": ["address", "route", "arp", "neighbor", "firewall", "dhcp-client", "dhcp-server", "pool", "dns"],
    "ip address": ["print", "add", "set", "remove", "enable", "disable"],
    "ip route": ["print", "add", "set", "remove", "enable", "disable"],
    "ip arp": ["print", "add", "remove"],
    "ip firewall": ["filter", "nat", "mangle", "connection"],
    "routing": ["ospf", "bgp", "route", "filter"],
    "routing ospf": ["instance", "area", "interface-template", "interface", "neighbor", "lsa", "static-neighbor"],
    "routing ospf instance": ["print", "add", "set", "remove"],
    "routing ospf area": ["print", "add", "set", "remove"],
    "routing ospf interface-template": ["print", "add", "set", "remove", "enable", "disable"],
    "routing ospf interface": ["print"],
    "routing ospf neighbor": ["print"],
    "routing ospf lsa": ["print"],
    "system": ["identity", "resource", "routerboard", "clock"],
    "tool": ["traceroute", "ping", "torch", "sniffer"],
    "log": ["print"],
}


# --- topologi ------------------------------------------------------------------------

def load_topology(lab_dir):
    lab_dir = Path(lab_dir)
    problem = yaml.safe_load((lab_dir / "problem.yaml").read_text())
    return yaml.safe_load((lab_dir / problem["lab_topology"]).read_text())


def node_kind(topo, node):
    body = topo.get("topology") or {}
    spec = (body.get("nodes") or {}).get(node) or {}
    return spec.get("kind") or (body.get("defaults") or {}).get("kind") or "linux"


def is_ros(lab_dir, node):
    return node_kind(load_topology(lab_dir), node) == ROS_KIND


def display_interface(kind, name):
    """Nama interface seperti yang dilihat pemain: eth1 container = ether2 RouterOS
    (ether1 dipakai vrnetlab untuk management)."""
    m = re.fullmatch(r"eth(\d+)", name)
    return f"ether{int(m.group(1)) + 1}" if kind == ROS_KIND and m else name


# --- normalisasi command -------------------------------------------------------------

def resolve(context, line):
    """Terjemahkan satu baris CLI dengan konteks menu saat ini.

    Kembalikan (konteks_baru, command_lengkap). command_lengkap None berarti
    baris itu hanya berpindah menu (mis. `/ip address`, `..`, `/`).
    """
    line = line.strip()
    if line.startswith((":", "{")):
        return context, line   # scripting RouterOS (:put, :foreach, {...}) dikirim apa adanya
    path = [] if line.startswith("/") else list(context)
    tokens = TOKEN.findall(line.lstrip("/"))
    for i, token in enumerate(tokens):
        if token == "..":
            path = path[:-1]
        elif token == "/":
            path = []
        elif token in VERBS:
            rest = tokens[i + 1:]
            finite = FINITE.get(token)
            if finite and not any(t.startswith(finite.split("=")[0]) for t in rest):
                rest.append(finite)
            command = "/" + " ".join(path + [token] + rest)
            return context, command
        elif "=" in token or token.startswith(("[", '"')):
            break
        else:
            path.append(token)
    else:
        return path, None
    # Ada argumen tapi tidak ada kata kerja: kirim apa adanya, RouterOS yang menolak.
    return context, "/" + " ".join(path + tokens[i:])


def failed(output):
    return bool(ERROR_RX.search(output))


# --- SSH -----------------------------------------------------------------------------

def container_ip(container):
    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", container],
        capture_output=True, text=True, timeout=5)
    ips = proc.stdout.split()
    if proc.returncode != 0 or not ips:
        raise ConnectionError(f"container {container} tidak berjalan atau tidak punya IP management")
    return ips[0]


def connect(lab_dir, node):
    import paramiko  # diimpor di sini: server/checkpoints tidak butuh paramiko untuk lab Linux

    topo = load_topology(lab_dir)
    host = container_ip(f"clab-{topo['name']}-{node}")
    client = paramiko.SSHClient()
    # Host key berubah setiap deploy dan alamatnya hanya di jaringan management lokal.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, username=USERNAME, password=PASSWORD, timeout=10,
                       look_for_keys=False, allow_agent=False, banner_timeout=20)
    except Exception as error:  # noqa: BLE001 - paramiko punya banyak jenis error koneksi
        raise ConnectionError(f"SSH ke {node} ({host}) gagal: {error}. RouterOS masih booting?") from error
    return client


def run(client, command, timeout=EXEC_TIMEOUT, echo=None):
    """Jalankan satu command. echo(chunk) dipanggil selama output mengalir."""
    channel = client.get_transport().open_session()
    channel.exec_command(command)
    chunks, deadline = [], time.time() + timeout
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([channel], [], [], 0.2)
            if ready:
                data = channel.recv(4096)
                if not data:
                    break
                text = data.decode(errors="replace").replace("\r\n", "\n").replace("\r", "")
                chunks.append(text)
                if echo:
                    echo(text)
            elif channel.exit_status_ready() and not channel.recv_ready():
                break
        else:
            chunks.append("\n[dihentikan: melewati batas waktu]\n")
    finally:
        channel.close()
    return "".join(chunks)


def exec_once(lab_dir, node, command, timeout=EXEC_TIMEOUT):
    """(output, ok). Dipakai checkpoints.py (state_check), inject.sh, dan verify.sh."""
    client = connect(lab_dir, node)
    try:
        output = run(client, command, timeout)
    finally:
        client.close()
    return output, not failed(output)


# --- shell pemain --------------------------------------------------------------------

def log_event(state, session, node, command, exit_code, output):
    from transcript import truncate
    event = {"ts": time.time(), "session": session, "node": node, "type": "command",
             "data": command, "exit": exit_code, "output": truncate(output.strip("\n"))}
    with open(state / "events" / f"{node}.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")


def completer_for(context_ref):
    def complete(text, state):
        import readline
        line = readline.get_line_buffer().lstrip()
        words = line.split()
        base = [] if line.startswith("/") else list(context_ref[0])
        prefix_words = [w.lstrip("/") for w in (words[:-1] if text else words)]
        key = " ".join(base + [w for w in prefix_words if w])
        options = [o for o in MENUS.get(key, []) if o.startswith(text)]
        return options[state] + " " if state < len(options) else None
    return complete


def shell(lab_dir, node):
    import readline

    lab_dir = Path(lab_dir).resolve()
    state = lab_dir / ".state"
    session = (state / "session_id").read_text().strip() if (state / "session_id").exists() else "unknown"
    try:
        client = connect(lab_dir, node)
    except ConnectionError as error:
        sys.exit(str(error))

    context = [[]]   # dibungkus list supaya completer melihat konteks terbaru
    readline.set_completer(completer_for(context))
    readline.set_completer_delims(" ")
    readline.parse_and_bind("tab: complete")
    print(f"MikroTik RouterOS · {node}. Ketik command seperti di CLI RouterOS "
          "(mis. /ip address print). `quit` untuk keluar.")
    print("ping, traceroute, dan monitor otomatis dibatasi (count/once) supaya selesai sendiri.\n")

    while True:
        where = "/" + " ".join(context[0]) if context[0] else ""
        try:
            line = input(f"[{USERNAME}@{node}] {where}> ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue
        if not line.strip():
            continue
        if line.strip() in ("quit", "/quit", "exit"):
            break
        new_context, command = resolve(context[0], line)
        if command is None:
            context[0] = new_context
            continue
        try:
            output = run(client, command, echo=lambda t: (sys.stdout.write(t), sys.stdout.flush()))
            code = 1 if failed(output) else 0
        except KeyboardInterrupt:
            output, code = "^C", 130
            print("^C")
        except Exception as error:  # noqa: BLE001 - koneksi putus: coba sambung ulang sekali
            print(f"koneksi ke {node} terputus ({error}), menyambung ulang…")
            try:
                client = connect(lab_dir, node)
                output = run(client, command, echo=lambda t: (sys.stdout.write(t), sys.stdout.flush()))
                code = 1 if failed(output) else 0
            except Exception as again:  # noqa: BLE001
                output, code = f"gagal: {again}", 255
                print(output)
        if output and not output.endswith("\n"):
            print()
        log_event(state, session, node, command, code, output)
    client.close()


def main(argv):
    if len(argv) >= 3 and argv[0] == "shell":
        shell(argv[1], argv[2])
    elif len(argv) >= 4 and argv[0] == "exec":
        try:
            output, ok = exec_once(argv[1], argv[2], " ".join(argv[3:]))
        except ConnectionError as error:
            print(error, file=sys.stderr)
            sys.exit(2)
        sys.stdout.write(output)
        sys.exit(0 if ok else 1)
    else:
        sys.exit(__doc__.strip())


if __name__ == "__main__":
    main(sys.argv[1:])
