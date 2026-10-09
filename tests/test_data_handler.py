import sqlite3

import pytest

import data_handler as dh


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(dh, "DB_PATH", path)
    dh.veritabani_hazirla()
    return path


@pytest.fixture
def ogretmen(db):
    assert dh.kullanici_olustur("ayse@okul.com", "Ayşe Öğretmen", "gizli-sifre")[0]
    return dh.kullanici_dogrula("ayse@okul.com", "gizli-sifre")[0]["id"]


@pytest.fixture
def diger(db):
    assert dh.kullanici_olustur("mehmet@okul.com", "Mehmet Öğretmen", "baska-sifre")[0]
    return dh.kullanici_dogrula("mehmet@okul.com", "baska-sifre")[0]["id"]


def _puanlar(*pairs):
    return [{"soru_no": i, "maksimum_puan": maximum, "verilen_puan": given, "ai_puani": given,
             "ogretmen_puani": given, "hatalar": []} for i, (given, maximum) in enumerate(pairs, start=1)]


def test_hesap_olusturma_ve_giris(db):
    assert dh.kullanici_olustur("a@b.com", "Ad Soyad", "12345678")[0]
    assert not dh.kullanici_olustur("A@B.com", "Başka", "12345678")[0], "aynı e-posta ikinci kez kaydedilemez"
    assert not dh.kullanici_olustur("gecersiz", "Ad", "12345678")[0]
    assert not dh.kullanici_olustur("c@d.com", "Ad", "kisa")[0]
    user, error = dh.kullanici_dogrula(" A@B.COM ", "12345678")
    assert user["email"] == "a@b.com" and error == ""
    assert dh.kullanici_dogrula("a@b.com", "yanlis-sifre")[0] is None


def test_hatali_giris_sinirlanir(db):
    dh.kullanici_olustur("a@b.com", "Ad Soyad", "12345678")
    for _ in range(dh.GIRIS_DENEME_SINIRI):
        assert dh.kullanici_dogrula("a@b.com", "yanlis")[0] is None
    user, error = dh.kullanici_dogrula("a@b.com", "12345678")
    assert user is None and "fazla" in error


def test_oturum_ve_sifre_degistirme(ogretmen):
    token = dh.oturum_olustur(ogretmen)
    assert dh.oturum_kullanicisi(token)["id"] == ogretmen
    assert dh.oturum_kullanicisi("uydurma") is None
    assert not dh.sifre_degistir(ogretmen, "yanlis", "yeni-sifre-1")[0]
    assert dh.sifre_degistir(ogretmen, "gizli-sifre", "yeni-sifre-1")[0]
    assert dh.oturum_kullanicisi(token) is None, "şifre değişince eski oturumlar kapanır"
    assert dh.kullanici_dogrula("ayse@okul.com", "yeni-sifre-1")[0]
    token = dh.oturum_olustur(ogretmen)
    dh.oturum_sil(token)
    assert dh.oturum_kullanicisi(token) is None


def test_bos_hucreler_ogrenci_olarak_kaydedilmez(ogretmen):
    count = dh.sinif_ogrenci_listesi_kaydet(ogretmen, "Matematik", "10-A", [
        {"student_id": "012", "name": "Ali Veli"},
        {"student_id": None, "name": "Numarasız"},
        {"student_id": float("nan"), "name": "NaN Numara"},
        {"student_id": "15", "name": None},
        {"student_id": 27.0, "name": " Ayşe Kaya "},
    ])
    assert count == 2
    assert dh.ogrencileri_getir(ogretmen, "Matematik", "10-A") == [
        {"student_id": "012", "name": "Ali Veli"}, {"student_id": "27", "name": "Ayşe Kaya"}]


