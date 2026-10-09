from io import BytesIO

import pytest
from PIL import Image

from degerlendirme import ai_sonucu_kontrol, puan_ozeti, sablon_olustur, yuzde
from gorsel import MAKS_KENAR, dosyalari_sayfalara_cevir, sayfa_boyutu, sayfayi_isaretle

SAYFA = [(1000, 2000)]


def _soru(no, verilen, maksimum, **extra):
    return {"soru_no": no, "soru_ozeti": f"Soru {no}", "ogrenci_cevabi": "x=5", "dogru_cevap": "x=5",
            "gerekce": "ok", "hatalar": [], "maksimum_puan": maksimum, "verilen_puan": verilen,
            "anahtar_kontrolu": "", "guven": 0.9, "isaretlemeler": [], **extra}


def test_bozuk_yanit_gecersiz_sayilir():
    assert not ai_sonucu_kontrol("json değil", [], SAYFA)["gecerli"]
    assert not ai_sonucu_kontrol({"sorular": "liste değil"}, [], SAYFA)["gecerli"]
    assert not ai_sonucu_kontrol({"sorular": []}, [], SAYFA)["gecerli"]


def test_sablonsuz_kagit_ai_yapisini_kullanir():
    result = ai_sonucu_kontrol({"sorular": [_soru(2, 30, 60), _soru(1, 40, 40)]}, [], SAYFA, toplam_puan=100)
    assert result["gecerli"] and result["uyarilar"] == []
    assert [(q["soru_no"], q["maksimum_puan"], q["verilen_puan"]) for q in result["sorular"]] == [(1, 40, 40), (2, 60, 30)]


def test_sablon_soru_yapisini_ve_puanlari_belirler():
    template = [{"soru_no": 1, "maksimum_puan": 25, "soru_ozeti": "Denklem", "dogru_cevap": "x=5"},
                {"soru_no": 2, "maksimum_puan": 75, "soru_ozeti": "Problem", "dogru_cevap": "12"}]
    raw = {"sorular": [_soru(1, 40, 50), _soru(3, 5, 10)]}
    result = ai_sonucu_kontrol(raw, template, SAYFA, toplam_puan=100)
    q1, q2 = result["sorular"]
    assert (q1["maksimum_puan"], q1["verilen_puan"]) == (25, 25), "puan şablondaki maksimuma çekilir"
    assert (q2["verilen_puan"], q2["hatalar"], q2["dogru_cevap"]) == (0.0, ["değerlendirilmedi"], "12")
    text = " ".join(result["uyarilar"])
    assert "sınır dışı" in text and "değerlendirilmedi" in text and "şablonda olmayan" in text


def test_toplami_asan_puanlar_orantilanir():
    result = ai_sonucu_kontrol({"sorular": [_soru(1, 100, 100), _soru(2, 50, 100)]}, [], SAYFA, toplam_puan=100)
    assert [(q["maksimum_puan"], q["verilen_puan"]) for q in result["sorular"]] == [(50, 50), (50, 50)]
    low = ai_sonucu_kontrol({"sorular": [_soru(1, 10, 40)]}, [], SAYFA, toplam_puan=100)
    assert any("düşük" in w for w in low["uyarilar"])


def test_guven_ve_bozuk_alanlar():
    raw = {"sorular": [_soru(1, "abc", 10, guven=0.3, hatalar="liste değil"), _soru(2, 5, 10, guven=85)]}
    q1, q2 = ai_sonucu_kontrol(raw, [], SAYFA)["sorular"]
    assert q1["verilen_puan"] == 0 and q1["hatalar"] == [] and q1["guven"] == 0.3
    assert q2["guven"] == 0.85, "yüzde olarak verilen güven 0-1 aralığına çevrilir"


