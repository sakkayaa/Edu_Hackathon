"""Görsel dosyalarını JPEG sayfalara dönüştürme ve cevap alanlarını işaretleme."""

from io import BytesIO

from PIL import Image, ImageDraw

KABUL_EDILEN_TURLER = ("png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp", "pdf")
MAKS_KENAR = 1800


def _jpeg(image):
    image = image.convert("RGB")
    image.thumbnail((MAKS_KENAR, MAKS_KENAR), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()


def sayfa_boyutu(image_bytes):
    with Image.open(BytesIO(image_bytes)) as image:
        return image.size


def dosyalari_sayfalara_cevir(files):
    """(filename, bytes) çiftlerini sıralı, küçültülmüş JPEG sayfalara çevir."""
    pages = []
    files = list(files or [])
    if not files:
        raise ValueError("En az bir dosya seçin.")
    for filename, content in files:
        suffix = str(filename).lower().rsplit(".", 1)[-1] if "." in str(filename) else ""
        if suffix == "pdf":
            try:
                import fitz
                document = fitz.open(stream=content, filetype="pdf")
                pages.extend(_jpeg(page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).pil_image())
                             for page in document)
                document.close()
            except Exception as exc:
                raise ValueError(f"PDF okunamadı: {filename}") from exc
        else:
            try:
                with Image.open(BytesIO(content)) as image:
                    frames = getattr(image, "n_frames", 1)
                    for index in range(frames):
                        image.seek(index)
                        pages.append(_jpeg(image.copy()))
            except Exception as exc:
                raise ValueError(f"Görsel okunamadı: {filename}") from exc
    if not pages:
        raise ValueError("Dosyalarda okunabilir sayfa bulunamadı.")
    return pages


def yuklemeleri_sayfalara_cevir(uploads):
    return dosyalari_sayfalara_cevir((upload.name, upload.getvalue()) for upload in uploads)


def sayfayi_isaretle(image_bytes, questions, page_number):
    """İlgili sayfadaki soru kutularını, puan kırıldıysa kırmızıyla çiz."""
    with Image.open(BytesIO(image_bytes)) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for question in questions:
        for mark in question.get("isaretlemeler", []):
            if mark.get("sayfa_no") != page_number:
                continue
            x1 = max(0, min(width - 1, round(float(mark.get("x1", 0)) * width)))
            y1 = max(0, min(height - 1, round(float(mark.get("y1", 0)) * height)))
            x2 = max(0, min(width - 1, round(float(mark.get("x2", 0)) * width)))
            y2 = max(0, min(height - 1, round(float(mark.get("y2", 0)) * height)))
            if x2 <= x1 or y2 <= y1:
                continue
            awarded = question.get("ogretmen_puani", question.get("verilen_puan", 0)) or 0
            maximum = question.get("maksimum_puan", 0) or 0
            color = (220, 45, 45) if float(awarded) < float(maximum) else (30, 150, 85)
            draw.rectangle((x1, y1, x2, y2), outline=color, width=max(3, width // 250))
            label = mark.get("etiket") or f"Soru {question.get('soru_no', '')}"
            draw.text((x1 + 3, max(0, y1 - 18)), str(label), fill=color)
    return image
