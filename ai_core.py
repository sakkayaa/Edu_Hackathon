"""Gemini tabanlı sınav ve öğrenci listesi görsel işlemleri."""

import json
import logging
import os
import re
from io import BytesIO
from typing import Any

from dotenv import load_dotenv
from google import genai
from PIL import Image, UnidentifiedImageError

load_dotenv()

logger = logging.getLogger(__name__)


def _api_hata_kodu(exc):
    """Google GenAI hata nesnelerinden HTTP durum kodunu çıkar."""
    for attribute in ("status_code", "code"):
        value = getattr(exc, attribute, None)
        try:
            if value is not None and 100 <= int(value) <= 599:
                return int(value)
        except (TypeError, ValueError):
            pass
    match = re.search(r"\b(429|500|502|503|504)\b", str(exc))
    return int(match.group(1)) if match else None


def _model_istegi(client, model, contents, config):
    """Önce ana modeli kullan; geçici sunucu yoğunluğunda yedek modeli dene."""
    try:
        return client.models.generate_content(model=model, contents=contents, config=config)
    except Exception as primary_error:
        status = _api_hata_kodu(primary_error)
        fallback = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.7-flash").strip()
        if status not in (500, 502, 503, 504) or not fallback or fallback == model:
            raise

        logger.warning("Gemini %s geçici olarak kullanılamıyor (HTTP %s); %s deneniyor.",
                       model, status, fallback)
        try:
            return client.models.generate_content(model=fallback, contents=contents, config=config)
        except Exception as fallback_error:
            fallback_status = _api_hata_kodu(fallback_error)
            logger.warning("Gemini yedek modeli %s de HTTP %s ile yanıt veremedi.",
                           fallback, fallback_status or "bilinmiyor")
            if fallback_status in (500, 502, 503, 504):
                raise RuntimeError(
                    f"Gemini modelleri şu anda yanıt veremedi: ana model {model} HTTP {status}, "
                    f"yedek model {fallback} HTTP {fallback_status}. Bu sunucu zaman aşımı/yoğunluk "
                    "hatasıdır; API anahtarı hatasında genellikle 401/403 görülür. Biraz bekleyip "
                    "yeniden deneyin; yüklediğiniz sayfalar korunuyor."
                ) from fallback_error
            raise RuntimeError(
                "Yedek AI modeli yanıt veremedi. GEMINI_FALLBACK_MODEL ayarını ve model erişiminizi kontrol edin."
            ) from fallback_error

SONUC_SEMASI = {
    "type": "OBJECT",
    "properties": {
        "sorular": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "soru_no": {"type": "INTEGER"},
                    "soru_ozeti": {"type": "STRING"},
                    "maksimum_puan": {"type": "NUMBER"},
                    "verilen_puan": {"type": "NUMBER"},
                    "hatalar": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "gerekce": {"type": "STRING"},
                    "anahtar_kontrolu": {"type": "STRING"},
                    "guven": {"type": "NUMBER"},
                    "isaretlemeler": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "sayfa_no": {"type": "INTEGER"},
                                "x1": {"type": "NUMBER"},
                                "y1": {"type": "NUMBER"},
                                "x2": {"type": "NUMBER"},
                                "y2": {"type": "NUMBER"},
                                "etiket": {"type": "STRING"},
                            },
                            "required": ["sayfa_no", "x1", "y1", "x2", "y2", "etiket"],
                        },
                    },
                },
                "required": [
                    "soru_no", "soru_ozeti", "maksimum_puan", "verilen_puan",
                    "hatalar", "gerekce", "anahtar_kontrolu", "guven", "isaretlemeler",
                ],
            },
        }
    },
    "required": ["sorular"],
}


def _gorselleri_ac(kaynaklar):
    if kaynaklar is None:
        return []
    sources = kaynaklar if isinstance(kaynaklar, (list, tuple)) else [kaynaklar]
    images = []
    try:
        for source in sources:
            if isinstance(source, Image.Image):
                images.append(source.copy())
            elif isinstance(source, (bytes, bytearray)):
                image = Image.open(BytesIO(source))
                image.load()
                images.append(image)
            else:
                image = Image.open(source)
                image.load()
                images.append(image)
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        for image in images:
            image.close()
        raise ValueError("Görsel açılamadı; geçerli resim dosyası seçin.") from exc
    return images


def kagit_oku(resim_yolu: Any, sorular_ve_rubrik=None, cevap_anahtari=None, max_puan=100) -> str:
    """Öğrenci kâğıdını soru soru okur; cevap anahtarı varsa karşılaştırır.

    Soru metinleri görselden okunur; önceden web formuna girilmeleri gerekmez.
    Öğrenci kâğıdı ve cevap anahtarı tek görsel ya da sayfa listesi olabilir.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY bulunamadı. API anahtarını .env dosyasına ekleyin.")
    if not resim_yolu:
        raise ValueError("En az bir öğrenci sınav sayfası yükleyin.")

    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    student_images = _gorselleri_ac(resim_yolu)
    key_images = _gorselleri_ac(cevap_anahtari)
    rubric = json.dumps(sorular_ve_rubrik or [], ensure_ascii=False, indent=2)
    prompt = f"""
Sen öğretmene yardımcı olan bir sınav değerlendirme asistanısın. Soruları ve
öğrenci cevaplarını öğrenci kâğıdı görsellerinden kendin oku; öğretmenin soru
metinlerini web sayfasına yazması gerekmez. Birden fazla öğrenci sayfası varsa
yükleme sırasına göre numaralandır.