def test_veriler_hesaplar_arasinda_ayridir(ogretmen, diger):
    exam_id = dh.sinav_ekle(ogretmen, "Ara Sınav", "Matematik", "10-A")
    result_id = dh.sonuc_kaydet(ogretmen, exam_id, "1", "Ali", _puanlar((5, 10)), [b"sayfa"])
    assert dh.siniflari_getir(diger) == [] and dh.sinavlari_getir(diger) == []
    assert dh.sinav_getir(diger, exam_id) is None
    assert dh.sonuclari_getir(diger) == [] and dh.sonuc_getir(diger, result_id) is None
    assert dh.sayfa_gorsellerini_getir(diger, result_id) == []
    assert dh.soru_istatistikleri(diger, [exam_id]) == []
    with pytest.raises(ValueError):
        dh.sonuc_kaydet(diger, exam_id, "2", "Sızma", _puanlar((1, 10)))
    dh.sinav_sil(diger, exam_id)
    dh.sonuc_sil(diger, result_id)
    assert dh.sinav_getir(ogretmen, exam_id) is not None
    assert dh.sayfa_gorsellerini_getir(ogretmen, result_id) == [b"sayfa"]
    # Aynı ders/sınıf adını iki öğretmen de kullanabilir.
    dh.sinif_ekle(diger, "Matematik", "10-A")
    assert len(dh.siniflari_getir(diger)) == 1


def test_taslak_onay_ve_sayfalarin_korunmasi(ogretmen):
    exam_id = dh.sinav_ekle(ogretmen, "Quiz", "Fizik", "9-B")
    result_id = dh.sonuc_kaydet(ogretmen, exam_id, "7", "Can", _puanlar((3, 10)), [b"s1", b"s2"],
                                approved=False, warnings=["düşük güven"])
    assert dh.sonuclari_getir(ogretmen) == []
    draft = dh.sonuclari_getir(ogretmen, approved=False)[0]
    assert draft["warnings"] == ["düşük güven"] and not draft["approved"]
    assert dh.soru_istatistikleri(ogretmen, [exam_id]) == [], "taslaklar istatistiğe girmez"

    same_id = dh.sonuc_kaydet(ogretmen, exam_id, "7", "Can", _puanlar((8, 10)))
    assert same_id == result_id
    assert dh.sayfa_gorsellerini_getir(ogretmen, result_id) == [b"s1", b"s2"], "sayfalar onayda korunur"
    assert dh.sonuclari_getir(ogretmen)[0]["scores"][0]["ogretmen_puani"] == 8

    with pytest.raises(ValueError):
        dh.sonuc_kaydet(ogretmen, exam_id, "8", "Ece", _puanlar((11, 10)))
    with pytest.raises(ValueError):
        dh.sonuc_kaydet(ogretmen, exam_id, " ", "Numarasız", _puanlar((1, 10)))


def test_soru_istatistikleri(ogretmen):
    exam_id = dh.sinav_ekle(ogretmen, "Final", "Kimya", "11-C")
    first = _puanlar((10, 10), (4, 20))
    second = _puanlar((5, 10), (20, 20))
    second[0]["ai_puani"] = 7  # öğretmen AI önerisini değiştirdi
    dh.sonuc_kaydet(ogretmen, exam_id, "1", "A", first)
    dh.sonuc_kaydet(ogretmen, exam_id, "2", "B", second)
    q1, q2 = dh.soru_istatistikleri(ogretmen, [exam_id])
    assert (q1["ogrenci_sayisi"], q1["hata_yapan"], q1["hata_yuzdesi"], q1["basari_yuzdesi"]) == (2, 1, 50.0, 75.0)
    assert q1["ai_ogretmen_tam_uyum_yuzdesi"] == 50.0
    assert (q2["hata_yuzdesi"], q2["basari_yuzdesi"], q2["ai_ogretmen_tam_uyum_yuzdesi"]) == (50.0, 60.0, 100.0)


def test_sablon_kaydi_temizlenir(ogretmen):
    exam_id = dh.sinav_ekle(ogretmen, "Quiz", "Fizik", "9-B")
    saved = dh.sinav_sorulari_kaydet(ogretmen, exam_id, [
        {"soru_no": 2.0, "soru_ozeti": "İkinci", "maksimum_puan": 60, "dogru_cevap": None},
        {"soru_no": 1, "soru_ozeti": "Birinci", "maksimum_puan": "40", "dogru_cevap": "x=5"},
        {"soru_no": 1, "soru_ozeti": "Tekrar", "maksimum_puan": 10},
        {"soru_no": None, "soru_ozeti": "Numarasız", "maksimum_puan": 10},
    ])
    assert [(q["soru_no"], q["maksimum_puan"], q["dogru_cevap"]) for q in saved] == [(1, 40.0, "x=5"), (2, 60.0, "")]
    assert dh.sinav_getir(ogretmen, exam_id)["questions"] == saved


