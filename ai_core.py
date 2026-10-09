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



def kagit_oku(sayfalar, sorular=None, max_puan=100):
    """Öğrenci kâğıdını soru soru değerlendir.

    sorular: sınavın kayıtlı soru şablonu (soru_no, soru_ozeti, maksimum_puan,
    dogru_cevap). Boşsa soru yapısı ve puan dağılımı kâğıttan okunur.
    """
    if not sayfalar:
        raise ValueError("En az bir öğrenci sınav sayfası yükleyin.")
    if sorular:
        template = json.dumps(sorular, ensure_ascii=False, sort_keys=True)
        rules = (
            "SINAVIN SORU ŞABLONU (öğretmen tarafından onaylandı):\n" + template + "\n\n"
            "Tam olarak bu soru numaralarını değerlendir ve maksimum_puan değerlerini şablondan aynen al. "
            "Öğrenci bir soruyu hiç cevaplamadıysa o soruya 0 ver ve hatalar listesine \"boş\" yaz."
        )
    else:
        rules = (
            f"Bu sınav için kayıtlı soru şablonu yok. Soruları kâğıttan oku. SINAVIN TOPLAM PUANI: {max_puan:g}. "
            "Kâğıtta soru başına puan yazıyorsa onu kullan; yazmıyorsa toplam puanı sorulara zorluklarına göre "
            f"dağıt. maksimum_puan değerlerinin toplamı tam olarak {max_puan:g} olsun."
        )
    # Şablon öğrenciden öğrenciye değişmez; önbellek noktası sınav boyunca tekrar kullanılır.
    content = [{"type": "text", "text": rules, "cache_control": {"type": "ephemeral"}}]
    content += _sayfa_bloklari(sayfalar, "ÖĞRENCİ KÂĞIDI")
    content.append({"type": "text", "text": "Yukarıdaki öğrenci kâğıdını soru soru değerlendir."})
    data, usage = _json_iste(_KAGIT_SISTEM, content, _SONUC_SEMASI)
    if not isinstance(data.get("sorular"), list):
        raise AIHatasi("AI yanıtında beklenen 'sorular' listesi bulunamadı.")
    return data, usage


# -------------------------------------------------------- soru şablonu

_SABLON_SEMASI = {
    "type": "object",
    "properties": {
        "sorular": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "soru_no": {"type": "integer"},
                    "soru_ozeti": {"type": "string"},
                    "dogru_cevap": {"type": "string"},
                    "maksimum_puan": {"type": "number"},
                },
                "required": ["soru_no", "soru_ozeti", "dogru_cevap", "maksimum_puan"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sorular"],
    "additionalProperties": False,
}

_SABLON_SISTEM = """Sen bir sınavın soru şablonunu çıkaran asistansın. Sana bir sınavın cevap anahtarı \
veya boş soru kâğıdı verilir. Her soru için soru numarasını, sorunun kısa özetini, doğru cevabı \
(çözümün kilit adımlarıyla, kısa) ve maksimum puanı çıkar. Her soruyu önce kendin çöz. Sayfada cevap \
yazmıyorsa kendi çözümünü yaz. Sayfadaki cevap senin çözümünle çelişiyorsa doğru_cevap alanına kendi \
çözümünü yaz ve başına "[Anahtardaki cevap farklı: ...; kontrol edin]" notunu ekle. Sayfada soru puanı yazıyorsa onu kullan; yazmıyorsa toplam puanı sorulara zorluklarına göre dağıt. \
Yanıtın yalnızca istenen JSON olsun; metinler Türkçe olsun."""


def sablon_cikar(sayfalar, max_puan=100):
    """Cevap anahtarı veya boş soru kâğıdından sınavın soru şablonunu çıkar."""
    if not sayfalar:
        raise ValueError("En az bir cevap anahtarı sayfası yükleyin.")
    content = _sayfa_bloklari(sayfalar, "CEVAP ANAHTARI / SORU KÂĞIDI")
    content.append({"type": "text", "text": f"SINAVIN TOPLAM PUANI: {max_puan:g}. maksimum_puan değerlerinin "
                                            f"toplamı tam olarak {max_puan:g} olsun. Soru şablonunu çıkar."})
    data, usage = _json_iste(_SABLON_SISTEM, content, _SABLON_SEMASI)
    if not isinstance(data.get("sorular"), list) or not data["sorular"]:
        raise AIHatasi("AI bu sayfalardan soru çıkaramadı. Daha net bir görsel deneyin.")
    return data, usage


# -------------------------------------------------------- sınıf listesi

_LISTE_SEMASI = {
    "type": "object",
    "properties": {
        "ogrenciler": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"student_id": {"type": "string"}, "name": {"type": "string"},
                               "guven": {"type": "number"}},
                "required": ["student_id", "name", "guven"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ogrenciler"],
    "additionalProperties": False,
}

_LISTE_SISTEM = """Sana bir sınıf listesinin fotoğrafı verilir. Her satırdan öğrenci numarasını ve tam \
adını çıkar. Yalnızca açıkça okunabilen bilgileri yaz; okunmayan bilgiyi tahmin etme. Numarayı baştaki \
sıfırları koruyarak metin olarak döndür. Her satır için 0-1 arası güven ver. Yanıtın yalnızca istenen JSON olsun."""


def ogrenci_listesi_oku(sayfalar):
    """Sınıf listesi görsel(ler)inden öğrenci numarası ve adlarını çıkar."""
    if not sayfalar:
        raise ValueError("Bir sınıf listesi fotoğrafı yükleyin.")
    content = _sayfa_bloklari(sayfalar, "SINIF LİSTESİ")
    content.append({"type": "text", "text": "Listedeki bütün öğrencileri çıkar."})
    data, usage = _json_iste(_LISTE_SISTEM, content, _LISTE_SEMASI)
    if not isinstance(data.get("ogrenciler"), list):
        raise AIHatasi("AI yanıtında öğrenci listesi bulunamadı.")
    return data, usage
