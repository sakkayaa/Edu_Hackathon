"""Claude tabanlı sınav kâğıdı, cevap anahtarı ve sınıf listesi okuma.

Bütün işlevler önceden hazırlanmış JPEG sayfa baytları alır (bkz. gorsel.py)
ve (sonuç sözlüğü, kullanım sözlüğü) döndürür.
"""

import base64
import json
import os

import anthropic
from dotenv import load_dotenv

from gorsel import sayfa_boyutu

load_dotenv()

VARSAYILAN_MODEL = "claude-haiku-4-5"
# 1 milyon token başına USD (girdi, çıktı); tahmini maliyet gösterimi için.
FIYATLAR = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}
MAKS_CIKTI = 16000


class AIHatasi(RuntimeError):
    """Kullanıcıya gösterilebilir AI hatası."""


def model_adi():
    return os.getenv("CLAUDE_MODEL", "").strip() or VARSAYILAN_MODEL


def api_anahtari_var_mi():
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def _istemci():
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise AIHatasi("ANTHROPIC_API_KEY bulunamadı. Claude API anahtarını .env dosyasına ekleyip uygulamayı yeniden başlatın.")
    # SDK 429 ve 5xx hatalarını artan beklemeyle kendiliğinden yeniden dener.
    return anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=180.0)


def _gorsel_blogu(image_bytes):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(image_bytes).decode("ascii")}}


def _sayfa_bloklari(pages, baslik):
    """Her sayfayı numarası ve piksel boyutuyla birlikte içerik bloklarına çevir."""
    blocks = []
    for number, page in enumerate(pages, start=1):
        width, height = sayfa_boyutu(page)
        blocks.append({"type": "text", "text": f"{baslik} — sayfa {number} ({width}x{height} piksel):"})
        blocks.append(_gorsel_blogu(page))
    return blocks


def _kullanim(response, model):
    usage = response.usage
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    input_price, output_price = FIYATLAR.get(model, FIYATLAR[VARSAYILAN_MODEL])
    cost = (usage.input_tokens * input_price + cache_write * input_price * 1.25
            + cache_read * input_price * 0.1 + usage.output_tokens * output_price) / 1_000_000
    return {"model": model, "input_tokens": usage.input_tokens + cache_write + cache_read,
            "output_tokens": usage.output_tokens, "maliyet_usd": round(cost, 6)}


