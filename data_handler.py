"""SQLite tabanlı hesap, sınıf, sınav ve sonuç işlemleri.

Bütün sınıf/sınav/sonuç işlevleri `owner_id` alır; bir öğretmen yalnızca
kendi verisini görür ve değiştirir.
"""

import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone


DB_PATH = os.getenv("SINAVMATIK_DB", os.path.join(os.path.dirname(__file__), "sinavmatik.db"))
SEMA_SURUMU = 2
OTURUM_SURESI_GUN = 14
GIRIS_DENEME_SINIRI = 5
GIRIS_KILIT_DAKIKA = 15

_SEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (
    email TEXT NOT NULL COLLATE NOCASE,
    attempted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course TEXT NOT NULL,
    class_name TEXT NOT NULL,
    UNIQUE(owner_id, course, class_name)
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    student_id TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(class_id, student_id)
);
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    course TEXT NOT NULL,
    class_name TEXT NOT NULL,
    exam_type TEXT NOT NULL DEFAULT 'Sınav',
    questions_json TEXT NOT NULL,
    total_points REAL NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exam_key_pages (
    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,
    image BLOB NOT NULL,
    PRIMARY KEY(exam_id, page_no)
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id TEXT NOT NULL,
    student_name TEXT NOT NULL DEFAULT '',
    scores_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    approved INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(exam_id, student_id)
);
CREATE TABLE IF NOT EXISTS result_pages (
    result_id INTEGER NOT NULL REFERENCES results(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,
    image BLOB NOT NULL,
    PRIMARY KEY(result_id, page_no)
);
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    islem TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0
);
"""


def _simdi():
    return datetime.now(timezone.utc)


def _connect(db_path=None):
    connection = sqlite3.connect(db_path or DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _sutunlar(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def veritabani_hazirla(db_path=None):
    """Tabloları oluştur; eski (hesaba bağlı olmayan) veritabanını yeni şemaya taşı."""
    conn = _connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        # İlk sürümde sınıflar hesaba bağlı değildi; tabloyu sahip sütunuyla yeniden kur.
        if "classes" in tables and "owner_id" not in _sutunlar(conn, "classes"):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL, password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE classes_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    course TEXT NOT NULL, class_name TEXT NOT NULL,
                    UNIQUE(owner_id, course, class_name));
                INSERT INTO classes_v2(id, owner_id, course, class_name)
                    SELECT id, (SELECT MIN(id) FROM users), course, class_name FROM classes
                    WHERE (SELECT MIN(id) FROM users) IS NOT NULL;
                DROP TABLE classes;
                ALTER TABLE classes_v2 RENAME TO classes;
                """
            )
        conn.executescript(_SEMA)
        exam_columns = _sutunlar(conn, "exams")
        if "exam_type" not in exam_columns:
            conn.execute("ALTER TABLE exams ADD COLUMN exam_type TEXT NOT NULL DEFAULT 'Sınav'")
        if "total_points" not in exam_columns:
            conn.execute("ALTER TABLE exams ADD COLUMN total_points REAL NOT NULL DEFAULT 100")
        if "owner_id" not in exam_columns:
            conn.execute("ALTER TABLE exams ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        conn.execute("UPDATE exams SET owner_id=(SELECT MIN(id) FROM users) WHERE owner_id IS NULL")
        if "warnings_json" not in _sutunlar(conn, "results"):
            conn.execute("ALTER TABLE results ADD COLUMN warnings_json TEXT NOT NULL DEFAULT '[]'")
        conn.execute(f"PRAGMA user_version = {SEMA_SURUMU}")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- hesaplar

def _sifre_ozeti(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000).hex()


def kullanici_olustur(email, display_name, password, db_path=None):
    """Yerel hesap oluştur; şifre tuzlanmış PBKDF2 özeti olarak saklanır."""
    email = email.strip().lower()
    display_name = display_name.strip()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email or not display_name:
        return False, "Ad soyad ve geçerli bir e-posta adresi girin."
    if len(password) < 8:
        return False, "Şifreniz en az 8 karakter olmalı."
    salt = secrets.token_bytes(16)
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "INSERT INTO users(email, display_name, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (email, display_name, salt.hex(), _sifre_ozeti(password, salt), _simdi().isoformat()),
            )
        return True, "Hesabınız hazır. Şimdi giriş yapabilirsiniz."
    except sqlite3.IntegrityError:
        return False, "Bu e-posta adresiyle zaten bir hesap var."


def kullanici_dogrula(email, password, db_path=None):
    """Giriş bilgilerini doğrula. (kullanıcı | None, hata mesajı) döndürür."""
    email = email.strip().lower()
    window_start = (_simdi() - timedelta(minutes=GIRIS_KILIT_DAKIKA)).isoformat()
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (window_start,))
        failed = conn.execute("SELECT COUNT(*) AS n FROM login_attempts WHERE email=?", (email,)).fetchone()["n"]
        if failed >= GIRIS_DENEME_SINIRI:
            return None, f"Çok fazla hatalı deneme. {GIRIS_KILIT_DAKIKA} dakika sonra yeniden deneyin."
        user = conn.execute(
            "SELECT id, email, display_name, password_salt, password_hash FROM users WHERE email=?", (email,)
        ).fetchone()
        valid = user is not None and hmac.compare_digest(
            _sifre_ozeti(password, bytes.fromhex(user["password_salt"])), user["password_hash"])
        if not valid:
            conn.execute("INSERT INTO login_attempts(email, attempted_at) VALUES (?, ?)", (email, _simdi().isoformat()))
            return None, "E-posta veya şifre hatalı."
        conn.execute("DELETE FROM login_attempts WHERE email=?", (email,))
    return {"id": user["id"], "email": user["email"], "display_name": user["display_name"]}, ""


def sifre_degistir(user_id, current_password, new_password, db_path=None):
    if len(new_password) < 8:
        return False, "Yeni şifre en az 8 karakter olmalı."
    with _connect(db_path) as conn:
        user = conn.execute("SELECT password_salt, password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if user is None or not hmac.compare_digest(
                _sifre_ozeti(current_password, bytes.fromhex(user["password_salt"])), user["password_hash"]):
            return False, "Mevcut şifre hatalı."
        salt = secrets.token_bytes(16)
        conn.execute("UPDATE users SET password_salt=?, password_hash=? WHERE id=?",
                     (salt.hex(), _sifre_ozeti(new_password, salt), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    return True, "Şifreniz güncellendi."


def _token_ozeti(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def oturum_olustur(user_id, db_path=None):
    """Tarayıcı çerezinde tutulacak oturum anahtarı üret; veritabanında yalnızca özeti saklanır."""
    token = secrets.token_urlsafe(32)
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_simdi().isoformat(),))
        conn.execute("INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                     (_token_ozeti(token), user_id, (_simdi() + timedelta(days=OTURUM_SURESI_GUN)).isoformat()))
    return token
