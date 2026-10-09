"""Sayfaların paylaştığı arayüz yardımcıları."""

from datetime import datetime
from html import escape

import streamlit as st

from data_handler import kullanim_kaydet

SINAV_TURLERI = ["Quiz", "Ara sınav", "Final", "Diğer"]
# Sayfa değişince kapanması gereken "detay görünümü" anahtarları.
DETAY_ANAHTARLARI = ["sinav_detay", "sinif_detay"]

# app.py her çalıştırmada doldurur: sayfa adı -> st.Page
SAYFALAR = {}
_kart_sayaci = 0


def sayaci_sifirla():
    """Her betik çalıştırmasının başında kart anahtarlarını baştan başlat."""
    global _kart_sayaci
    _kart_sayaci = 0


def kart():
    """Beyaz zeminli, çerçeveli kutu. Stil, anahtarın ürettiği `st-key-kart-…` sınıfına bağlıdır."""
    global _kart_sayaci
    _kart_sayaci += 1
    return st.container(border=True, key=f"kart-{_kart_sayaci}")


def git(page, **state):
    """Başka bir sayfaya geç; verilen değerleri oturum durumuna yaz."""
    st.session_state.update(state)
    st.session_state["_gecis"] = True
    st.switch_page(SAYFALAR[page])


def bildir(message, kind="success"):
    """Sayfa yeniden çizildikten sonra gösterilecek kısa bildirim bırak."""
    st.session_state.setdefault("flash", []).append((kind, message))


def bildirimleri_goster():
    for kind, message in st.session_state.pop("flash", []):
        if kind == "success":
            st.toast(message, icon=":material/check_circle:")
        else:
            getattr(st, kind)(message)


def sinav_etiketi(exam):
    return f"{exam['name']} · {exam['course']} · {exam['class_name']}"


def sinif_etiketi(item):
    return f"{item['course']} · {item['class_name']}"


def ogrenci_etiketi(student):
    return f"{student['student_id']} — {student['name']}"


def ai_calistir(owner_id, islem, fn, *args, **kwargs):
    """AI işlevini çalıştır, kullanımını kaydet ve yalnızca sonucu döndür."""
    data, usage = fn(*args, **kwargs)
    kullanim_kaydet(owner_id, islem, usage)
    return data


def yerel_tarih(iso_text):
    """UTC ISO zaman damgasını yerel saat dilimindeki datetime'a çevir."""
    try:
        return datetime.fromisoformat(str(iso_text).replace("Z", "+00:00")).astimezone()
    except (TypeError, ValueError):
        return None


def sayfa_basligi(title, subtitle="", eylem=None, eylem_ikon=":material/add:", geri=None):
    """Sayfa başlığı; sağ üstte isteğe bağlı ana eylem düğmesi.

    geri: "← ..." bağlantısının metni. (eylem tıklandı mı, geri tıklandı mı) döndürür.
    """
    back_clicked = False
    if geri:
        back_clicked = st.button(geri, icon=":material/arrow_back:", type="tertiary", key=f"geri_{title}")
    left, right = st.columns([4, 1.25], vertical_alignment="bottom")
    with left:
        st.title(title)
        if subtitle:
            st.markdown(f"<p class='page-sub'>{escape(subtitle)}</p>", unsafe_allow_html=True)
    clicked = False
    if eylem:
        clicked = right.button(eylem, icon=eylem_ikon, type="primary", use_container_width=True, key=f"eylem_{title}")
    st.markdown("<div class='page-head-gap'></div>", unsafe_allow_html=True)
    return clicked, back_clicked


def bos_durum(simge, title, text, eylem=None, key=None, eylem_ikon=":material/add:"):
    """Ortalanmış boş durum kutusu; düğme tıklandıysa True döndürür."""
    with kart():
        st.markdown(f"<div class='empty'><div class='empty-icon'>{simge}</div><h3>{escape(title)}</h3>"
                    f"<p>{escape(text)}</p></div>", unsafe_allow_html=True)
        clicked = False
        if eylem:
            _, center, _ = st.columns([1, 1, 1])
            clicked = center.button(eylem, icon=eylem_ikon, type="primary", use_container_width=True, key=key or f"bos_{title}")
        st.markdown("<div style='height:1.4rem'></div>", unsafe_allow_html=True)
    return clicked


def rozet(text, tur=""):
    """Küçük durum etiketi HTML'i. tur: '' | 'ok' | 'warn' | 'danger'."""
    return f"<span class='badge {tur}'>{escape(str(text))}</span>"


def satir_metni(title, meta, rozetler="", oran=None):
    """Liste satırının sol tarafı: başlık, açıklama, rozetler ve isteğe bağlı ilerleme çubuğu."""
    bar = f"<div class='bar'><i style='width:{min(max(oran, 0), 1) * 100:.0f}%'></i></div>" if oran is not None else ""
    st.markdown(f"<div class='row-title'>{escape(title)}</div><div class='row-meta'>{escape(meta)}</div>"
                f"<div style='margin-top:6px'>{rozetler}</div>{bar}", unsafe_allow_html=True)


def kalici_secim(widget, label, options, key, **kwargs):
    """Seçimi sayfalar arasında hatırlayan selectbox/radio.

    Streamlit o an ekranda olmayan bileşenlerin değerini unutur; son seçim ayrı
    bir anahtarda saklanıp bileşen yeniden çizilirken geri yüklenir.
    """
    saved = st.session_state.get(f"_son_{key}")
    if st.session_state.get(key) not in options:
        st.session_state[key] = saved if saved in options else options[0]
    value = widget(label, options, key=key, **kwargs)
    if value is None:  # segmented_control seçimi kaldırılabilir; son geçerli seçime dön
        value = saved if saved in options else options[0]
    st.session_state[f"_son_{key}"] = value
    return value
