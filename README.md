# SınavMatik

SınavMatik, öğretmenlerin sınav kâğıtlarını düzenlemesine ve açık uçlu sorular için yapay zekâdan ön puanlama önerisi almasına yardımcı olan bir uygulamadır. Son puanı öğretmen kontrol eder ve onaylar.

## Özellikler

- Öğretmen hesabı ve sınıf yönetimi
- Öğrenci ve sınav bilgilerini kaydetme
- Sınav kâğıtlarını görsel olarak yükleme
- Gemini ile soru ve öğrenci listesi okuma
- Puan önerilerini öğretmenin inceleyip düzenlemesi
- Onaylanan sonuçları inceleme

## Gereksinimler

- Python 3.10 veya üzeri
- Google Gemini API anahtarı

## Kurulum

Depoyu indirin ve proje klasörüne geçin:

```bash
git clone https://github.com/sakkayaa/Edu_Hackathon.git
cd Edu_Hackathon
```

Sanal ortam oluşturup bağımlılıkları yükleyin:

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\Activate.ps1
```

macOS veya Linux:

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

Proje klasöründe `.env` dosyası oluşturup API anahtarınızı ekleyin:

```env
GEMINI_API_KEY=anahtarınızı_buraya_yazın
```

Uygulamayı başlatın:

```bash
streamlit run app.py
```

## Kullanım

Uygulama açıldığında öğretmen hesabı oluşturun veya giriş yapın. Sınıf ve sınav bilgilerini ekleyin, kâğıtları yükleyin ve AI önerilerini inceleyin. Puanları onaylamadan önce kontrol edip gerektiğinde düzenleyin.

## Proje dosyaları

- `app.py`: Streamlit uygulaması ve arayüz akışı
- `ai_core.py`: Gemini API ile görsel okuma işlemleri
- `data_handler.py`: Veri doğrulama ve değerlendirme yardımcıları
- `degerlendirme.py`: Puan ve sonuç işleme yardımcıları
- `index.html`: Web arayüzü dosyası

## Veri ve gizlilik

Uygulama yerel veritabanı kullanır. AI ile okuma sırasında yüklenen görseller Gemini API hizmetine gönderilir. Gerçek öğrenci verileri kullanırken gerekli izinleri alın ve API anahtarınızı paylaşmayın.
