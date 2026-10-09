"""AI grading validation and teacher-approved class analytics."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from math import isfinite
from typing import Any, Mapping, Sequence


class VeriDogrulamaHatasi(ValueError):
    """Raised when rubric, AI output, or reviewed results are invalid."""


def _records(value: Any, label: str = "Soru listesi") -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        value = value.get("sorular")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise VeriDogrulamaHatasi(f"{label} boş veya geçersiz.")
    if any(not isinstance(item, Mapping) for item in value):
        raise VeriDogrulamaHatasi(f"{label} içindeki kayıtlar nesne olmalı.")
    return list(value)


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise VeriDogrulamaHatasi(f"{label} sonlu bir sayı olmalı.")
    return float(value)


def ai_yanitini_dogrula(
    ai_yaniti: Mapping[str, Any],
    sorular_ve_rubrik: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    guven_esigi: float = 0.70,
) -> dict[str, Any]:
    """Validate ``ai_core.kagit_oku`` output against the exam rubric."""
    threshold = _number(guven_esigi, "Güven eşiği")
    if not 0 <= threshold <= 1:
        raise VeriDogrulamaHatasi("Güven eşiği 0 ile 1 arasında olmalı.")

    rubric_records = _records(sorular_ve_rubrik, "Rubrik")
    ai_records = _records(ai_yaniti, "AI yanıtı")
    rubric: dict[int, Mapping[str, Any]] = {}
    for index, question in enumerate(rubric_records, start=1):
        number = question.get("soru_no")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise VeriDogrulamaHatasi(f"Rubrikteki {index}. soru numarası geçersiz.")
        if number in rubric:
            raise VeriDogrulamaHatasi(f"Rubrikte {number}. soru tekrarlanıyor.")
        maximum = _number(question.get("maksimum_puan"), f"{number}. soru maksimum puanı")
        if maximum <= 0 or not question.get("rubrik"):
            raise VeriDogrulamaHatasi(f"{number}. sorunun maksimum puanı veya rubriği eksik.")
        rubric[number] = question

    received: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(ai_records, start=1):
        number = item.get("soru_no")
        if isinstance(number, bool) or not isinstance(number, int):
            raise VeriDogrulamaHatasi(f"AI yanıtındaki {index}. soru numarası geçersiz.")
        if number not in rubric:
            raise VeriDogrulamaHatasi(f"AI yanıtında rubrikte olmayan {number}. soru var.")
        if number in received:
            raise VeriDogrulamaHatasi(f"AI yanıtında {number}. soru tekrarlanıyor.")

        maximum = _number(rubric[number]["maksimum_puan"], f"{number}. soru maksimum puanı")
        if _number(item.get("maksimum_puan"), f"{number}. AI maksimum puanı") != maximum:
            raise VeriDogrulamaHatasi(f"{number}. sorunun maksimum puanı rubrikle uyuşmuyor.")
        score = _number(item.get("verilen_puan"), f"{number}. soru puanı")
        if not 0 <= score <= maximum:
            raise VeriDogrulamaHatasi(f"{number}. soru puanı 0 ile {maximum:g} arasında olmalı.")
        confidence = _number(item.get("guven"), f"{number}. soru güven değeri")
        if not 0 <= confidence <= 1:
            raise VeriDogrulamaHatasi(f"{number}. soru güven değeri 0 ile 1 arasında olmalı.")
        mistakes = item.get("hatalar")
        reason = item.get("gerekce")
        if not isinstance(mistakes, list) or any(not isinstance(error, str) for error in mistakes):
            raise VeriDogrulamaHatasi(f"{number}. sorunun hataları metin listesi olmalı.")
        if not isinstance(reason, str) or not reason.strip():
            raise VeriDogrulamaHatasi(f"{number}. sorunun gerekçesi boş olamaz.")

        received[number] = {
            "soru_no": number,
            "maksimum_puan": rubric[number]["maksimum_puan"],
            "verilen_puan": item["verilen_puan"],
            "hatalar": list(mistakes),
            "gerekce": reason.strip(),
            "guven": confidence,
            "ogretmen_kontrolu_gerekli": (
                confidence < threshold or item.get("ogretmen_kontrolu_gerekli") is True
            ),
        }

    missing = [number for number in rubric if number not in received]
    if missing:
        raise VeriDogrulamaHatasi("AI yanıtında eksik sorular var: " + ", ".join(map(str, missing)))
    return {"sorular": [received[number] for number in rubric]}


def ogretmen_duzenle(
    ai_sonucu: Mapping[str, Any],
    duzenlemeler: Mapping[int, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create an unapproved review record, preserving AI and teacher scores separately."""
    if not isinstance(ai_sonucu, Mapping):
        raise VeriDogrulamaHatasi("AI sonucu nesne biçiminde olmalı.")
    edits = duzenlemeler or {}
    if not isinstance(edits, Mapping):
        raise VeriDogrulamaHatasi("Düzenlemeler soru numarasına göre nesne olmalı.")

    reviewed = []
    seen: set[int] = set()
    for item in _records(ai_sonucu, "AI sonucu"):
        number = item.get("soru_no")
        if isinstance(number, bool) or not isinstance(number, int) or number in seen:
            raise VeriDogrulamaHatasi("AI sonucundaki soru numarası geçersiz veya tekrarlı.")
        seen.add(number)
        maximum = _number(item.get("maksimum_puan"), f"{number}. soru maksimum puanı")
        ai_score = _number(item.get("verilen_puan"), f"{number}. AI puanı")
        edit = edits.get(number, {})
        if not isinstance(edit, Mapping):
            raise VeriDogrulamaHatasi(f"{number}. soru düzenlemesi geçersiz.")
        teacher_score = _number(edit.get("ogretmen_puani", ai_score), f"{number}. öğretmen puanı")
        if maximum <= 0 or not 0 <= ai_score <= maximum or not 0 <= teacher_score <= maximum:
            raise VeriDogrulamaHatasi(f"{number}. soru puanı maksimum puan sınırları dışında.")
        mistakes = edit.get("hatalar", item.get("hatalar", []))
        reason = edit.get("gerekce", item.get("gerekce", ""))
        if not isinstance(mistakes, list) or any(not isinstance(error, str) for error in mistakes):
            raise VeriDogrulamaHatasi(f"{number}. sorunun hataları metin listesi olmalı.")
        if not isinstance(reason, str) or not reason.strip():
            raise VeriDogrulamaHatasi(f"{number}. sorunun gerekçesi boş olamaz.")
        reviewed.append({
            "soru_no": number,
            "maksimum_puan": item["maksimum_puan"],
            "ai_puani": item["verilen_puan"],
            "ogretmen_puani": teacher_score,
            "hatalar": list(mistakes),
            "gerekce": reason.strip(),
            "guven": item.get("guven"),
            "ogretmen_kontrolu_gerekli": item.get("ogretmen_kontrolu_gerekli", False),
        })
    return {"ogretmen_onayli": False, "sorular": reviewed}


