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
def oturum_kullanicisi(token, db_path=None):
    if not token:
        return None
    with _connect(db_path) as conn:
        row = conn.execute(
            """SELECT u.id, u.email, u.display_name FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.expires_at > ?""", (_token_ozeti(token), _simdi().isoformat())
        ).fetchone()
    return dict(row) if row else None


def oturum_sil(token, db_path=None):
    if token:
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_ozeti(token),))


def hesap_verilerini_sil(owner_id, db_path=None):
    """Öğretmenin bütün sınıf, öğrenci, sınav, sonuç ve kâğıt görsellerini kalıcı olarak sil."""
    with _connect(db_path) as conn:
        exam_ids = [row["id"] for row in conn.execute("SELECT id FROM exams WHERE owner_id=?", (owner_id,))]
        for exam_id in exam_ids:
            _sinav_sil(conn, exam_id)
        conn.execute("DELETE FROM classes WHERE owner_id=?", (owner_id,))
        conn.execute("DELETE FROM usage_log WHERE owner_id=?", (owner_id,))


# ----------------------------------------------------- sınıflar, öğrenciler

def _temiz(value):
    """Tablo düzenleyicisinden gelen boş hücreleri (None/NaN) boş metne çevir."""
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            value = int(value)
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none", "<na>") else text


def _sinif_id(conn, owner_id, course, class_name):
    row = conn.execute("SELECT id FROM classes WHERE owner_id=? AND course=? AND class_name=?",
                       (owner_id, course, class_name)).fetchone()
    return row["id"] if row else None


def sinif_ekle(owner_id, course, class_name, db_path=None):
    course, class_name = course.strip(), class_name.strip()
    if not course or not class_name:
        raise ValueError("Ders ve sınıf bilgilerini girin.")
    with _connect(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO classes(owner_id, course, class_name) VALUES (?, ?, ?)",
                     (owner_id, course, class_name))
        return _sinif_id(conn, owner_id, course, class_name)