def _json_iste(system, content, schema):
    """Claude'dan şemaya uygun JSON iste; (veri, kullanım) döndür."""
    model = model_adi()
    output_config = {"format": {"type": "json_schema", "schema": schema}}
    if not model.startswith("claude-haiku"):
        # Haiku dışındaki modellerde düşünme açıktır; maliyeti effort belirler.
        output_config["effort"] = os.getenv("CLAUDE_EFFORT", "").strip() or "low"
    try:
        response = _istemci().messages.create(
            model=model, max_tokens=MAKS_CIKTI, system=system,
            messages=[{"role": "user", "content": content}], output_config=output_config,
        )
    except anthropic.AuthenticationError as exc:
        raise AIHatasi("Claude API anahtarı geçersiz. .env dosyasındaki ANTHROPIC_API_KEY değerini kontrol edin.") from exc
    except anthropic.PermissionDeniedError as exc:
        raise AIHatasi(f"API anahtarınızın '{model}' modeline erişim izni yok.") from exc
    except anthropic.NotFoundError as exc:
        raise AIHatasi(f"'{model}' modeli bulunamadı. .env dosyasındaki CLAUDE_MODEL değerini kontrol edin.") from exc
    except anthropic.RateLimitError as exc:
        raise AIHatasi("Claude istek sınırına ulaşıldı. Bir dakika bekleyip yeniden deneyin.") from exc
    except anthropic.BadRequestError as exc:
        if "credit balance" in str(exc).lower():
            raise AIHatasi("Claude hesabınızda kredi kalmadı. console.anthropic.com üzerinden kredi yükleyin.") from exc
        raise AIHatasi(f"AI isteği reddedildi: {exc.message}") from exc
    except anthropic.APIStatusError as exc:
        if exc.status_code >= 500:
            raise AIHatasi("Claude hizmeti şu anda yoğun. Biraz bekleyip yeniden deneyin; yüklediğiniz sayfalar korunuyor.") from exc
        raise AIHatasi(f"AI isteği başarısız oldu (HTTP {exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise AIHatasi("Claude hizmetine ulaşılamadı. İnternet bağlantınızı kontrol edip yeniden deneyin.") from exc

    if response.stop_reason == "refusal":
        raise AIHatasi("AI bu içeriği değerlendirmeyi reddetti. Sayfaları kontrol edin.")
    if response.stop_reason == "max_tokens":
        raise AIHatasi("AI yanıtı çok uzun olduğu için yarıda kesildi. Kâğıdı daha az sayfayla yeniden deneyin.")
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIHatasi("AI yanıtı geçerli JSON biçiminde değil. Yeniden deneyin.") from exc
    if not isinstance(data, dict):
        raise AIHatasi("AI yanıtı beklenen biçimde değil. Yeniden deneyin.")
    return data, _kullanim(response, model)


# ------------------------------------------------------------ kâğıt okuma

# Alan sırası bilinçlidir: model önce cevabı okuyup gerekçesini yazar, puanı sonra verir.
_SONUC_SEMASI = {
    "type": "object",
    "properties": {
        "sorular": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "soru_no": {"type": "integer"},
                    "soru_ozeti": {"type": "string"},
                    "ogrenci_cevabi": {"type": "string"},
                    "dogru_cevap": {"type": "string"},
                    "gerekce": {"type": "string"},
                    "hatalar": {"type": "array", "items": {"type": "string"}},
                    "maksimum_puan": {"type": "number"},
                    "verilen_puan": {"type": "number"},
                    "anahtar_kontrolu": {"type": "string"},
                    "guven": {"type": "number"},
                    "isaretlemeler": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sayfa_no": {"type": "integer"},
                                "x1": {"type": "number"}, "y1": {"type": "number"},
                                "x2": {"type": "number"}, "y2": {"type": "number"},
                                "etiket": {"type": "string"},
                            },
                            "required": ["sayfa_no", "x1", "y1", "x2", "y2", "etiket"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["soru_no", "soru_ozeti", "ogrenci_cevabi", "dogru_cevap", "gerekce", "hatalar",
                             "maksimum_puan", "verilen_puan", "anahtar_kontrolu", "guven", "isaretlemeler"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sorular"],
    "additionalProperties": False,
}

_KAGIT_SISTEM = """Sen öğretmene yardımcı olan bir sınav değerlendirme asistanısın. Öğrencinin sınav \
kâğıdı sayfalarını okur, her soruyu ayrı ayrı değerlendirir ve öğretmene puan önerirsin. Nihai puanı \
öğretmen onaylar; görevin dürüst, kanıta dayalı ve tutarlı bir ön değerlendirme yapmaktır.

Her soru için sırayla:
1. soru_ozeti: Soruyu kâğıttan oku ve kısaca özetle.
2. ogrenci_cevabi: Öğrencinin yazdığını (işlem adımlarıyla) olduğu gibi aktar. Yazmadığı bir şeyi \
ekleme; okunmayan yerleri "[okunamadı]" diye belirt. Soru boş bırakıldıysa "Boş" yaz.
3. dogru_cevap: Soruyu kendin bağımsız çöz ve doğru cevabı kısaca yaz.
4. gerekce: Öğrencinin cevabını kendi çözümünle (ve verilmişse şablondaki doğru cevapla) adım adım \
karşılaştır; nerede doğru, nerede yanlış olduğunu bir iki cümleyle söyle.
5. hatalar: Hataları kısa, genel etiketlerle listele (ör. "işlem hatası", "işaret hatası", "eksik \
çözüm", "kavram yanılgısı", "birim hatası", "boş"). Hata yoksa boş liste ver.
6. maksimum_puan ve verilen_puan: Kısmi doğruları dikkate alarak, aşağıdaki ölçeğe göre tutarlı puanla \
(soruda veya şablonda ayrı bir puanlama ölçütü yazıyorsa o geçerlidir):
   - Yöntem ve sonuç doğru: tam puan. Yalnızca birim/gösterim eksiği varsa puanın yaklaşık %90'ı.
   - Yöntem doğru, tek bir işlem ya da işaret hatası yüzünden sonuç yanlış: puanın yaklaşık yarısı.
   - Doğru bir başlangıç var ama çözüm yarım veya birden fazla hata var: puanın yaklaşık dörtte biri.
   - Yöntem tamamen yanlış, ilgisiz veya soru boş: 0.
   Aynı hatayı yapan iki öğrenci aynı puanı almalı; yalnızca sonuç yanlış diye sıfır verme.
7. anahtar_kontrolu: Şablondaki doğru cevap senin çözümünle çelişiyorsa bunu açıkça yaz; çelişki \
yoksa boş metin ver. Şablonu otomatik olarak doğru kabul etme.
8. guven: 0 ile 1 arasında. El yazısı okunaksızsa, soru belirsizse veya puanlama yoruma açıksa düşür.
9. isaretlemeler: Bu sorunun sayfada kapladığı alanı (soru metni ve öğrencinin çözümünün tamamı, ilk \
satırından son satırına kadar) tek bir dikdörtgen olarak ver. Koordinatlar o sayfanın pikselleridir: \
sol üst köşe (0,0), x sağa, y aşağı doğru artar; x1,y1 sol üst, x2,y2 sağ alt köşedir. Soru birden \
fazla sayfaya yayılıyorsa sayfa başına bir dikdörtgen ver. etiket "Soru N" olsun. Emin değilsen boş liste ver.

Sayfalar yükleme sırasına göre numaralıdır. Yanıtın yalnızca istenen JSON olsun; metinler Türkçe olsun."""


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