TOPLAM MAKSİMUM PUAN: {max_puan}
ÖĞRETMENİN EK ÖLÇÜTLERİ (varsa): {rubric}

Her soruyu önce bağımsız biçimde kendin çöz ve öğrenci cevabını değerlendir.
Sonra cevap anahtarı görselleri verilmişse bunları ikinci kontrol kaynağı olarak
kullan. Anahtar hatalı görünüyorsa bunu anahtar_kontrolu alanında yaz; anahtarı
otomatik olarak doğru kabul etme. Anahtar ve öğrenci sayfaları farklı görsel
gruplarıdır. İşaretleme koordinatları yalnızca öğrenci sayfalarına göredir.

Kurallar:
- Her soruyu numaralandır ve kısa soru_ozeti yaz.
- Sayfada soru başına puan ağırlığı belirtilmişse onu kullan. Belirtilmemişse
  toplam maksimum puanı sorular arasında makul dağıt; maksimum_puan değerlerinin
  toplamı {max_puan} puanı geçmesin.
- İşlem adımlarını ve kısmi doğru cevapları dikkate al; öğrenci cevabını uydurma.
- Okunmayan veya belirsiz cevaplarda gerekçede bunu söyle ve guven değerini düşür.
- Hatalar alanında kısa etiketler kullan; hata yoksa boş liste ver.
- Her soru için kanıta dayalı kısa gerekçe, varsa anahtarla farkı ve 0-1 güven ver.
- isaretlemeler, yalnızca öğrenci kâğıdındaki cevap bölgesini yaklaşık gösterir.
  x1,y1,x2,y2 koordinatları sayfa ölçüsüne oranlı 0-1 aralığındadır; emin değilsen boş liste ver.
- Bu bir öğretmen önerisidir; nihai puanı öğretmen onaylar.
- Yalnızca tanımlı JSON şemasında yanıt ver.
"""

    contents = []
    if key_images:
        contents.extend(["CEVAP ANAHTARI SAYFALARI:", *key_images])
    contents.extend(["ÖĞRENCİ SINAV KÂĞIDI SAYFALARI:", *student_images, prompt])
    try:
        client = genai.Client(api_key=api_key)
        response = _model_istegi(
            client, model, contents,
            {"response_mime_type": "application/json", "response_schema": SONUC_SEMASI},
        )
    except RuntimeError:
        raise
    except Exception as exc:
        status = _api_hata_kodu(exc)
        if status in (500, 502, 503, 504):
            raise RuntimeError(
                "Gemini hizmeti şu anda yoğun veya geçici olarak erişilemiyor. Biraz bekleyip yeniden deneyin."
            ) from exc
        raise RuntimeError(f"AI değerlendirmesi alınamadı: {exc}") from exc
    finally:
        for image in student_images + key_images:
            image.close()

    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("AI boş yanıt verdi. Sayfaları ve anahtarı kontrol edip tekrar deneyin.")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI yanıtı geçerli JSON biçiminde değil.") from exc
    if not isinstance(result, dict) or not isinstance(result.get("sorular"), list):
        raise RuntimeError("AI yanıtında beklenen 'sorular' listesi bulunamadı.")
    return json.dumps(result, ensure_ascii=False)


def ogrenci_listesi_oku(resim_yolu: Any) -> str:
    """Sınıf listesi görselinden öğrenci numarası ve adlarını JSON olarak çıkar."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY bulunamadı. API anahtarını .env dosyasına ekleyin.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    image_list = _gorselleri_ac(resim_yolu)
    if not image_list:
        raise ValueError("Bir sınıf listesi fotoğrafı yükleyin.")
    image = image_list[0]
    schema = {
        "type": "OBJECT",
        "properties": {
            "ogrenciler": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {"student_id": {"type": "STRING"}, "name": {"type": "STRING"}, "guven": {"type": "NUMBER"}},
                    "required": ["student_id", "name", "guven"],
                },
            }
        },
        "required": ["ogrenciler"],
    }
    prompt = """Bu görseldeki sınıf listesini oku. Her satırdan öğrenci numarası ve tam adı çıkar.
Yalnızca açıkça okunabilen bilgileri yaz; okunmayan bilgiyi tahmin etme.
Numarayı baştaki sıfırları koruyarak metin olarak döndür. 0-1 arası güven ver.
Yalnızca istenen JSON biçiminde yanıt ver."""
    try:
        client = genai.Client(api_key=api_key)
        response = _model_istegi(client, model, [image, prompt],
            {"response_mime_type": "application/json", "response_schema": schema})
    except RuntimeError:
        raise
    except Exception as exc:
        status = _api_hata_kodu(exc)
        if status in (500, 502, 503, 504):
            raise RuntimeError(
                "Gemini hizmeti şu anda yoğun veya geçici olarak erişilemiyor. Biraz bekleyip yeniden deneyin."
            ) from exc
        raise RuntimeError(f"Sınıf listesi okunamadı: {exc}") from exc
    finally:
        for page in image_list:
            page.close()
    if not getattr(response, "text", None):
        raise RuntimeError("AI sınıf listesi için boş yanıt verdi.")
    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI'nin sınıf listesi yanıtı geçerli JSON değil.") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("ogrenciler"), list):
        raise RuntimeError("AI yanıtında öğrenci listesi bulunamadı.")
    return json.dumps(parsed, ensure_ascii=False)