def siniflari_getir(owner_id, db_path=None):
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT c.id, c.course, c.class_name, COUNT(s.id) AS ogrenci_sayisi
               FROM classes c LEFT JOIN students s ON s.class_id=c.id
               WHERE c.owner_id=? GROUP BY c.id ORDER BY c.course, c.class_name""", (owner_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def sinif_sil(owner_id, course, class_name, db_path=None):
    """Sınıfı, öğrenci listesini ve o sınıfa ait sınavları (sonuçlarıyla) sil."""
    with _connect(db_path) as conn:
        for row in conn.execute("SELECT id FROM exams WHERE owner_id=? AND course=? AND class_name=?",
                                (owner_id, course, class_name)).fetchall():
            _sinav_sil(conn, row["id"])
        conn.execute("DELETE FROM classes WHERE owner_id=? AND course=? AND class_name=?",
                     (owner_id, course, class_name))


def ogrencileri_getir(owner_id, course, class_name, db_path=None):
    with _connect(db_path) as conn:
        class_id = _sinif_id(conn, owner_id, course, class_name)
        if class_id is None:
            return []
        students = conn.execute("SELECT student_id, name FROM students WHERE class_id=? ORDER BY id",
                                (class_id,)).fetchall()
    return [dict(student) for student in students]


def sinif_ogrenci_listesi_kaydet(owner_id, course, class_name, students, db_path=None):
    """Sınıf listesini verilen satırlarla değiştir; numarası veya adı boş satırlar atlanır."""
    class_id = sinif_ekle(owner_id, course, class_name, db_path)
    cleaned = {}
    for student in students:
        student_id, name = _temiz(student.get("student_id")), _temiz(student.get("name"))
        if student_id and name:
            cleaned[student_id] = name
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM students WHERE class_id=?", (class_id,))
        conn.executemany("INSERT INTO students(class_id, student_id, name) VALUES (?, ?, ?)",
                         [(class_id, student_id, name) for student_id, name in cleaned.items()])
    return len(cleaned)


def ogrenci_ekle(owner_id, course, class_name, student_id, name, db_path=None):
    student_id, name = _temiz(student_id), _temiz(name)
    if not student_id or not name:
        return
    class_id = sinif_ekle(owner_id, course, class_name, db_path)
    with _connect(db_path) as conn:
        conn.execute("INSERT INTO students(class_id, student_id, name) VALUES (?, ?, ?) "
                     "ON CONFLICT(class_id, student_id) DO UPDATE SET name=excluded.name",
                     (class_id, student_id, name))


# ---------------------------------------------------------------- sınavlar

def _sinav_dict(row):
    return dict(row) | {"questions": json.loads(row["questions_json"])}


def _sinav_sahibi_mi(conn, owner_id, exam_id):
    return conn.execute("SELECT 1 FROM exams WHERE id=? AND owner_id=?", (exam_id, owner_id)).fetchone() is not None


def _sinav_sil(conn, exam_id):
    # Eski veritabanlarında results→exams bağında CASCADE yok; elle temizle.
    conn.execute("DELETE FROM result_pages WHERE result_id IN (SELECT id FROM results WHERE exam_id=?)", (exam_id,))
    conn.execute("DELETE FROM results WHERE exam_id=?", (exam_id,))
    conn.execute("DELETE FROM exam_key_pages WHERE exam_id=?", (exam_id,))
    conn.execute("DELETE FROM exams WHERE id=?", (exam_id,))


def sinav_ekle(owner_id, name, course, class_name, questions=None, exam_type="Sınav", total_points=100, db_path=None):
    if not name.strip():
        raise ValueError("Sınav adı gerekli.")
    sinif_ekle(owner_id, course, class_name, db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO exams(owner_id, name, course, class_name, exam_type, questions_json, total_points, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (owner_id, name.strip(), course.strip(), class_name.strip(), exam_type,
             json.dumps(questions or [], ensure_ascii=False), float(total_points), _simdi().isoformat()),
        )
        return cursor.lastrowid


def sinavlari_getir(owner_id, db_path=None):
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM exams WHERE owner_id=? ORDER BY created_at DESC, id DESC",
                            (owner_id,)).fetchall()
    return [_sinav_dict(row) for row in rows]


def sinav_getir(owner_id, exam_id, db_path=None):
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM exams WHERE id=? AND owner_id=?", (exam_id, owner_id)).fetchone()
    return _sinav_dict(row) if row else None


def sinav_guncelle(owner_id, exam_id, name, exam_type, total_points, db_path=None):
    if not name.strip():
        raise ValueError("Sınav adı gerekli.")
    with _connect(db_path) as conn:
        conn.execute("UPDATE exams SET name=?, exam_type=?, total_points=? WHERE id=? AND owner_id=?",
                     (name.strip(), exam_type, float(total_points), exam_id, owner_id))


def sinav_sorulari_kaydet(owner_id, exam_id, questions, db_path=None):
    """Sınavın soru şablonunu (soru no, özet, maksimum puan, doğru cevap) kaydet."""
    cleaned = []
    seen = set()
    for question in questions:
        try:
            number = int(float(question.get("soru_no")))
            maximum = float(question.get("maksimum_puan"))
        except (TypeError, ValueError):
            continue
        if number in seen or not math.isfinite(maximum) or maximum < 0:
            continue
        seen.add(number)
        cleaned.append({"soru_no": number, "soru_ozeti": _temiz(question.get("soru_ozeti")),
                        "maksimum_puan": maximum, "dogru_cevap": _temiz(question.get("dogru_cevap"))})
    cleaned.sort(key=lambda q: q["soru_no"])
    with _connect(db_path) as conn:
        conn.execute("UPDATE exams SET questions_json=? WHERE id=? AND owner_id=?",
                     (json.dumps(cleaned, ensure_ascii=False), exam_id, owner_id))
    return cleaned


def sinav_sil(owner_id, exam_id, db_path=None):
    with _connect(db_path) as conn:
        if _sinav_sahibi_mi(conn, owner_id, exam_id):
            _sinav_sil(conn, exam_id)


def anahtar_sayfalari_kaydet(owner_id, exam_id, page_images, db_path=None):
    with _connect(db_path) as conn:
        if not _sinav_sahibi_mi(conn, owner_id, exam_id):
            raise ValueError("Sınav bulunamadı.")
        conn.execute("DELETE FROM exam_key_pages WHERE exam_id=?", (exam_id,))
        conn.executemany("INSERT INTO exam_key_pages(exam_id, page_no, image) VALUES (?, ?, ?)",
                         [(exam_id, i + 1, sqlite3.Binary(page)) for i, page in enumerate(page_images)])


def anahtar_sayfalarini_getir(owner_id, exam_id, db_path=None):
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT k.image FROM exam_key_pages k JOIN exams e ON e.id=k.exam_id
               WHERE k.exam_id=? AND e.owner_id=? ORDER BY k.page_no""", (exam_id, owner_id)).fetchall()
    return [bytes(row["image"]) for row in rows]


