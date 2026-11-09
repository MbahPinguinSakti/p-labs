"""Modul akun: pengguna, password, dan sesi login P-lab (SQLite, tanpa dependensi).

Keputusan desain:
- Akun dibuat admin (CLI p-lab-admin atau import CSV); tidak ada registrasi bebas.
  Role: admin (kelola akun), guru (melihat progres siswa di mode kelas), siswa.
- username dibatasi `^[a-z0-9][a-z0-9-]{0,31}$` (tanpa minus di depan, `local` dicadangkan) karena dipakai sebagai nama folder
  instance lab dan nama lab containerlab: aman untuk path dan nama container,
  tidak mungkin berisi `../`, spasi, atau huruf besar.
- Password di-hash dengan scrypt (hashlib, stdlib), salt acak per user. Format
  `scrypt$n$r$p$salt_b64$hash_b64` menyimpan parameternya, jadi parameter bisa
  dinaikkan nanti tanpa merusak hash lama (verifikasi memakai parameter tersimpan).
  Perbandingan dengan hmac.compare_digest. Login user yang tidak ada tetap
  menghitung satu hash palsu supaya waktu respons tidak membocorkan username.
- Token sesi acak `secrets.token_urlsafe(32)` hanya dikembalikan ke pemanggil;
  DB menyimpan sha256-nya, sehingga bocornya file DB tidak membocorkan sesi aktif.
  Token berumur SESSION_TTL sejak login (tidak diperpanjang oleh aktivitas;
  last_seen hanya untuk informasi). Menonaktifkan user mematikan semua sesinya.
- Threading: satu koneksi SQLite BARU per operasi (murah untuk file lokal) dan
  mode WAL + busy timeout. Tidak ada koneksi bersama, jadi aman untuk thread pool
  FastAPI tanpa lock. Waktu diambil dari `clock` yang bisa diinjeksi (test).
- import_csv: PER BARIS. Baris valid dimasukkan, baris rusak (username salah,
  role tidak valid, duplikat, password pendek) dilaporkan dengan nomor barisnya
  dan tidak membatalkan yang lain. Alasannya: satu salah ketik di daftar 40 siswa
  tidak boleh menggagalkan semuanya; admin cukup memperbaiki baris yang gagal dan
  mengimpor ulang file kecil itu. Password kosong -> password acak, dikembalikan
  di hasil agar admin bisa membagikannya (tidak disimpan dalam bentuk asli).
- Admin terakhir (aktif) tidak bisa dinonaktifkan, diturunkan, atau dihapus,
  supaya sistem tidak terkunci.
"""

import base64
import csv
import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