def test_isaretler_pikselden_orana_cevrilir():
    marks = [
        {"sayfa_no": 1, "x1": 100, "y1": 500, "x2": 600, "y2": 1000, "etiket": "S1"},
        {"sayfa_no": 1, "x1": 900, "y1": 100, "x2": 1500, "y2": 300, "etiket": ""},   # sayfadan taşıyor
        {"sayfa_no": 2, "x1": 0, "y1": 0, "x2": 10, "y2": 10, "etiket": "yok"},      # olmayan sayfa
        {"sayfa_no": 1, "x1": 5, "y1": 5, "x2": 5, "y2": 5, "etiket": "nokta"},       # alanı yok
        {"sayfa_no": 1, "x1": "x", "y1": 0, "x2": 1, "y2": 1},                         # bozuk
    ]
    q = ai_sonucu_kontrol({"sorular": [_soru(1, 5, 10, isaretlemeler=marks)]}, [], SAYFA)["sorular"][0]
    assert q["isaretlemeler"] == [
        {"sayfa_no": 1, "x1": 0.1, "y1": 0.25, "x2": 0.6, "y2": 0.5, "etiket": "S1"},
        {"sayfa_no": 1, "x1": 0.9, "y1": 0.05, "x2": 1.0, "y2": 0.15, "etiket": "Soru 1"},
    ]


def test_puan_yardimcilari():
    scores = [{"soru_no": 1, "maksimum_puan": 40, "verilen_puan": 10, "ogretmen_puani": 30},
              {"soru_no": 2, "maksimum_puan": 60, "verilen_puan": 60, "soru_ozeti": "S", "dogru_cevap": "C"}]
    assert puan_ozeti(scores) == (90, 100) and yuzde(scores) == 90
    assert yuzde([]) is None
    assert sablon_olustur(scores)[1] == {"soru_no": 2, "soru_ozeti": "S", "maksimum_puan": 60.0, "dogru_cevap": "C"}


def _png(size, color="white"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_gorseller_kucultulur_ve_jpeg_olur():
    pages = dosyalari_sayfalara_cevir([("a.png", _png((4000, 3000))), ("b.png", _png((300, 200)))])
    assert sayfa_boyutu(pages[0]) == (MAKS_KENAR, MAKS_KENAR * 3 // 4)
    assert sayfa_boyutu(pages[1]) == (300, 200)
    assert all(page[:2] == b"\xff\xd8" for page in pages)


def test_pdf_sayfalarina_ayrilir():
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    for _ in range(3):
        document.new_page(width=595, height=842)
    pages = dosyalari_sayfalara_cevir([("sinav.pdf", document.tobytes())])
    assert len(pages) == 3 and max(sayfa_boyutu(pages[0])) == MAKS_KENAR


def test_gecersiz_dosyalar_reddedilir():
    with pytest.raises(ValueError):
        dosyalari_sayfalara_cevir([("bozuk.png", b"resim degil")])
    with pytest.raises(ValueError):
        dosyalari_sayfalara_cevir([])


def test_isaretleme_kutuyu_cizer():
    page = dosyalari_sayfalara_cevir([("a.png", _png((400, 400)))])[0]
    question = {"soru_no": 1, "maksimum_puan": 10, "ogretmen_puani": 2, "hatalar": ["işlem hatası"],
                "isaretlemeler": [{"sayfa_no": 1, "x1": 0.25, "y1": 0.25, "x2": 0.75, "y2": 0.75, "etiket": "S1"}]}
    marked = sayfayi_isaretle(page, [question], 1)
    r, g, b = marked.getpixel((100, 200))
    assert r > 150 and g < 120, "puan kırılan cevap kırmızı kutuyla işaretlenir"
    assert sayfayi_isaretle(page, [question], 2).getpixel((100, 200)) == (255, 255, 255)


def test_dosya_adindan_ogrenci_eslesir():
    from views.degerlendir import _dosyadan_ogrenci
    roster = [{"student_id": "101", "name": "Ayşe Kaya"}, {"student_id": "103", "name": "Zeynep Çelik"},
              {"student_id": "7", "name": "Işıl İnce"}]
    assert _dosyadan_ogrenci("101_ayse.png", roster)["student_id"] == "101"
    assert _dosyadan_ogrenci("zeynep celik.pdf", roster)["student_id"] == "103"
    assert _dosyadan_ogrenci("ISIL-INCE-sinav.jpg", roster)["student_id"] == "7"
    assert _dosyadan_ogrenci("IMG_0042.png", roster) is None
    assert _dosyadan_ogrenci("1017.png", roster) is None, "numara parçası eşleşme sayılmaz"