# ---------------------------------------------------------------- sonuçlar

def _sonuc_dict(row):
    return dict(row) | {"scores": json.loads(row["scores_json"]),
                        "warnings": json.loads(row["warnings_json"] or "[]")}


def sonuc_kaydet(owner_id, exam_id, student_id, student_name, scores, page_images=None,
                 approved=True, warnings=None, db_path=None):
    """Öğrenci sonucunu kaydet/güncelle.

    approved=False AI taslağıdır; istatistiklere girmez. page_images None ise
    daha önce kaydedilmiş sayfalar korunur.
    """
    student_id, student_name = _temiz(student_id), _temiz(student_name)
    if not student_id:
        raise ValueError("Sonuç kaydetmek için öğrenci numarası gereklidir.")
    for score in scores:
        maximum = float(score["maksimum_puan"])
        final = float(score.get("ogretmen_puani", score.get("verilen_puan", 0)))
        if not math.isfinite(final) or final < 0 or final > maximum + 1e-9:
            raise ValueError(f"{score.get('soru_no')}. sorunun puanı geçersiz.")
    with _connect(db_path) as conn:
        if not _sinav_sahibi_mi(conn, owner_id, exam_id):
            raise ValueError("Sınav bulunamadı.")
        conn.execute(
            """INSERT INTO results(exam_id, student_id, student_name, scores_json, warnings_json, approved, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(exam_id, student_id) DO UPDATE SET
                 student_name=excluded.student_name, scores_json=excluded.scores_json,
                 warnings_json=excluded.warnings_json, approved=excluded.approved, updated_at=excluded.updated_at""",
            (exam_id, student_id, student_name, json.dumps(scores, ensure_ascii=False),
             json.dumps(warnings or [], ensure_ascii=False), 1 if approved else 0, _simdi().isoformat()),
        )
        result_id = conn.execute("SELECT id FROM results WHERE exam_id=? AND student_id=?",
                                 (exam_id, student_id)).fetchone()["id"]
        if page_images is not None:
            conn.execute("DELETE FROM result_pages WHERE result_id=?", (result_id,))
            conn.executemany("INSERT INTO result_pages(result_id, page_no, image) VALUES (?, ?, ?)",
                             [(result_id, i + 1, sqlite3.Binary(page)) for i, page in enumerate(page_images)])
        return result_id


def sonuclari_getir(owner_id, exam_id=None, approved=True, sirala="ad", db_path=None):
    """Sonuçları getir. approved: True onaylı, False taslak, None hepsi. sirala: 'ad' | 'tarih'."""
    query = ("SELECT r.*, e.name AS exam_name, e.course, e.class_name, e.created_at AS exam_created_at "
             "FROM results r JOIN exams e ON e.id=r.exam_id WHERE e.owner_id=?")
    params = [owner_id]
    if approved is not None:
        query += " AND r.approved=?"
        params.append(1 if approved else 0)
    if exam_id is not None:
        query += " AND e.id=?"
        params.append(exam_id)
    query += " ORDER BY r.updated_at DESC" if sirala == "tarih" else " ORDER BY e.class_name, r.student_name, r.student_id"
    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_sonuc_dict(row) for row in rows]


def sonuc_getir(owner_id, result_id, db_path=None):
    with _connect(db_path) as conn:
        row = conn.execute(
            """SELECT r.*, e.name AS exam_name, e.course, e.class_name, e.created_at AS exam_created_at
               FROM results r JOIN exams e ON e.id=r.exam_id WHERE r.id=? AND e.owner_id=?""",
            (result_id, owner_id)).fetchone()
    return _sonuc_dict(row) if row else None


