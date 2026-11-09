"""Konfigurasi P-lab: mode Pribadi / Server dari satu file YAML.

Lokasi file: env LAB_CONFIG, kalau tidak ada /etc/p-lab/server.yaml. Tanpa file
sama sekali, P-lab berjalan sebagai mode Pribadi dengan default (data di
<repo>/var, 127.0.0.1:8000), jadi instalasi pribadi tidak perlu config.
Contoh lengkap berkomentar: platform/templates/server.yaml.

Keputusan desain:
- Semua masalah dikumpulkan lalu dilaporkan sekaligus (ConfigError.problems).
  Admin yang mengisi 6 nilai tidak boleh harus memperbaiki-dan-mencoba-lagi
  satu per satu.
- Kunci yang tidak dikenal dianggap masalah: `idle_minute: 5` (salah ketik)
  yang diam-diam diabaikan membuat admin mengira batasnya sudah terpasang.
- Mode pribadi dengan `listen` non-lokal adalah ERROR, bukan diabaikan diam-diam.
  Mengabaikan membuat admin mengira server terbuka di LAN padahal tidak (atau
  sebaliknya, kalau nanti aturannya berubah); error memaksa dia memilih: ganti
  `mode: server` atau hapus baris listen.
- Mode server mewajibkan data_dir absolut: unit systemd jalan dengan direktori
  kerja yang berbeda, path relatif akan menunjuk tempat yang tidak disangka.
- Tidak ada efek samping saat import: file baru dibaca di load().
- allowed_hosts / trusted_proxies hanya bermakna di mode server; di mode pribadi
  keduanya ERROR (alasan sama dengan listen): Host pribadi selalu dikunci ke
  localhost, dan tidak ada proxy di depan server yang hanya listen di 127.0.0.1.
"""

import ipaddress
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = Path("/etc/p-lab/server.yaml")
MODES = ("pribadi", "server")
STYLES = ("mandiri", "kelas")
LOCAL_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
SERVER_DATA_DIR = "/var/lib/p-lab"

KNOWN_KEYS = {"mode", "listen", "data_dir", "style", "capacity", "allowed_hosts", "trusted_proxies"}
CAPACITY_KEYS = {"mem_mb", "max_deploys", "idle_minutes"}
HOSTNAME_RE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")


class ConfigError(Exception):
    """Config tidak valid; `problems` berisi SEMUA masalah (kalimat Indonesia)."""

    def __init__(self, problems, path=None):
        self.problems = list(problems)
        self.path = path
        where = f" ({path})" if path else ""
        super().__init__(f"Config tidak valid{where}:\n" + "\n".join(f"  - {p}" for p in self.problems))


@dataclass(frozen=True)
class Capacity:
    mem_mb: int = 24000
    max_deploys: int = 2
    idle_minutes: int = 30


@dataclass(frozen=True)
class Config:
    mode: str = "pribadi"
    host: str = LOCAL_HOST
    port: int = DEFAULT_PORT
    data_dir: Path = ROOT / "var"
    style: str = "mandiri"
    capacity: Capacity = field(default_factory=Capacity)
    # Nama host/IP (tanpa port, huruf kecil) yang boleh muncul di header Host.
    # Kosong = mode server menerima Host apa pun (server.py memberi peringatan).
    allowed_hosts: tuple = ()
    # ipaddress.ip_network: reverse proxy yang header X-Forwarded-* -nya dipercaya.
    trusted_proxies: tuple = ()
    path: Path = None            # file config yang dibaca (None = default bawaan)

    @property
    def is_server(self):
        return self.mode == "server"

    @property
    def listen(self):
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"

    @property
    def db_path(self):
        return self.data_dir / "p-lab.db"


def config_path():
    return Path(os.environ.get("LAB_CONFIG") or DEFAULT_PATH)


def parse_listen(value):
    """'host:port' atau '[::1]:port' -> (host, port); ValueError kalau rusak."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("harus berupa teks 'host:port', contoh 0.0.0.0:8000")
    text = value.strip()
    if text.startswith("["):
        host, sep, port = text[1:].partition("]:")
        if not sep:
            raise ValueError(f"format salah: {value!r} (contoh [::1]:8000)")
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise ValueError(f"alamat IPv6 salah: {host!r}") from None
    else:
        host, sep, port = text.rpartition(":")
        if not sep or not host:
            raise ValueError(f"format salah: {value!r} (contoh 0.0.0.0:8000)")
        if ":" in host:
            raise ValueError("IPv6 harus ditulis dalam kurung siku, contoh [::1]:8000")
        looks_ip = re.fullmatch(r"[0-9.]+", host)
        if looks_ip:
            try:
                ipaddress.IPv4Address(host)
            except ValueError:
                raise ValueError(f"alamat IPv4 salah: {host!r}") from None
        elif not HOSTNAME_RE.fullmatch(host):
            raise ValueError(f"nama host salah: {host!r}")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError(f"port harus angka 1-65535, dapat {port!r}")
    return host, int(port)


def is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalize_host(value):
    """'[::1]' / 'Plab.Sekolah' -> '::1' / 'plab.sekolah'; ValueError kalau bukan nama/IP."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("harus berupa nama host atau IP")
    text = value.strip().lower()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        pass
    if re.fullmatch(r"[0-9.]+", text) or not HOSTNAME_RE.fullmatch(text):
        raise ValueError(f"bukan nama host atau IP yang valid (tanpa port/skema): {value!r}")
    return text


