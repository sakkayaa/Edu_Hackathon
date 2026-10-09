"""AI değerlendirme sonucunu doğrulama ve puan yardımcıları."""

import json
import math


DUSUK_GUVEN = 0.6


def _sayi(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def son_puan(question):
    """Öğretmen puanı varsa onu, yoksa AI önerisini döndür."""
    return float(question.get("ogretmen_puani", question.get("verilen_puan", 0)) or 0)


def puan_ozeti(scores):
    """(alınan, maksimum) toplamlarını döndür."""
    return (sum(son_puan(q) for q in scores), sum(float(q.get("maksimum_puan", 0) or 0) for q in scores))


def yuzde(scores):
    earned, maximum = puan_ozeti(scores)
    return 100 * earned / maximum if maximum else None


def sablon_olustur(scores):
    """Onaylanmış bir kâğıttan sınavın soru şablonunu türet."""
    return [{"soru_no": int(q["soru_no"]), "soru_ozeti": str(q.get("soru_ozeti", "")),
             "maksimum_puan": float(q["maksimum_puan"]), "dogru_cevap": str(q.get("dogru_cevap", ""))}
            for q in scores]


def _isaretler(raw_marks, qno, sayfa_boyutlari):
    """Piksel koordinatlı AI işaretlerini sayfa ölçüsüne oranlı 0-1 değerlere çevir."""
    marks = []
    for mark in raw_marks if isinstance(raw_marks, list) else []:
        try:
            page = int(mark["sayfa_no"])
            if page < 1 or page > len(sayfa_boyutlari):
                continue
            width, height = sayfa_boyutlari[page - 1]
            coords = [float(mark[key]) for key in ("x1", "y1", "x2", "y2")]
            if not all(math.isfinite(v) for v in coords) or width <= 0 or height <= 0:
                continue
            x1, x2 = sorted((min(max(coords[0] / width, 0.0), 1.0), min(max(coords[2] / width, 0.0), 1.0)))
            y1, y2 = sorted((min(max(coords[1] / height, 0.0), 1.0), min(max(coords[3] / height, 0.0), 1.0)))
            if x2 - x1 < 0.005 or y2 - y1 < 0.005:
                continue
            marks.append({"sayfa_no": page, "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                          "etiket": str(mark.get("etiket") or f"Soru {qno}")})
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return marks


def ai_sonucu_kontrol(ham_sonuc, soru_tanimlari, sayfa_boyutlari, toplam_puan=None):
    """AI sonucunu sınav şablonuna göre düzenle; puanları ve sayfa işaretlerini doğrula.

    soru_tanimlari doluysa soru numaraları ve maksimum puanlar şablondan alınır;
    boşsa AI'nin kâğıttan okuduğu yapı kullanılır.
    {"gecerli": bool, "sorular": [...], "uyarilar": [...]} döndürür.
    """
    try:
        veri = json.loads(ham_sonuc) if isinstance(ham_sonuc, str) else ham_sonuc
        ai_sorular = veri["sorular"]
        if not isinstance(ai_sorular, list):
            raise ValueError("'sorular' alanı liste olmalı.")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return {"gecerli": False, "sorular": [], "uyarilar": [f"AI yanıtı okunamadı: {exc}"]}

    warnings = []
    by_number = {}
    for item in ai_sorular:
        number = _sayi(item.get("soru_no")) if isinstance(item, dict) else None
        if number is None:
            warnings.append("Soru numarası okunamayan bir AI sonucu yok sayıldı.")
            continue
        by_number.setdefault(int(number), item)

    definitions = {int(d["soru_no"]): d for d in (soru_tanimlari or [])}
    if definitions:
        question_specs = [(qno, float(d["maksimum_puan"])) for qno, d in sorted(definitions.items())]
        extra = sorted(set(by_number) - set(definitions))
        if extra:
            warnings.append("AI şablonda olmayan soru(lar) buldu ve yok sayıldı: " + ", ".join(map(str, extra)))
    else:
        question_specs = []
        for qno, item in sorted(by_number.items()):
            maximum = _sayi(item.get("maksimum_puan"), 0)
            if maximum <= 0:
                warnings.append(f"{qno}. soru için AI geçerli maksimum puan vermedi; öğretmen kontrol etmeli.")
                maximum = 0
            question_specs.append((qno, maximum))
        if not question_specs:
            return {"gecerli": False, "sorular": [], "uyarilar": ["AI soruları kâğıttan okuyamadı."]}

    normalized = []
    for qno, maximum in question_specs:
        definition = definitions.get(qno, {})
        item = by_number.get(qno)
        if item is None:
            warnings.append(f"{qno}. soru AI tarafından değerlendirilmedi; öğretmen puanlamalı.")
            normalized.append({
                "soru_no": qno, "soru_ozeti": str(definition.get("soru_ozeti", "")), "ogrenci_cevabi": "",
                "dogru_cevap": str(definition.get("dogru_cevap", "")), "maksimum_puan": maximum, "verilen_puan": 0.0,
                "hatalar": ["değerlendirilmedi"], "gerekce": "AI bu soruya sonuç vermedi; öğretmen puanı belirlemeli.",
                "anahtar_kontrolu": "", "guven": 0.0, "isaretlemeler": [],
            })
            continue

        score = _sayi(item.get("verilen_puan"))
        if score is None:
            score = 0.0
            warnings.append(f"{qno}. sorunun AI puanı okunamadı; 0 öneri olarak gösterildi.")
        if score < 0 or score > maximum:
            warnings.append(f"{qno}. sorunun AI puanı sınır dışındaydı ve 0–{maximum:g} aralığına çekildi.")
            score = min(max(score, 0.0), maximum)

        confidence = _sayi(item.get("guven"), 0.0)
        if confidence > 1 and confidence <= 100:
            confidence /= 100  # model yüzde olarak verdiyse
        confidence = min(max(confidence, 0.0), 1.0)
        if confidence < DUSUK_GUVEN:
            warnings.append(f"{qno}. soru düşük AI güvenine sahip; öğretmen kontrol etmeli.")

        errors = item.get("hatalar", [])
        if not isinstance(errors, list):
            errors = []
        errors = [str(error).strip() for error in errors if str(error).strip()]

        normalized.append({
            "soru_no": qno,
            "soru_ozeti": str(item.get("soru_ozeti") or definition.get("soru_ozeti", "")),
            "ogrenci_cevabi": str(item.get("ogrenci_cevabi", "")),
            "dogru_cevap": str(item.get("dogru_cevap") or definition.get("dogru_cevap", "")),
            "maksimum_puan": maximum, "verilen_puan": score, "hatalar": errors,
            "gerekce": str(item.get("gerekce", "")), "anahtar_kontrolu": str(item.get("anahtar_kontrolu", "")),
            "guven": confidence, "isaretlemeler": _isaretler(item.get("isaretlemeler"), qno, sayfa_boyutlari),
        })

    if toplam_puan is not None and not definitions:
        total = sum(q["maksimum_puan"] for q in normalized)
        target = float(toplam_puan)
        if total > target + 0.001:
            warnings.append("AI'nin soru puanları sınav toplamını aşıyordu; soru maksimumları orantılı olarak düzeltildi.")
            for q in normalized:
                q["maksimum_puan"] = round(q["maksimum_puan"] * target / total, 2)
                q["verilen_puan"] = min(q["verilen_puan"], q["maksimum_puan"])
        elif total < target - 0.001:
            warnings.append(f"Soru puanlarının toplamı ({total:g}) sınav toplamından ({target:g}) düşük; "
                            "soru maksimumlarını kontrol edin.")
    return {"gecerli": True, "sorular": normalized, "uyarilar": warnings}