def sonuc_sil(owner_id, result_id, db_path=None):
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM result_pages WHERE result_id IN (SELECT r.id FROM results r JOIN exams e "
                     "ON e.id=r.exam_id WHERE r.id=? AND e.owner_id=?)", (result_id, owner_id))
        conn.execute("DELETE FROM results WHERE id=? AND exam_id IN (SELECT id FROM exams WHERE owner_id=?)",
                     (result_id, owner_id))


def sayfa_gorsellerini_getir(owner_id, result_id, db_path=None):
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT p.image FROM result_pages p JOIN results r ON r.id=p.result_id
               JOIN exams e ON e.id=r.exam_id WHERE p.result_id=? AND e.owner_id=? ORDER BY p.page_no""",
            (result_id, owner_id)).fetchall()
    return [bytes(row["image"]) for row in rows]


def soru_istatistikleri(owner_id, exam_ids, db_path=None):
    """Onaylı cevaplardan soru başına hata oranı, ortalama başarı ve AI/öğretmen puan uyumu."""
    if not exam_ids:
        return []
    placeholders = ",".join("?" for _ in exam_ids)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT r.scores_json, e.class_name FROM results r JOIN exams e ON e.id=r.exam_id
                WHERE r.approved=1 AND e.owner_id=? AND r.exam_id IN ({placeholders})""",
            [owner_id, *exam_ids]).fetchall()

    totals = {}
    for row in rows:
        for q in json.loads(row["scores_json"]):
            key = (row["class_name"], int(q["soru_no"]))
            item = totals.setdefault(key, {"sinif": key[0], "soru_no": key[1], "ogrenci_sayisi": 0, "hata_yapan": 0,
                                           "alinan": 0.0, "alinabilir": 0.0, "ai_karsilastirilan": 0, "ai_tam_uyum": 0})
            final = float(q.get("ogretmen_puani", q.get("verilen_puan", 0)))
            maximum = float(q["maksimum_puan"])
            item["ogrenci_sayisi"] += 1
            item["alinan"] += final
            item["alinabilir"] += maximum
            if final < maximum:
                item["hata_yapan"] += 1
            if q.get("ai_puani") is not None and q.get("ogretmen_puani") is not None:
                item["ai_karsilastirilan"] += 1
                if abs(float(q["ai_puani"]) - float(q["ogretmen_puani"])) < 0.001:
                    item["ai_tam_uyum"] += 1
    output = []
    for _, item in sorted(totals.items()):
        n, compared = item["ogrenci_sayisi"], item.pop("ai_karsilastirilan")
        exact = item.pop("ai_tam_uyum")
        earned, possible = item.pop("alinan"), item.pop("alinabilir")
        item["hata_yuzdesi"] = round(100 * item["hata_yapan"] / n, 1) if n else 0
        item["basari_yuzdesi"] = round(100 * earned / possible, 1) if possible else None
        item["ai_ogretmen_tam_uyum_yuzdesi"] = round(100 * exact / compared, 1) if compared else None
        output.append(item)
    return output


# ------------------------------------------------------------- AI kullanımı

def kullanim_kaydet(owner_id, islem, kullanim, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO usage_log(owner_id, created_at, islem, model, input_tokens, output_tokens, cost_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (owner_id, _simdi().isoformat(), islem, kullanim.get("model", ""), int(kullanim.get("input_tokens", 0)),
             int(kullanim.get("output_tokens", 0)), float(kullanim.get("maliyet_usd", 0))))


def kullanim_ozeti(owner_id, db_path=None):
    """Toplam ve son 30 günlük AI çağrı sayısı ile tahmini maliyet (USD)."""
    since = (_simdi() - timedelta(days=30)).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS cagri, COALESCE(SUM(cost_usd), 0) AS maliyet,
                      COALESCE(SUM(input_tokens), 0) AS girdi, COALESCE(SUM(output_tokens), 0) AS cikti,
                      COALESCE(SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END), 0) AS cagri_30,
                      COALESCE(SUM(CASE WHEN created_at >= ? THEN cost_usd ELSE 0 END), 0) AS maliyet_30,
                      COALESCE(SUM(CASE WHEN islem='kagit' THEN 1 ELSE 0 END), 0) AS kagit,
                      COALESCE(SUM(CASE WHEN islem='kagit' THEN cost_usd ELSE 0 END), 0) AS kagit_maliyet
               FROM usage_log WHERE owner_id=?""", (since, since, owner_id)).fetchone()
    return dict(row)
