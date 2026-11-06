"""Rekam perubahan konfigurasi RouterOS yang dibuat di luar terminal P-lab.

Terminal P-lab (ros.py shell) mencatat setiap command. Winbox, WebFig, API, atau
SSH langsung tidak melewati proxy itu, jadi perubahan dari sana tidak terlihat
oleh checkpoint dan penilaian. Modul ini menutup celah tersebut dari sisi router:

  1. Tiap POLL_INTERVAL detik, ambil `/export terse` dari tiap router.
  2. Bandingkan dengan snapshot sebelumnya. Kalau berbeda dan tidak ada command
     tulis dari terminal P-lab di node itu pada jendela waktu yang sama,
     perubahan itu dibuat dari luar.
  3. Terjemahkan selisihnya menjadi command RouterOS lengkap
     (`/ip address set [find interface=ether3] address=10.20.0.1/24`) dan tulis
     sebagai event biasa dengan `source`. Aturan NOS, safety, efficiency, dan
     state_check pun langsung berlaku tanpa diubah.

Login non-SSH (`via winbox`, `via web`, `via api`, ...) dibaca dari /log untuk
memberi label sumber, dan dicatat sebagai event `gui_login` supaya evaluator
tahu sesi ini memakai GUI walau belum ada perubahan.

Batasan yang tidak bisa diatasi: aktivitas MEMBACA di GUI (membuka tabel
IP > Addresses) tidak meninggalkan jejak di router. Lihat evaluate.py
(gui_usage) untuk cara penilaian menyikapinya.

Dijalankan sebagai thread di dalam `checkpoints.py watch`.
"""

import json
import re
import threading
import time
from pathlib import Path

import ros

POLL_INTERVAL = 3.0
# Jeda sebelum memutuskan sumber perubahan: ros.py shell menulis event setelah
# output command selesai, bisa sedikit setelah snapshot menangkap perubahannya.
GRACE = 2.0
EXTERNAL = "luar-terminal"   # sumber tidak diketahui (mis. SSH langsung)

GUI_LOGIN = re.compile(r"logged in from \S+ via (?P<via>[\w-]+)")
# Command terminal yang mungkin mengubah konfigurasi. Sengaja longgar: lebih baik
# perubahan dari terminal tidak tercatat dobel daripada salah dituduh dari GUI.
WRITE_CMD = re.compile(r"^[:{]|\b(add|set|remove|enable|disable|unset|reset|move|edit|comment|"
                       r"reboot|shutdown|import|run|make-static|reset-configuration)\b")
# Token export: [ find ... ], key="nilai dengan spasi", "teks", atau kata biasa.
TOKEN = re.compile(r'\[[^\]]*\]|[^\s"=]+=(?:"(?:\\.|[^"])*"|\S*)|"(?:\\.|[^"])*"|\S+')
VERBS = {"add", "set"}
# Kunci yang paling baik untuk menunjuk satu entri, urut prioritas.
IDENTITY = ("name", "default-name", "interface", "interfaces", "dst-address", "address", "comment")

_write_lock = threading.Lock()


# --- export → command ---------------------------------------------------------------

def parse_export(text):
    """Baris konfigurasi dari `/export terse` (tanpa komentar header)."""
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def split_line(line):
    """`/ip address add a=1 b=2` → ('/ip address', 'add', selector, {a: 1, b: 2})."""
    tokens = TOKEN.findall(line)
    for i, token in enumerate(tokens):
        if token in VERBS:
            menu, verb, rest = " ".join(tokens[:i]), token, tokens[i + 1:]
            break
    else:
        return None
    selector = rest.pop(0) if rest and rest[0].startswith("[") else ""
    values = {}
    for token in rest:
        key, _, value = token.partition("=")
        values[key] = value
    return menu, verb, selector, values


def show_selector(selector):
    """`[ find default-name=ether3 ]` → `ether3` (bentuk yang diketik orang dan
    yang dikenali aturan NOS); selector lain dirapikan spasinya."""
    inner = selector.strip("[] ").removeprefix("find").strip()
    m = re.fullmatch(r"default-name=(\S+)", inner)
    if m:
        return m.group(1)
    return f"[find {inner}]" if inner else ""


def selector_for(values):
    key = next((k for k in IDENTITY if k in values), None)
    if key is None and values:
        key = next(iter(values))
    return f"[find {key}={values[key]}]" if key else ""


def kv(values):
    return " ".join(f"{k}={v}" if v != "" else k for k, v in values.items())


def _command(*parts):
    return " ".join(p for p in parts if p)


def _pair(removed, added):
    """Pasangkan entri lama dan baru di menu yang sama (entri yang diedit).
    Skor = jumlah key=value yang identik; minimal satu."""
    pairs, free = [], list(added)
    for old in removed:
        best = max(free, key=lambda new: len(old.items() & new.items()), default=None)
        if best is not None and old.items() & best.items():
            pairs.append((old, best))
            free.remove(best)
        else:
            pairs.append((old, None))
    return pairs, free