ROLES = ("admin", "guru", "siswa")
USERNAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")   # sama dengan instance.USER_RX
RESERVED = {"local"}   # nama instance install pribadi (lihat instance.py)
MIN_PASSWORD = 8
MAX_PASSWORD = 256
SESSION_TTL = 12 * 3600          # detik
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
SCRYPT_MAXMEM = 128 * 1024 * 1024
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','guru','siswa')),
    pw_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE login_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    last_seen REAL NOT NULL
);
CREATE INDEX idx_sessions_user ON login_sessions(user_id);
"""


class AccountError(Exception):
    """Kesalahan yang pesannya (Bahasa Indonesia) aman ditampilkan ke user."""


# --- password -----------------------------------------------------------------

def _scrypt(password, salt, n, r, p, dklen=32):
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p,
                          dklen=dklen, maxmem=SCRYPT_MAXMEM)


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_DUMMY_HASH = hash_password("tidak-dipakai")


def check_password_policy(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise AccountError(f"Password minimal {MIN_PASSWORD} karakter.")
    if len(password) > MAX_PASSWORD:
        raise AccountError(f"Password maksimal {MAX_PASSWORD} karakter.")


def random_password():
    # 12 karakter dari alfabet tanpa karakter membingungkan (0/O, 1/l/I)
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def validate_username(username):
    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
        raise AccountError("Username hanya boleh huruf kecil, angka, dan tanda minus "
                           "(a-z, 0-9, -), 1 sampai 32 karakter, dan tidak diawali minus.")
    if username in RESERVED:
        raise AccountError(f"Username '{username}' dicadangkan sistem, pilih nama lain.")
    return username


def validate_role(role):
    if role not in ROLES:
        raise AccountError(f"Role tidak valid: {role!r}. Pilihan: {', '.join(ROLES)}.")
    return role


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _public(row):
    """Baris user tanpa pw_hash (aman dikirim ke pemanggil/UI)."""
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"],
            "role": row["role"], "active": bool(row["active"]), "created_at": row["created_at"]}


class ImportResult:
    """created: [(username, password_acak_atau_None)]; errors: [(nomor_baris, pesan)]."""

    def __init__(self):
        self.created = []
        self.errors = []


def default_db():
    """<data_dir>/p-lab.db dari config: pribadi <repo>/var/p-lab.db, server mis. /var/lib/p-lab/p-lab.db."""
    import config
    return config.load().db_path


class AccountStore:
    def __init__(self, db_path=None, clock=time.time, session_ttl=SESSION_TTL):
        self.path = Path(db_path or os.environ.get("LAB_DB") or default_db())
        self.clock = clock
        self.session_ttl = session_ttl
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        old_umask = os.umask(0o077)   # DB, -wal, -shm: hanya pemilik (isi hash password)
        try:
            self._init_db()
        finally:
            os.umask(old_umask)
        self.path.chmod(0o600)

    # -- koneksi ----------------------------------------------------------------
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        db.execute(statement)
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version > SCHEMA_VERSION:
                db.execute("ROLLBACK")
                raise AccountError("Database akun dibuat oleh versi P-lab yang lebih baru.")
            if db.in_transaction:
                db.execute("COMMIT")

    # -- manajemen user -----------------------------------------------------------
    def create_user(self, username, password, role="siswa", display_name=None):
        validate_username(username)
        validate_role(role)
        check_password_policy(password)
        display = (display_name or "").strip() or username
        pw_hash = hash_password(password)
        with closing(self._connect()) as db:
            try:
                cur = db.execute(
                    "INSERT INTO users(username, display_name, role, pw_hash, active, created_at) "
                    "VALUES (?,?,?,?,1,?)", (username, display, role, pw_hash, self.clock()))
            except sqlite3.IntegrityError:
                raise AccountError(f"Username '{username}' sudah dipakai.")
            return self._get(db, cur.lastrowid)

    def _row(self, db, user):
        """Cari baris user dari id atau username; AccountError kalau tidak ada."""
        col = "id" if isinstance(user, int) else "username"
        row = db.execute(f"SELECT * FROM users WHERE {col} = ?", (user,)).fetchone()
        if not row:
            raise AccountError(f"User '{user}' tidak ditemukan.")
        return row

    def _get(self, db, user):
        return _public(self._row(db, user))

    def get_user(self, user):
        """user = id (int) atau username (str). None kalau tidak ada."""
        with closing(self._connect()) as db:
            try:
                return self._get(db, user)
            except AccountError:
                return None

    def list_users(self, role=None):
        with closing(self._connect()) as db:
            sql, args = "SELECT * FROM users", ()
            if role:
                sql, args = sql + " WHERE role = ?", (validate_role(role),)
            return [_public(r) for r in db.execute(sql + " ORDER BY username", args)]

    def count_admins(self):
        with closing(self._connect()) as db:
            return self._count_admins(db)

    @staticmethod
    def _count_admins(db):
        return db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]

    def set_password(self, user, password):
        check_password_policy(password)
        with closing(self._connect()) as db:
            row = self._row(db, user)
            db.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_password(password), row["id"]))
            db.execute("DELETE FROM login_sessions WHERE user_id = ?", (row["id"],))

    def _guard_last_admin(self, db, row, what):
        if row["role"] == "admin" and row["active"] and self._count_admins(db) <= 1:
            raise AccountError(f"Tidak bisa {what}: ini admin aktif terakhir.")

    def set_role(self, user, role):
        validate_role(role)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(db, user)
                if role != "admin":
                    self._guard_last_admin(db, row, "menurunkan role")
                db.execute("UPDATE users SET role = ? WHERE id = ?", (role, row["id"]))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            return self._get(db, row["id"])

    def set_active(self, user, active):
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(db, user)
                if not active:
                    self._guard_last_admin(db, row, "menonaktifkan akun")
                db.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, row["id"]))
                if not active:
                    db.execute("DELETE FROM login_sessions WHERE user_id = ?", (row["id"],))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            return self._get(db, row["id"])

    def delete_user(self, user):
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(db, user)
                self._guard_last_admin(db, row, "menghapus akun")
                db.execute("DELETE FROM login_sessions WHERE user_id = ?", (row["id"],))
                db.execute("DELETE FROM users WHERE id = ?", (row["id"],))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    # -- sesi login ---------------------------------------------------------------
    def login(self, username, password):
        """Token sesi kalau username+password benar dan akun aktif, selain itu None."""
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM users WHERE username = ?",
                             (username if isinstance(username, str) else "",)).fetchone()
            ok = verify_password(password if isinstance(password, str) else "",
                                 row["pw_hash"] if row else _DUMMY_HASH)
            if not (row and ok and row["active"]):
                return None
            now = self.clock()
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO login_sessions VALUES (?,?,?,?,?)",
                       (_token_hash(token), row["id"], now, now + self.session_ttl, now))
            return token

    def user_for_token(self, token):
        """User (tanpa pw_hash) untuk token yang valid, belum kedaluwarsa, dan akunnya aktif."""
        if not token or not isinstance(token, str):
            return None
        with closing(self._connect()) as db:
            now = self.clock()
            th = _token_hash(token)
            row = db.execute(
                "SELECT u.*, s.expires_at FROM login_sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = ?", (th,)).fetchone()
            if not row:
                return None
            if row["expires_at"] <= now:
                db.execute("DELETE FROM login_sessions WHERE token_hash = ?", (th,))
                return None
            if not row["active"]:
                return None
            db.execute("UPDATE login_sessions SET last_seen = ? WHERE token_hash = ?", (now, th))
            return _public(row)

    def logout(self, token):
        if not token or not isinstance(token, str):
            return
        with closing(self._connect()) as db:
            db.execute("DELETE FROM login_sessions WHERE token_hash = ?", (_token_hash(token),))

    def logout_all(self, user):
        with closing(self._connect()) as db:
            row = self._row(db, user)
            db.execute("DELETE FROM login_sessions WHERE user_id = ?", (row["id"],))

    def purge_expired(self):
        """Hapus sesi kedaluwarsa; mengembalikan jumlah yang dihapus."""
        with closing(self._connect()) as db:
            return db.execute("DELETE FROM login_sessions WHERE expires_at <= ?",
                              (self.clock(),)).rowcount

    # -- import CSV ---------------------------------------------------------------
    def import_csv(self, source, default_role="siswa"):
        """Impor `username,display_name,role,password` (path atau file teks).

        Per baris (lihat docstring modul). role kosong -> default_role, password
        kosong -> acak. Header wajib ada.
        """
        if isinstance(source, (str, Path)):
            try:
                with open(source, newline="", encoding="utf-8-sig") as f:
                    return self.import_csv(f, default_role)
            except OSError as error:
                raise AccountError(f"Tidak bisa membaca file CSV: {error.strerror or error}")
        reader = csv.DictReader(source)
        fields = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
        if "username" not in fields:
            raise AccountError("CSV harus punya header: username,display_name,role,password.")
        reader.fieldnames = fields
        result = ImportResult()
        for row in reader:
            line = reader.line_num
            get = lambda k: (row.get(k) or "").strip()
            username, role = get("username"), get("role") or default_role
            password = row.get("password") or ""
            generated = None
            try:
                if not password:
                    generated = password = random_password()
                self.create_user(username, password, role, get("display_name"))
                result.created.append((username, generated))
            except AccountError as error:
                result.errors.append((line, f"{username or '(kosong)'}: {error}"))
        return result
