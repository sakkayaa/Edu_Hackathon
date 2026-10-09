from data_handler import veri_kontrol_fonksiyonu

ornekler = {
    "normal": '{"puan": 80, "hatalar": ["işlem hatası"], "gerekce": "2. adımda toplama yanlış", "guven": 0.9}',
    "negatif puan": '{"puan": -5, "hatalar": []}',
    "üst sınır aşıldı": '{"puan": 150, "hatalar": []}',
    "bozuk json": "bu hiç json değil",
    "markdown içinde": '```json\n{"puan": 70, "hatalar": []}\n```',
    "düşük güven": '{"puan": 50, "hatalar": [], "guven": 0.3}',
    "puan eksik": '{"hatalar": ["x"]}',
}

for ad, metin in ornekler.items():
    print(f"--- {ad} ---")
    print(veri_kontrol_fonksiyonu(metin, max_puan=100))
    print()