def ogretmen_onayla(duzenlenmis_sonuc: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and mark teacher-reviewed results as approved."""
    if not isinstance(duzenlenmis_sonuc, Mapping):
        raise VeriDogrulamaHatasi("Onaylanacak değerlendirme geçersiz.")
    result = deepcopy(dict(duzenlenmis_sonuc))
    for question in _records(result, "Onaylanacak değerlendirme"):
        number = question.get("soru_no")
        maximum = _number(question.get("maksimum_puan"), f"{number}. soru maksimum puanı")
        score = _number(question.get("ogretmen_puani"), f"{number}. öğretmen puanı")
        if maximum <= 0 or not 0 <= score <= maximum:
            raise VeriDogrulamaHatasi(f"{number}. sorunun öğretmen puanı geçersiz.")
        if not isinstance(question.get("hatalar"), list) or not isinstance(question.get("gerekce"), str):
            raise VeriDogrulamaHatasi(f"{number}. sorunun öğretmen kontrolü tamamlanmamış.")
    result["ogretmen_onayli"] = True
    return result


def sinif_sonuclarini_dogrula(
    sonuclar: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return a deep-copied class result collection with valid approval states."""
    if not isinstance(sonuclar, Sequence) or isinstance(sonuclar, (str, bytes)):
        raise VeriDogrulamaHatasi("Sınıf sonuçları liste biçiminde olmalı.")
    normalized = []
    for index, result in enumerate(sonuclar, start=1):
        if not isinstance(result, Mapping) or not isinstance(result.get("ogretmen_onayli"), bool):
            raise VeriDogrulamaHatasi(f"{index}. öğrenci sonucunda onay durumu bulunamadı.")
        item = deepcopy(dict(result))
        _records(item, f"{index}. öğrenci sonucu")
        normalized.append(item)
    return normalized


def sinif_hata_analizi(
    sonuclar: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute question error counts/percentages from approved results only.

    A question is counted as an error when the teacher-approved ``hatalar``
    list is non-empty. Unapproved AI suggestions and teacher edits are skipped.
    """
    if not isinstance(sonuclar, Sequence) or isinstance(sonuclar, (str, bytes)):
        raise VeriDogrulamaHatasi("Sınıf sonuçları liste biçiminde olmalı.")
    totals: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"maksimum_puan": None, "ogrenci_sayisi": 0, "hata_sayisi": 0, "puan_toplami": 0.0}
    )
    approved_count = 0
    for index, result in enumerate(sonuclar, start=1):
        if not isinstance(result, Mapping):
            raise VeriDogrulamaHatasi(f"{index}. öğrenci sonucu geçersiz.")
        if result.get("ogretmen_onayli") is not True:
            continue
        approved_count += 1
        seen: set[int] = set()
        for question in _records(result, f"{index}. onaylı sonuç"):
            number = question.get("soru_no")
            if isinstance(number, bool) or not isinstance(number, int) or number < 1 or number in seen:
                raise VeriDogrulamaHatasi("Onaylı sonuçtaki soru numarası geçersiz veya tekrarlı.")
            seen.add(number)
            maximum = _number(question.get("maksimum_puan"), f"{number}. soru maksimum puanı")
            score = _number(question.get("ogretmen_puani"), f"{number}. öğretmen puanı")
            mistakes = question.get("hatalar")
            if maximum <= 0 or not 0 <= score <= maximum:
                raise VeriDogrulamaHatasi(f"Onaylı {number}. soru puanı geçersiz.")
            if not isinstance(mistakes, list) or any(not isinstance(error, str) for error in mistakes):
                raise VeriDogrulamaHatasi(f"Onaylı {number}. sorunun hataları geçersiz.")
            total = totals[number]
            if total["maksimum_puan"] is not None and total["maksimum_puan"] != maximum:
                raise VeriDogrulamaHatasi(f"{number}. sorunun maksimum puanı sonuçlarda farklı.")
            total["maksimum_puan"] = maximum
            total["ogrenci_sayisi"] += 1
            total["puan_toplami"] += score
            if mistakes:
                total["hata_sayisi"] += 1

    question_results = []
    for number, total in sorted(totals.items()):
        count = total["ogrenci_sayisi"]
        errors = total["hata_sayisi"]
        question_results.append({
            "soru_no": number,
            "onayli_ogrenci_sayisi": count,
            "hata_yapan_ogrenci_sayisi": errors,
            "hata_yuzdesi": round(errors / count * 100, 2) if count else 0.0,
            "maksimum_puan": total["maksimum_puan"],
            "ortalama_puan": round(total["puan_toplami"] / count, 2) if count else 0.0,
        })
    return {"onayli_ogrenci_sayisi": approved_count, "sorular": question_results}

