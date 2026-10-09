"""Exam image grading suggestions backed by the OpenAI Responses API.

The model's output follows the shared project contract::

    {"sorular": [{"soru_no": 1, "maksimum_puan": 20,
                  "verilen_puan": 15, "hatalar": [],
                  "gerekce": "...", "guven": 0.82}]}

``ogretmen_kontrolu_gerekli`` is added locally for low-confidence answers;
it is never trusted to the model. All returned points are suggestions and
must be reviewed by a teacher before they are used as final grades.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence


class KagitOkumaHatasi(ValueError):
    """Raised when an exam image cannot be read or graded safely."""


_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sorular": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "soru_no": {"type": "integer"},
                    "maksimum_puan": {"type": "number"},
                    "verilen_puan": {"type": "number"},
                    "hatalar": {"type": "array", "items": {"type": "string"}},
                    "gerekce": {"type": "string"},
                    "guven": {"type": "number"},
                },
                "required": [
                    "soru_no",
                    "maksimum_puan",
                    "verilen_puan",
                    "hatalar",
                    "gerekce",
                    "guven",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sorular"],
    "additionalProperties": False,
}

_ANSWER_KEY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sorular": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "soru_no": {"type": "integer"},
                    "cevap": {"type": "string"},
                    "kabul_edilebilir_cevaplar": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "cozum_yolu": {"type": "string"},
                },
                "required": [
                    "soru_no",
                    "cevap",
                    "kabul_edilebilir_cevaplar",
                    "cozum_yolu",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sorular"],
    "additionalProperties": False,
}


def _read_image(image: Any) -> tuple[bytes, str]:
    """Read bytes from a path, bytes-like object, or uploaded file object."""
    name = getattr(image, "name", None)

    if isinstance(image, (str, os.PathLike, Path)):
        path = Path(image)
        name = path.name
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise KagitOkumaHatasi(f"Sınav görseli okunamadı: {path}") from exc
    elif isinstance(image, (bytes, bytearray, memoryview)):
        content = bytes(image)
    elif hasattr(image, "read"):
        try:
            if hasattr(image, "seek"):
                image.seek(0)
            content = image.read()
        except (OSError, ValueError) as exc:
            raise KagitOkumaHatasi("Yüklenen sınav görseli okunamadı.") from exc
    else:
        raise KagitOkumaHatasi(
            "Görsel; dosya yolu, bytes veya read() destekleyen yüklenmiş dosya olmalı."
        )

    if not isinstance(content, bytes):
        try:
            content = bytes(content)
        except (TypeError, ValueError) as exc:
            raise KagitOkumaHatasi("Yüklenen dosyanın içeriği okunamadı.") from exc
    if not content:
        raise KagitOkumaHatasi("Sınav görseli boş.")
    if len(content) > 20 * 1024 * 1024:
        raise KagitOkumaHatasi("Sınav görseli 20 MB sınırını aşıyor.")

    # Detect the actual format first; extension and browser-provided MIME can
    # be incorrect. OpenAI image input accepts PNG/JPEG for this integration.
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    else:
        guessed, _ = mimetypes.guess_type(str(name or ""))
        if guessed not in {"image/png", "image/jpeg"}:
            raise KagitOkumaHatasi(
                "Desteklenmeyen görsel biçimi. Lütfen PNG veya JPEG yükleyin."
            )
        # Reject a filename-only MIME guess if the file doesn't look like an
        # image; this catches renamed PDFs and other unsupported documents.
        raise KagitOkumaHatasi(
            "Dosya içeriği PNG/JPEG olarak doğrulanamadı. Görseli yeniden dışa aktarın."
        )
    return content, mime


def _normalize_rubric(value: Any) -> list[dict[str, Any]]:
    """Accept a list of question records or {"sorular": [...]} and validate it."""
    if isinstance(value, Mapping):
        value = value.get("sorular")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise KagitOkumaHatasi(
            "Soru-rubrik bilgisi boş. En az bir soru için soru_no, maksimum_puan ve rubrik girin."
        )

    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, question in enumerate(value, start=1):
        if not isinstance(question, Mapping):
            raise KagitOkumaHatasi(f"{index}. soru bilgisi bir nesne olmalı.")
        number = question.get("soru_no")
        maximum = question.get("maksimum_puan")
        rubric = question.get("rubrik")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise KagitOkumaHatasi(f"{index}. soru için geçerli bir soru_no girin.")
        if number in seen:
            raise KagitOkumaHatasi(f"{number}. soru birden fazla kez tanımlanmış.")
        if isinstance(maximum, bool) or not isinstance(maximum, (int, float)) or maximum <= 0:
            raise KagitOkumaHatasi(f"{number}. soru için maksimum_puan sıfırdan büyük olmalı.")
        if rubric is None or rubric == "" or rubric == [] or rubric == {}:
            raise KagitOkumaHatasi(f"{number}. sorunun rubriği boş.")
        seen.add(number)
        normalized.append(
            {"soru_no": number, "maksimum_puan": maximum, "rubrik": rubric}
        )
    return normalized


def _parse_and_validate(
    raw_text: str,
    questions: list[dict[str, Any]],
    confidence_threshold: float,
) -> dict[str, Any]:
    try:
        payload = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise KagitOkumaHatasi("AI yanıtı geçerli JSON biçiminde değil.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("sorular"), list):
        raise KagitOkumaHatasi("AI yanıtında 'sorular' listesi bulunamadı.")
    if not payload["sorular"]:
        raise KagitOkumaHatasi(
            "Görselde okunabilir bir sınav sorusu bulunamadı. Daha net bir PNG/JPEG yükleyin."
        )

    expected = {item["soru_no"]: item for item in questions}
    received: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(payload["sorular"], start=1):
        if not isinstance(item, dict):
            raise KagitOkumaHatasi(f"AI yanıtındaki {index}. soru geçersiz.")
        number = item.get("soru_no")
        if isinstance(number, bool) or not isinstance(number, int):
            raise KagitOkumaHatasi(f"AI yanıtındaki {index}. soru numarası geçersiz.")
        if number not in expected:
            raise KagitOkumaHatasi(f"AI yanıtında rubrikte olmayan {number}. soru var.")
        if number in received:
            raise KagitOkumaHatasi(f"AI yanıtında {number}. soru tekrarlanıyor.")

        rubric_question = expected[number]
        maximum = rubric_question["maksimum_puan"]
        model_maximum = item.get("maksimum_puan")
        score = item.get("verilen_puan")
        confidence = item.get("guven")
        for field_name, value in (("maksimum_puan", model_maximum), ("verilen_puan", score)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise KagitOkumaHatasi(f"{number}. sorunun {field_name} alanı sayısal değil.")
        if model_maximum != maximum:
            raise KagitOkumaHatasi(
                f"{number}. sorunun maksimum_puan değeri rubrikle uyuşmuyor ({maximum})."
            )
        if score < 0 or score > maximum:
            raise KagitOkumaHatasi(
                f"{number}. soruya verilen puan 0 ile {maximum} arasında olmalı."
            )
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise KagitOkumaHatasi(f"{number}. sorunun güven değeri 0 ile 1 arasında olmalı.")
        mistakes = item.get("hatalar")
        reason = item.get("gerekce")
        if not isinstance(mistakes, list) or any(not isinstance(error, str) for error in mistakes):
            raise KagitOkumaHatasi(f"{number}. sorunun hatalar alanı metin listesi olmalı.")
        if not isinstance(reason, str) or not reason.strip():
            raise KagitOkumaHatasi(f"{number}. sorunun kısa gerekçesi eksik.")

        received[number] = {
            "soru_no": number,
            "maksimum_puan": maximum,
            "verilen_puan": score,
            "hatalar": mistakes,
            "gerekce": reason.strip(),
            "guven": confidence,
            "ogretmen_kontrolu_gerekli": confidence < confidence_threshold,
        }

    missing = [number for number in expected if number not in received]
    if missing:
        missing_text = ", ".join(str(number) for number in missing)
        raise KagitOkumaHatasi(f"AI yanıtında {missing_text}. soru(lar) eksik.")

    return {"sorular": [received[item["soru_no"]] for item in questions]}


def _validate_answer_key(
    answer_key: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate a reusable answer key created once for an exam."""
    key_questions = answer_key.get("sorular") if isinstance(answer_key, Mapping) else answer_key
    if not isinstance(key_questions, Sequence) or isinstance(key_questions, (str, bytes)):
        raise KagitOkumaHatasi(
            "Cevap anahtarı geçersiz. Önce cevap_anahtari_oku() ile anahtarı oluşturun."
        )

    expected = {question["soru_no"] for question in questions}
    received: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(key_questions, start=1):
        if not isinstance(item, Mapping):
            raise KagitOkumaHatasi(f"Cevap anahtarındaki {index}. soru geçersiz.")
        number = item.get("soru_no")
        if isinstance(number, bool) or not isinstance(number, int) or number not in expected:
            raise KagitOkumaHatasi(f"Cevap anahtarındaki {index}. soru numarası rubrikle eşleşmiyor.")
        if number in received:
            raise KagitOkumaHatasi(f"Cevap anahtarında {number}. soru tekrarlanıyor.")
        answer = item.get("cevap")
        alternatives = item.get("kabul_edilebilir_cevaplar", [])
        solution = item.get("cozum_yolu", "")
        if not isinstance(answer, str) or not answer.strip():
            raise KagitOkumaHatasi(f"Cevap anahtarında {number}. sorunun cevabı eksik.")
        if not isinstance(alternatives, list) or any(not isinstance(value, str) for value in alternatives):
            raise KagitOkumaHatasi(f"{number}. sorunun kabul edilebilir cevapları metin listesi olmalı.")
        if not isinstance(solution, str):
            raise KagitOkumaHatasi(f"{number}. sorunun çözüm yolu metin olmalı.")
        received[number] = {
            "soru_no": number,
            "cevap": answer.strip(),
            "kabul_edilebilir_cevaplar": alternatives,
            "cozum_yolu": solution.strip(),
        }

    missing = expected - received.keys()
    if missing:
        missing_text = ", ".join(str(number) for number in sorted(missing))
        raise KagitOkumaHatasi(f"Cevap anahtarında {missing_text}. soru(lar) eksik.")
    return {"sorular": [received[q["soru_no"]] for q in questions]}