def diff_commands(old_lines, new_lines):
    """Selisih dua export terse sebagai command RouterOS yang setara."""
    old_set, new_set = set(old_lines), set(new_lines)
    removed = [split_line(l) for l in old_lines if l not in new_set]
    added = [split_line(l) for l in new_lines if l not in old_set]
    removed, added = [r for r in removed if r], [a for a in added if a]
    commands = []

    # `set` = objek tunggal/bawaan (identitas = menu + selector): bandingkan per kunci.
    old_sets = {(m, s): v for m, verb, s, v in removed if verb == "set"}
    new_sets = {(m, s): v for m, verb, s, v in added if verb == "set"}
    for menu, sel in dict.fromkeys([*old_sets, *new_sets]):
        before, after = old_sets.get((menu, sel), {}), new_sets.get((menu, sel), {})
        changed = {k: v for k, v in after.items() if before.get(k) != v}
        changed.update({k: "(default)" for k in before if k not in after})
        if changed:
            commands.append(_command(menu, "set", show_selector(sel), kv(changed)))

    # `add` = entri di daftar: entri lama+baru yang mirip = diedit.
    menus = dict.fromkeys(m for m, verb, _, _ in removed + added if verb == "add")
    for menu in menus:
        gone = [v for m, verb, _, v in removed if verb == "add" and m == menu]
        new = [v for m, verb, _, v in added if verb == "add" and m == menu]
        pairs, fresh = _pair(gone, new)
        for before, after in pairs:
            if after is None:
                commands.append(_command(menu, "remove", selector_for(before)))
                continue
            shared = dict(before.items() & after.items())
            changed = {k: v for k, v in after.items() if before.get(k) != v}
            changed.update({k: "(default)" for k in before if k not in after})
            commands.append(_command(menu, "set", selector_for(shared), kv(changed)))
        commands += [_command(menu, "add", kv(values)) for values in fresh]
    return commands


# --- poller per router --------------------------------------------------------------

class RouterWatch(threading.Thread):
    def __init__(self, lab, node, interval=POLL_INTERVAL):
        super().__init__(daemon=True, name=f"guiwatch-{node}")
        self.lab, self.node, self.interval = lab, node, interval
        self.events_file = lab.events_dir / f"{node}.jsonl"
        self.snapshot = None       # baris export terakhir; bertahan saat koneksi putus
        self.seen_logins = None    # baris log login yang sudah diproses
        self.via = None            # cara login GUI terakhir di node ini
        self.polled_at = time.time()
        self.stop = threading.Event()

    def run(self):
        client = None
        while not self.stop.is_set():
            try:
                if client is None:
                    client = ros.connect(self.lab.dir, self.node)
                self.poll(client)
            except Exception:  # noqa: BLE001 - router reboot/booting: sambung ulang nanti
                if client is not None:
                    client.close()
                client = None
            self.stop.wait(self.interval)
        if client is not None:
            client.close()

    def poll(self, client):
        self.check_logins(ros.run(client, '/log print terse where message~"logged in"'))
        since = time.time()
        output = ros.run(client, "/export terse")
        if "[dihentikan:" in output:   # export terpotong timeout: jangan dibandingkan
            return
        lines = parse_export(output)
        if self.snapshot is None or not lines:
            self.snapshot = lines or self.snapshot
            self.polled_at = since
            return
        if lines == self.snapshot:
            self.polled_at = since
            return
        self.stop.wait(GRACE)
        if not self.terminal_wrote(self.polled_at - 1):
            source = self.via or EXTERNAL
            for command in diff_commands(self.snapshot, lines):
                self.emit({"type": "command", "data": command, "exit": 0, "source": source})
        self.snapshot, self.polled_at = lines, since

    def check_logins(self, text):
        lines = [l for l in text.splitlines() if GUI_LOGIN.search(l)]
        if self.seen_logins is None:   # login sebelum watcher jalan bukan bagian sesi ini
            self.seen_logins = set(lines)
            return
        for line in lines:
            if line in self.seen_logins:
                continue
            self.seen_logins.add(line)
            via = GUI_LOGIN.search(line).group("via")
            if via != "ssh":   # SSH tidak bisa dibedakan dari ros.py/state_check
                self.via = via
                self.emit({"type": "gui_login", "via": via})

    def terminal_wrote(self, since):
        """Adakah command tulis dari terminal P-lab di node ini sejak `since`?"""
        try:
            raw = self.events_file.read_text(errors="replace").splitlines()
        except FileNotFoundError:
            return False
        for line in reversed(raw):
            try:
                event = json.loads(line, strict=False)
            except json.JSONDecodeError:
                continue
            if event.get("ts", 0) < since:
                break
            if (event.get("type") == "command" and not event.get("source")
                    and event.get("session") == self.lab.session and WRITE_CMD.search(event.get("data", ""))):
                return True
        return False

    def emit(self, fields):
        event = {"ts": time.time(), "session": self.lab.session, "node": self.node, **fields}
        with _write_lock, open(self.events_file, "a") as f:
            f.write(json.dumps(event) + "\n")


def start(lab):
    """Jalankan RouterWatch untuk semua node RouterOS di lab; kembalikan thread-nya."""
    watchers = [RouterWatch(lab, node) for node, kind in lab.kinds.items() if kind == ros.ROS_KIND]
    for watcher in watchers:
        watcher.start()
    return watchers