def test_silme_islemleri(ogretmen):
    exam_id = dh.sinav_ekle(ogretmen, "Quiz", "Fizik", "9-B")
    other_exam = dh.sinav_ekle(ogretmen, "Quiz", "Fizik", "9-C")
    dh.ogrenci_ekle(ogretmen, "Fizik", "9-B", "1", "Ali")
    dh.anahtar_sayfalari_kaydet(ogretmen, exam_id, [b"anahtar"])
    result_id = dh.sonuc_kaydet(ogretmen, exam_id, "1", "Ali", _puanlar((5, 10)), [b"sayfa"])
    dh.sonuc_kaydet(ogretmen, other_exam, "1", "Veli", _puanlar((5, 10)), [b"sayfa"])

    dh.sinif_sil(ogretmen, "Fizik", "9-B")
    assert dh.sinav_getir(ogretmen, exam_id) is None and dh.sonuc_getir(ogretmen, result_id) is None
    assert dh.anahtar_sayfalarini_getir(ogretmen, exam_id) == []
    assert dh.ogrencileri_getir(ogretmen, "Fizik", "9-B") == []
    assert [c["class_name"] for c in dh.siniflari_getir(ogretmen)] == ["9-C"]

    dh.hesap_verilerini_sil(ogretmen)
    assert dh.siniflari_getir(ogretmen) == [] and dh.sinavlari_getir(ogretmen) == []
    with sqlite3.connect(dh.DB_PATH) as conn:
        for table in ("results", "result_pages", "exam_key_pages", "students"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


def test_eski_veritabani_yeni_semaya_tasinir(tmp_path, monkeypatch):
    path = str(tmp_path / "eski.db")
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL, password_salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE classes (id INTEGER PRIMARY KEY AUTOINCREMENT, course TEXT NOT NULL, class_name TEXT NOT NULL,
                UNIQUE(course, class_name));
            CREATE TABLE students (id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, student_id TEXT NOT NULL,
                name TEXT NOT NULL, UNIQUE(class_id, student_id));
            CREATE TABLE exams (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, course TEXT NOT NULL,
                class_name TEXT NOT NULL, exam_type TEXT NOT NULL DEFAULT 'Sınav', questions_json TEXT NOT NULL,
                created_at TEXT NOT NULL);
            CREATE TABLE results (id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER NOT NULL REFERENCES exams(id),
                student_id TEXT NOT NULL, student_name TEXT NOT NULL DEFAULT '', scores_json TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL, UNIQUE(exam_id, student_id));
            CREATE TABLE result_pages (result_id INTEGER NOT NULL REFERENCES results(id) ON DELETE CASCADE,
                page_no INTEGER NOT NULL, image BLOB NOT NULL, PRIMARY KEY(result_id, page_no));
            INSERT INTO users VALUES (1, 'eski@okul.com', 'Eski Hesap', '00', '00', '2026-01-01');
            INSERT INTO classes VALUES (1, 'Matematik', '10-A');
            INSERT INTO students VALUES (1, 1, '5', 'Ali');
            INSERT INTO exams VALUES (1, 'Ara', 'Matematik', '10-A', 'Quiz', '[]', '2026-01-02');
            INSERT INTO results VALUES (1, 1, '5', 'Ali', '[{"soru_no":1,"maksimum_puan":10,"verilen_puan":6}]', 1, '2026-01-03');
        """)
    monkeypatch.setattr(dh, "DB_PATH", path)
    dh.veritabani_hazirla()
    dh.veritabani_hazirla()  # ikinci çalıştırma zararsız olmalı
    assert dh.ogrencileri_getir(1, "Matematik", "10-A") == [{"student_id": "5", "name": "Ali"}]
    assert dh.sinavlari_getir(1)[0]["total_points"] == 100
    assert dh.sonuclari_getir(1)[0]["warnings"] == []
    dh.sinav_sil(1, 1)
    assert dh.sonuclari_getir(1) == []
