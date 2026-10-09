# SınavMatik

Öğretmenlerin açık uçlu sınav kâğıtlarını Claude ile soru soru ön değerlendirmesine, puanları kontrol edip onaylamasına ve sınıf sonuçlarını incelemesine yardımcı olan Streamlit uygulaması. AI önerir, öğretmen onaylar.

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` dosyasını açıp [Claude Console](https://console.anthropic.com/settings/keys)'dan aldığınız anahtarı yazın:

```env
ANTHROPIC_API_KEY=sk-ant-...
```

Uygulamayı başlatın:

```bash
streamlit run app.py
```

## Öğretmen akışı

Her sayfada ana eylem sağ üsttedir (ör. **Sınav ekle**); listeler boşken ortada ne yapılacağını söyleyen bir kutu çıkar. Genel Bakış, ilk kullanımda üç adımlık bir başlangıç rehberi gösterir.

1. **Sınıflar:** Ders ve sınıf/şube oluşturun. Öğrenci listesini elle girin veya listenin fotoğrafını/PDF'ini yükleyip AI ile okutun; okunan satırları düzeltip kaydedin.
2. **Sınavlar:** Sınav adını, türünü, sınıfı ve toplam puanı girin. Cevap anahtarı (veya boş soru kâğıdı) yüklerseniz AI **soru şablonunu** bir kez çıkarır: soru numaraları, özetler, doğru cevaplar ve puanlar. Şablonu tabloda düzeltebilirsiniz. Anahtar yüklemezseniz şablon, onayladığınız ilk kâğıttan oluşur.
3. **Kâğıt Değerlendir → Kâğıt yükle:**
   - *Tek öğrenci:* öğrenciyi seçip sayfalarını (resim veya PDF) yükleyin.
   - *Toplu:* her dosya bir öğrencinin kâğıdıdır. Dosya adında öğrenci numarası veya adı geçiyorsa (`101.pdf`, `ayse kaya.jpg`) öğrenci otomatik eşleşir; diğerlerini tablodan seçersiniz.
4. **Kâğıt Değerlendir → Onay bekleyenler:** AI sonuçları taslak olarak kaydedilir; sayfayı kapatsanız da kaybolmaz. Her kâğıtta solda işaretlenmiş kâğıt, sağda soru kartları görünür: okunan cevap, doğru cevap, gerekçe, hata etiketleri ve güven. Puanı ve etiketleri düzeltip onaylayın. Onaylanmayan kâğıtlar istatistiklere girmez.
5. **Analizler:** Not tablosu (Excel/CSV indirme), not dağılımı, soru bazlı başarı ve hata oranları, en sık hata türleri, kaydedilmiş kâğıtlar, sınıflar arası karşılaştırma ve öğrencinin sınavlar boyunca gelişimi. Onaylı bir sonucu buradan yeniden düzenleyebilir veya silebilirsiniz.
6. **Ayarlar:** AI bağlantı durumu, tahmini AI harcaması, şifre değiştirme ve bütün verileri silme.

## Model ve maliyet

Varsayılan model, görsel okuyabilen en ucuz Claude modeli olan `claude-haiku-4-5`'tir (1 milyon token başına $1 girdi, $5 çıktı). Maliyeti düşük tutmak için:

- Sayfalar gönderilmeden önce uzun kenarı 1568 piksele küçültülür ve JPEG olarak sıkıştırılır.
- Cevap anahtarı her öğrencide yeniden gönderilmez; bir kez metin şablonuna çevrilir.
- Şablon, istekte önbelleğe alınabilecek şekilde en başa konur.

Tahmini harcama **Ayarlar** sayfasında görünür. El yazısı zor okunuyorsa veya puanlama isabetsiz geliyorsa `.env` içinde daha güçlü bir model seçebilirsiniz:

| Ayar | Varsayılan | Açıklama |
| --- | --- | --- |
| `CLAUDE_MODEL` | `claude-haiku-4-5` | `claude-sonnet-5-5` ($2/$10) veya `claude-opus-5-5` ($4/$20) daha isabetli, daha pahalı |
| `CLAUDE_EFFORT` | `low` | Yalnızca Sonnet/Opus: `low`, `medium`, `high` |
| `SINAVMATIK_MAKS_KENAR` | `1568` | Gönderilen sayfanın uzun kenarı (piksel) |
| `SINAVMATIK_DB` | `sinavmatik.db` | Veritabanı dosyasının yolu |

Claude geçici olarak yoğunsa veya istek sınırına takılırsa SDK isteği artan beklemeyle 3 kez yeniden dener. Yine başarısız olursa yüklediğiniz dosyalar ekranda kalır; biraz bekleyip yeniden deneyin.

## Ölçüler

- **Ortalama başarı:** Soruda alınan puanların alınabilecek puana oranı.
- **Hata oranı:** Soruda tam puan alamayan onaylı öğrenci sonuçlarının yüzdesi (kısmi puan da hata sayılır).
- **AI tam puan uyumu:** AI önerisinin öğretmenin verdiği son puanla birebir aynı olma yüzdesi. Tek başına AI'nin doğruluğunun kanıtı değildir.

Sınıflar arası karşılaştırma için sınavların dersi, adı ve soru şablonu aynı olmalıdır.

## Veriler ve gizlilik

- Her hesap yalnızca kendi sınıflarını, sınavlarını ve sonuçlarını görür.
- Veriler yerel `sinavmatik.db` SQLite dosyasında tutulur. Bu dosya öğrenci bilgisi içerir; `.gitignore` ile depo dışında bırakılmıştır. Yedeklemesi size aittir.
- Şifreler tuzlanmış PBKDF2 özeti olarak saklanır; 5 hatalı girişten sonra hesap 15 dakika kilitlenir. Oturum, tarayıcı çerezi sayesinde sayfa yenilemede korunur (14 gün).
- Değerlendirme sırasında kâğıt görselleri Anthropic'in Claude API'sine gönderilir. Öğrenci verilerini yalnızca gerekli izinlerle kullanın.
- **Ayarlar → Verilerimi sil** bütün sınıf, sınav, sonuç ve kâğıt görsellerinizi kalıcı olarak siler.

AI puanları kesin not değildir; AI de cevap anahtarı da hatalı olabilir. Kâğıt üzerindeki kutular yaklaşık konum tahminidir.

## Proje yapısı

```
app.py              Giriş, oturum çerezi, gezinme
views/              Sayfalar: genel_bakis, siniflar, sinavlar, degerlendir, analiz, ayarlar
ui/                 Ortak stil ve arayüz yardımcıları (sayfa başlığı, kart, boş durum, rozet)
assets/             Logo ve sekme simgesi
.streamlit/         Tema ayarları (renkler, köşe yarıçapı)
ai_core.py          Claude çağrıları: kâğıt okuma, soru şablonu, sınıf listesi
degerlendirme.py    AI sonucunu doğrulama ve puan yardımcıları
gorsel.py           Resim/PDF → sayfa görselleri, işaretleme
data_handler.py     SQLite: hesaplar, sınıflar, sınavlar, sonuçlar, AI kullanım kaydı
tests/              pytest testleri
```

## Testler

```bash
pytest
```