def _request_json_from_image(
    image_bytes: bytes,
    mime_type: str,
    instructions: str,
    prompt: str,
    schema: dict[str, Any],
    schema_name: str,
    model: str | None,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise KagitOkumaHatasi(
            "OPENAI_API_KEY tanımlı değil. API anahtarını ortam değişkeni olarak ayarlayın."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise KagitOkumaHatasi(
            "OpenAI Python paketi kurulu değil. 'pip install -r requirements.txt' çalıştırın."
        ) from exc

    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    try:
        response = OpenAI(api_key=api_key).responses.create(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            instructions=instructions,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{encoded_image}",
                        "detail": "high",
                    },
                ],
            }],
            text={"format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }},
        )
    except Exception as exc:
        raise KagitOkumaHatasi(
            "AI isteği tamamlanamadı. API bağlantısını ve model ayarını kontrol edip yeniden deneyin."
        ) from exc
    result = getattr(response, "output_text", None)
    if not isinstance(result, str) or not result.strip():
        raise KagitOkumaHatasi("AI okunabilir bir yanıt döndürmedi. Daha net bir görsel yükleyin.")
    return result


def cevap_anahtari_oku(
    resim: Any,
    sorular_ve_rubrik: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Read the teacher's answer sheet once and create a reusable answer key.

    Call once per exam, then store the returned JSON in app/session state and
    reuse it for every student's paper. The teacher's answer-sheet image is
    not sent again during student-paper grading.
    """
    image_bytes, mime_type = _read_image(resim)
    questions = _normalize_rubric(sorular_ve_rubrik)
    rubric_json = json.dumps(questions, ensure_ascii=False, indent=2)
    raw_text = _request_json_from_image(
        image_bytes,
        mime_type,
        "Bu görsel öğretmenin cevap anahtarıdır. Öğrenci kâğıdı gibi puanlama; "
        "her sorunun beklenen cevabını, kabul edilebilir alternatifleri ve çözüm yolunu çıkar. "
        "Cevabı okunamayan soruda tahmin etme.",
        "Rubrikte belirtilen sorular için cevap anahtarını çıkar. Soru numaralarını aynen kullan.\n"
        f"Rubrik:\n{rubric_json}",
        _ANSWER_KEY_SCHEMA,
        "sinav_cevap_anahtari",
        model,
    )
    try:
        payload = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise KagitOkumaHatasi("AI cevap anahtarını geçerli JSON olarak döndürmedi.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("sorular"), list):
        raise KagitOkumaHatasi("AI yanıtında cevap anahtarının 'sorular' listesi bulunamadı.")
    if any(not isinstance(item, Mapping) or not str(item.get("cevap", "")).strip() for item in payload["sorular"]):
        raise KagitOkumaHatasi(
            "Cevap kâğıdındaki bir veya daha fazla yanıt okunamadı. Daha net görsel yükleyin."
        )
    return _validate_answer_key(payload, questions)


def kagit_oku(
    resim: Any,
    sorular_ve_rubrik: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    cevap_anahtari: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    confidence_threshold: float = 0.70,
    model: str | None = None,
) -> dict[str, Any]:
    """Compare one student's exam image with the exam's reusable answer key.

    Args:
        resim: Student paper as PNG/JPEG path, bytes, or uploaded file object.
        sorular_ve_rubrik: Question records containing ``soru_no``,
            ``maksimum_puan`` and ``rubrik``.
        cevap_anahtari: Result of ``cevap_anahtari_oku``. Create it once per
            exam and reuse the returned JSON for each student's paper.
        confidence_threshold: Answers below this confidence are flagged for
            teacher review in ``ogretmen_kontrolu_gerekli``.
        model: Optional model override. Defaults to ``OPENAI_MODEL`` or
            ``gpt-4.1-mini``.

    Raises:
        KagitOkumaHatasi: For invalid images, rubric/key data, model output,
            missing credentials, or API failures.

    Note:
        Scores are suggestions, not approved grades. The teacher must review
        them before results are finalized.
    """
    if (
        isinstance(confidence_threshold, bool)
        or not isinstance(confidence_threshold, (int, float))
        or not 0 <= confidence_threshold <= 1
    ):
        raise KagitOkumaHatasi("Güven eşiği 0 ile 1 arasında olmalı.")

    image_bytes, mime_type = _read_image(resim)
    questions = _normalize_rubric(sorular_ve_rubrik)
    answer_key = _validate_answer_key(cevap_anahtari, questions)
    rubric_json = json.dumps(questions, ensure_ascii=False, indent=2)
    answer_key_json = json.dumps(answer_key, ensure_ascii=False, indent=2)

    instructions = (
        "Sen dikkatli bir öğretmen yardımcısısın. Öğrenci kâğıdını öğretmenin "
        "cevap anahtarı ve verilen rubriğe göre karşılaştırarak değerlendir. "
        "Yalnızca rubrikteki soruları döndür; soru numaralarını ve maksimum "
        "puanları aynen kullan. Eşdeğer doğru ifadeleri kabul et. Her soru için "
        "verilen puanı, gözlenen hata türlerini, kısa gerekçeyi ve 0 ile 1 arasında "
        "güven değerini ver. Yazı okunmuyorsa tahmin etme, güveni düşük tut ve "
        "gerekçede okunamayan kısmı belirt. Sonuç öğretmen önerisidir; kesin karar verme."
    )
    prompt = (
        "Rubrik:\n"
        f"{rubric_json}\n\n"
        "Öğretmenin cevap anahtarı:\n"
        f"{answer_key_json}\n\n"
        "Öğrenci kâğıdını cevap anahtarıyla soru soru karşılaştırıp rubriğe göre "
        "puan önerisi üret."
    )
    output_text = _request_json_from_image(
        image_bytes,
        mime_type,
        instructions,
        prompt,
        _OUTPUT_SCHEMA,
        "sinav_degerlendirmesi",
        model,
    )
    return _parse_and_validate(output_text, questions, float(confidence_threshold))