def _list(data, key, problems):
    raw = data.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        problems.append(f"{key} harus berupa daftar, contoh: {key}: [192.168.1.10]")
        return []
    return raw


def _positive_int(value, name, problems):
    # bool adalah subclass int di Python: `max_deploys: true` harus ditolak
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        problems.append(f"{name} harus bilangan bulat positif, dapat {value!r}.")
        return None
    return value


def _read(path, explicit):
    if not path.exists():
        if explicit:
            raise ConfigError([f"file config tidak ada: {path}"], path)
        return None, {}
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError([f"file config tidak bisa dibaca: {exc}"], path) from None
    except yaml.YAMLError as exc:
        raise ConfigError([f"YAML rusak: {str(exc).splitlines()[0] if str(exc) else exc}"], path) from None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(["isi file harus berupa pasangan kunci: nilai"], path)
    return path, data


def from_dict(data, path=None):
    """Validasi dict hasil YAML -> Config. Mengumpulkan semua masalah."""
    problems = []
    for key in sorted(set(data) - KNOWN_KEYS, key=str):
        problems.append(f"kunci tidak dikenal: {key!r} (yang ada: {', '.join(sorted(KNOWN_KEYS))}).")

    mode = data.get("mode", "pribadi")
    if mode not in MODES:
        problems.append(f"mode harus salah satu dari {' | '.join(MODES)}, dapat {mode!r}.")
        mode = None
    style = data.get("style", "mandiri")
    if style not in STYLES:
        problems.append(f"style harus salah satu dari {' | '.join(STYLES)}, dapat {style!r}.")

    host, port = LOCAL_HOST, DEFAULT_PORT
    if "listen" in data:
        try:
            host, port = parse_listen(data["listen"])
        except ValueError as exc:
            problems.append(f"listen {exc}.")
            host, port = LOCAL_HOST, DEFAULT_PORT
        else:
            if mode == "pribadi" and not is_loopback(host):
                problems.append(
                    f"mode pribadi hanya boleh listen di alamat lokal (127.0.0.1), dapat {host!r}. "
                    "Pakai `mode: server` untuk melayani jaringan, atau hapus baris listen.")
            elif mode == "pribadi":
                host = LOCAL_HOST
    elif mode == "server":
        host = "0.0.0.0"   # server yang tidak bisa dijangkau klien tidak berguna

    default_dir = SERVER_DATA_DIR if mode == "server" else str(ROOT / "var")
    raw_dir = data.get("data_dir", default_dir)
    data_dir = None
    if not isinstance(raw_dir, str) or not raw_dir.strip():
        problems.append(f"data_dir harus berupa path, dapat {raw_dir!r}.")
    else:
        data_dir = Path(raw_dir).expanduser()
        if mode == "server" and not data_dir.is_absolute():
            problems.append(f"data_dir harus path absolut di mode server, dapat {raw_dir!r}.")
        elif not data_dir.is_absolute():
            data_dir = ROOT / data_dir

    cap_raw = data.get("capacity", {})
    cap = {}
    if cap_raw is None:
        cap_raw = {}
    if not isinstance(cap_raw, dict):
        problems.append("capacity harus berisi mem_mb, max_deploys, idle_minutes.")
        cap_raw = {}
    for key in sorted(set(cap_raw) - CAPACITY_KEYS, key=str):
        problems.append(f"kunci tidak dikenal di capacity: {key!r} (yang ada: {', '.join(sorted(CAPACITY_KEYS))}).")
    for key in CAPACITY_KEYS:
        if key in cap_raw:
            val = _positive_int(cap_raw[key], f"capacity.{key}", problems)
            if val is not None:
                cap[key] = val

    hosts, proxies = [], []
    for item in _list(data, "allowed_hosts", problems):
        try:
            hosts.append(normalize_host(item))
        except ValueError as exc:
            problems.append(f"allowed_hosts: {exc}.")
    for item in _list(data, "trusted_proxies", problems):
        try:
            # strict=False: '10.0.0.5/24' diterima sebagai 10.0.0.0/24, bukan error.
            proxies.append(ipaddress.ip_network(str(item).strip(), strict=False))
        except ValueError:
            problems.append(f"trusted_proxies: {item!r} bukan IP atau CIDR (contoh 127.0.0.1, 10.0.0.0/24).")
    if mode == "pribadi":
        for key in ("allowed_hosts", "trusted_proxies"):
            if data.get(key):
                problems.append(f"{key} hanya berlaku di mode server; mode pribadi selalu hanya menerima "
                                "localhost. Hapus barisnya atau pakai `mode: server`.")

    if problems:
        raise ConfigError(problems, path)
    return Config(mode=mode, host=host, port=port, data_dir=data_dir, style=style,
                  capacity=Capacity(**cap), allowed_hosts=tuple(dict.fromkeys(hosts)),
                  trusted_proxies=tuple(proxies), path=path)


def load(path=None):
    """Baca config. path eksplisit atau env LAB_CONFIG yang hilang = error;
    file default (/etc/p-lab/server.yaml) yang hilang = mode pribadi bawaan."""
    explicit = path is not None or bool(os.environ.get("LAB_CONFIG"))
    found, data = _read(Path(path) if path is not None else config_path(), explicit)
    return from_dict(data, found)
