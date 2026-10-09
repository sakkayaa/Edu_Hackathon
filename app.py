"""SınavMatik öğretmen paneli."""

from io import BytesIO
import json
import uuid

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw

from ai_core import kagit_oku, ogrenci_listesi_oku
from data_handler import (
    ai_sonucu_kontrol_fonksiyonu,
    ogretmen_girisini_dogrula,
    ogretmen_hesabi_getir,
    ogretmen_kaydi_olustur,
    ogretmen_tercihlerini_guncelle,
    ogretmen_veritabani_yolu,
    sayfa_gorsellerini_getir,
    sinav_ekle,
    sinavlari_getir,
    sinif_ekle,
    siniflari_getir,
    sinif_ogrenci_listesi_kaydet,
    ogrencileri_getir,
    ogrenci_ekle,
    sonuc_kaydet,
    sonuclari_getir,
    soru_istatistikleri,
    veritabani_hazirla,
)


st.set_page_config(page_title="SınavMatik", page_icon="📝", layout="wide", initial_sidebar_state="expanded")
veritabani_hazirla()
if st.session_state.get("teacher_user_id"):
    for auth_key in ("login_password", "register_password"):
        st.session_state.pop(auth_key, None)
SUBJECTS = ["Matematik", "Biyoloji", "Kimya", "Türkçe", "Tarih", "Fizik", "İngilizce", "Diğer"]
ACCENTS = {
    "Adaçayı": ("#087f6b", "#e8f5f0"), "Okyanus": ("#426b9a", "#eaf1f8"),
    "Erik": ("#795a91", "#f1ebf5"), "Kiremit": ("#b76d52", "#f8eee9"),
    "Zeytin": ("#72803a", "#f0f2e7"), "Grafit": ("#58666b", "#edf0f0"),
}
SUBJECT_DESIGNS = {
    "Matematik": {"mark": "∑   π   √", "description": "Formüller ve sayılar", "designs": ["Formül Defteri", "Geometri Izgarası"], "pattern": "radial-gradient(circle at 88% 5%, #dcefe8 0, transparent 28%), linear-gradient(90deg, #087f6b08 1px, transparent 1px), linear-gradient(#087f6b08 1px, transparent 1px), #f8f8f4", "pattern_alt": "radial-gradient(circle at 92% 8%, #e2efe9 0, transparent 28%), radial-gradient(#087f6b12 1px, transparent 1px), #f8f8f4"},
    "Biyoloji": {"mark": "DNA   ·   Hücre   ·   Yaşam", "description": "Canlı sistemler", "designs": ["Canlı Sistemler", "Hücre Atlası"], "pattern": "radial-gradient(ellipse at 94% 0%, #e3f1df 0, transparent 30%), radial-gradient(ellipse at 70% 7%, #087f6b08 0, transparent 22%), #f8f8f4", "pattern_alt": "radial-gradient(circle at 92% 5%, #e6f1df 0, transparent 26%), repeating-linear-gradient(120deg, #72803a08 0, #72803a08 1px, transparent 1px, transparent 48px), #f8f8f4"},
    "Kimya": {"mark": "H₂O   ·   NaCl   ·   pH", "description": "Moleküller ve tepkimeler", "designs": ["Molekül Notları", "Periyodik Düzen"], "pattern": "radial-gradient(circle at 90% 8%, #f4e7d6 0, transparent 28%), radial-gradient(circle at 84% 10%, #b76d520c 1px, transparent 2px), #f8f8f4", "pattern_alt": "radial-gradient(circle at 92% 4%, #f2e9dc 0, transparent 26%), linear-gradient(90deg, #b76d5209 1px, transparent 1px), linear-gradient(#b76d5209 1px, transparent 1px), #f8f8f4"},
    "Türkçe": {"mark": "Aa   ·   Sözcük   ·   Metin", "description": "Dil ve anlatım", "designs": ["Metin Atölyesi", "Edebiyat Defteri"], "pattern": "linear-gradient(90deg, #795a9108 1px, transparent 1px), linear-gradient(180deg, #f0eaf4 0, transparent 30%), #f8f8f4", "pattern_alt": "linear-gradient(180deg, #f0eaf4 0, transparent 30%), repeating-linear-gradient(0deg, #795a9108 0, #795a9108 1px, transparent 1px, transparent 42px), #f8f8f4"},
    "Tarih": {"mark": "MÖ   ·   MS   ·   Zaman", "description": "Dönemler ve kaynaklar", "designs": ["Zaman Çizgisi", "Arşiv Notları"], "pattern": "linear-gradient(180deg, #f4eadb 0, transparent 32%), repeating-linear-gradient(0deg, #b76d5208 0, #b76d5208 1px, transparent 1px, transparent 42px), #faf8f3", "pattern_alt": "radial-gradient(ellipse at 90% 0%, #f4eadb 0, transparent 30%), linear-gradient(90deg, #b76d5208 1px, transparent 1px), #faf8f3"},
    "Fizik": {"mark": "F = ma   ·   λ   ·   Δ", "description": "Kuvvet ve hareket", "designs": ["Vektör Alanı", "Dalga Laboratuvarı"], "pattern": "radial-gradient(circle at 88% 8%, #e3eafa 0, transparent 28%), radial-gradient(#426b9a10 1px, transparent 1px), #f8f8f4", "pattern_alt": "radial-gradient(ellipse at 92% 0%, #e3eafa 0, transparent 28%), repeating-linear-gradient(0deg, #426b9a08 0, #426b9a08 1px, transparent 1px, transparent 44px), #f8f8f4"},
    "İngilizce": {"mark": "Aa   ·   Sözcük   ·   Anlam", "description": "Dil ve kelime dağarcığı", "designs": ["Dil Atölyesi", "Kelime Haritası"], "pattern": "linear-gradient(180deg, #e8eef8 0, transparent 32%), repeating-linear-gradient(90deg, #426b9a08 0, #426b9a08 1px, transparent 1px, transparent 54px), #f8f8f4", "pattern_alt": "radial-gradient(ellipse at 90% 0%, #e8eef8 0, transparent 30%), repeating-linear-gradient(0deg, #426b9a08 0, #426b9a08 1px, transparent 1px, transparent 42px), #f8f8f4"},
    "Diğer": {"mark": "Ders   ·   Plan   ·   Gelişim", "description": "Öğretmen çalışma alanı", "designs": ["Sade Çalışma Alanı", "Planlama Panosu"], "pattern": "radial-gradient(ellipse at 90% 0%, #e9f4ee 0, transparent 34%), #f8f8f4", "pattern_alt": "linear-gradient(90deg, #087f6b08 1px, transparent 1px), linear-gradient(180deg, #e9f4ee 0, transparent 34%), #f8f8f4"},
}
# Renkli branş temaları; klasik arayüz bu paletleri kullanmaz.
DESIGN_PALETTES = {
    "Matematik": [("#D5F1E5", "#B7E5D1", "#176B58", "#74C6A6"), ("#DCE5FF", "#C2D1FF", "#354F9D", "#7F98EA")],
    "Biyoloji": [("#DDF0C7", "#C6E5A7", "#3D7438", "#8FBE61"), ("#CDEBDD", "#AEE0C8", "#176B55", "#59B68A")],
    "Kimya": [("#FFE7C5", "#FFD391", "#A4561F", "#E49A4E"), ("#CFEAF4", "#A9DCEA", "#226B83", "#60AEC4")],
    "Türkçe": [("#F1D8EA", "#E6BFE0", "#874D79", "#C47DB5"), ("#FFE1D4", "#FFC8B5", "#A65342", "#D97A61")],
    "Tarih": [("#F2E0BC", "#E9CF98", "#88602D", "#C4933F"), ("#EAE0CC", "#DCC8A7", "#705333", "#AA895D")],
    "Fizik": [("#D6E2FF", "#BDD0FF", "#3459A4", "#7894E0"), ("#CDEBFA", "#A9DDF3", "#176B93", "#55A9D1")],
    "İngilizce": [("#DED9FF", "#C9C2FB", "#5C519C", "#9085DD"), ("#D0EAF2", "#AFDDE9", "#286D85", "#65ACBD")],
    "Diğer": [("#D2EBE1", "#B8DFD0", "#286D5A", "#70BDA3"), ("#DCE5F7", "#C6D3EF", "#4A5F91", "#8298CB")],
}


def arayuz_temasi(subject, design):
    info = SUBJECT_DESIGNS.get(subject, SUBJECT_DESIGNS["Diğer"])
    if design not in info["designs"]:
        return None
    index = info["designs"].index(design)
    wash, panel, deep, border = DESIGN_PALETTES.get(subject, DESIGN_PALETTES["Diğer"])[index]
    pattern = (
        f"radial-gradient(ellipse at 92% 2%, {panel} 0, transparent 35%), "
        f"linear-gradient(135deg, {wash} 0%, #fbfcfa 56%, #f8f8f4 100%)"
    )
    return {"wash": wash, "panel": panel, "deep": deep, "border": border, "pattern": pattern}


CLASSIC_DESIGN = "Klasik SınavMatik"


def kayitli_tercihleri_yaz():
    teacher_id = st.session_state.get("teacher_user_id")
    if teacher_id:
        subject = st.session_state.get("teacher_subject", "Diğer")
        available_designs = [CLASSIC_DESIGN] + SUBJECT_DESIGNS.get(subject, SUBJECT_DESIGNS["Diğer"])["designs"]
        if st.session_state.get("teacher_ui_choice") not in available_designs:
            st.session_state["teacher_ui_choice"] = CLASSIC_DESIGN
        ogretmen_tercihlerini_guncelle(
            teacher_id, subject,
            st.session_state.get("teacher_ui_choice", CLASSIC_DESIGN),
            st.session_state.get("teacher_accent", "Adaçayı"),
        )


def oturum_ac(account):
    st.session_state["teacher_user_id"] = account["id"]
    st.session_state["teacher_subject"] = account["subject"]
    st.session_state["teacher_ui_choice"] = account["ui_choice"]
    st.session_state["teacher_accent"] = account["accent"]
    st.session_state["teacher_name"] = account["full_name"]
    st.session_state["teacher_db_path"] = ogretmen_veritabani_yolu(account["id"])
    st.rerun()


teacher_id = st.session_state.get("teacher_user_id")
profile = ogretmen_hesabi_getir(teacher_id) if teacher_id else None
if profile and profile["subject"] == "İngilizce" and profile["ui_choice"] in ("Language Studio", "Word Atlas"):
    translated_design = {"Language Studio": "Dil Atölyesi", "Word Atlas": "Kelime Haritası"}[profile["ui_choice"]]
    ogretmen_tercihlerini_guncelle(teacher_id, profile["subject"], translated_design, profile["accent"])
    profile = ogretmen_hesabi_getir(teacher_id)
if teacher_id and profile is None:
    for key in ("teacher_user_id", "teacher_name", "teacher_db_path"):
        st.session_state.pop(key, None)
    teacher_id = None
if not teacher_id:
    auth_subject = st.session_state.get("register_subject", SUBJECTS[0])
    auth_info = SUBJECT_DESIGNS[auth_subject]
    auth_design = st.session_state.get(f"register_design_{auth_subject}", CLASSIC_DESIGN)
    auth_accent_name = st.session_state.get("register_accent", "Adaçayı")
    auth_accent, auth_pale = ACCENTS.get(auth_accent_name, ACCENTS["Adaçayı"])
    auth_theme = arayuz_temasi(auth_subject, auth_design)
    auth_background = "radial-gradient(ellipse at 88% 4%, #e3f2e9 0, transparent 34%), #f8f8f4"
    auth_wash, auth_deep, auth_border = auth_pale, auth_accent, f"{auth_accent}30"
    if auth_theme:
        auth_background = auth_theme["pattern"]
        auth_wash, auth_deep, auth_border = auth_theme["wash"], auth_theme["deep"], auth_theme["border"]
    st.markdown(f"""
    <style>
    #MainMenu, [data-testid="stMainMenu"] {{ visibility:hidden !important; }}
    .stAppDeployButton {{ display:none !important; }}
    :root {{ --ink:#19312d; --muted:#71827d; --green:{auth_accent}; --pale:{auth_pale}; --line:#e5ece8; }}
    .stApp {{ background:{auth_background}; }}
    .main .block-container {{ max-width:1050px; padding-top:4rem; }}
    .auth-hero {{ padding:30px 28px; border-radius:20px; background:linear-gradient(145deg,{auth_wash},#fbfcfa); border:1px solid {auth_border}; min-height:330px; }}
    .auth-mark {{ display:inline-block; padding:8px 12px; border-radius:10px; background:#fff; color:{auth_deep}; font-weight:700; letter-spacing:.05em; }}
    .auth-note {{ color:#71827d; line-height:1.7; }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{ background:rgba(255,255,255,.92); border:1px solid var(--line); border-radius:16px; box-shadow:0 8px 24px #17352d0a; }}
    button[data-testid="stBaseButton-primary"] {{ background:{auth_accent}; border-color:{auth_accent}; border-radius:10px; }}
    [data-baseweb="radio"] input:checked + div {{ border-color:{auth_accent} !important; background-color:{auth_accent} !important; }}
    div[data-baseweb="select"]:focus-within > div {{ border-color:{auth_accent} !important; box-shadow:0 0 0 1px {auth_accent} !important; }}
    </style>
    """, unsafe_allow_html=True)
    hero, form_col = st.columns([1.05, 1], gap="large", vertical_alignment="center")
    with hero:
        st.markdown(f"""
        <div class="auth-hero">
          <span class="auth-mark">SınavMatik</span>
          <div style="height:34px"></div>
          <div style="font-size:38px;font-weight:700;line-height:1.15;color:#19312d">Öğretmenler için<br>akıllı değerlendirme.</div>
          <p class="auth-note">Sınavlarını düzenle, AI önerilerini incele ve son kararı kendin ver.</p>
          <div style="height:14px"></div>
          <div style="display:inline-flex;gap:10px;align-items:center;margin-top:12px;padding:10px 14px;border-radius:10px;background:{auth_theme['panel'] if auth_theme else auth_pale};color:{auth_deep};font-size:13px;font-weight:700;letter-spacing:.04em">{auth_info['mark']}</div>
          <p class="auth-note" style="margin-top:14px">{auth_subject} · {auth_design}</p>
        </div>
        """, unsafe_allow_html=True)
    with form_col:
        with st.container(border=True):
            st.subheader("Öğretmen hesabı")
            auth_mode = st.radio("İşlem", ["Giriş yap", "Kayıt ol"], horizontal=True, label_visibility="collapsed", key="auth_mode")
            if auth_mode == "Giriş yap":
                email = st.text_input("E-posta", key="login_email", placeholder="ogretmen@okul.edu.tr")
                password = st.text_input("Parola", type="password", key="login_password")
                if st.button("Giriş yap", type="primary", use_container_width=True, key="login_submit"):
                    account = ogretmen_girisini_dogrula(email, password)
                    if account:
                        oturum_ac(account)
                    st.error("E-posta veya parola hatalı.")
            else:
                full_name = st.text_input("Ad soyad", key="register_name", placeholder="Adınız Soyadınız")
                email = st.text_input("E-posta", key="register_email", placeholder="ogretmen@okul.edu.tr")
                password = st.text_input("Parola", type="password", key="register_password", help="En az 8 karakter")
                subject = st.selectbox("Öğretmen branşı", SUBJECTS, key="register_subject")
                designs = [CLASSIC_DESIGN] + SUBJECT_DESIGNS[subject]["designs"]
                design = st.selectbox("Arayüz seçimi", designs, key=f"register_design_{subject}",
                    help="Klasik SınavMatik görünümünü veya branşınıza özel sade bir tasarımı seçin.")
                accent = st.selectbox("Vurgu rengi", list(ACCENTS), key="register_accent")
                if st.button("Hesap oluştur", type="primary", use_container_width=True, key="register_submit"):
                    try:
                        account = ogretmen_kaydi_olustur(full_name, email, password, subject, design, accent)
                        oturum_ac(account)
                    except ValueError as exc:
                        st.error(str(exc))
                st.caption("Parola güvenli biçimde saklanır. Arayüz ve renk tercihlerini daha sonra değiştirebilirsin.")
                st.caption("Bu kurulumdaki mevcut sınıf ve sınavlar ilk öğretmen hesabına bağlanır. Sonraki hesapların verileri ayrıdır.")
    st.stop()

teacher_db_path = ogretmen_veritabani_yolu(teacher_id)
if "teacher_subject" not in st.session_state:
    st.session_state["teacher_subject"] = profile["subject"]
if "teacher_ui_choice" not in st.session_state:
    st.session_state["teacher_ui_choice"] = profile["ui_choice"]
elif st.session_state["teacher_ui_choice"] in ("Language Studio", "Word Atlas"):
    st.session_state["teacher_ui_choice"] = {"Language Studio": "Dil Atölyesi", "Word Atlas": "Kelime Haritası"}[st.session_state["teacher_ui_choice"]]
if "teacher_accent" not in st.session_state:
    st.session_state["teacher_accent"] = profile["accent"]
subject_info = SUBJECT_DESIGNS.get(profile["subject"], SUBJECT_DESIGNS["Diğer"])
accent_color, accent_pale = ACCENTS.get(profile["accent"], ACCENTS["Adaçayı"])
selected_design = profile["ui_choice"]
theme = arayuz_temasi(profile["subject"], selected_design)
page_background = "radial-gradient(ellipse at 90% 0%, #e9f4ee 0, transparent 34%), #f8f8f4"
theme_wash, theme_panel, theme_deep, theme_border = "#f8f8f4", "#f3faf6", accent_color, "#e5ece8"
if theme:
    page_background = theme["pattern"]
    theme_wash, theme_panel, theme_deep, theme_border = theme["wash"], theme["panel"], theme["deep"], theme["border"]
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
:root {{ --ink:#19312d; --muted:#71827d; --green:{accent_color}; --pale:{accent_pale}; --line:#e5ece8; --coral:#ed8c70; --theme-wash:{theme_wash}; --theme-panel:{theme_panel}; --theme-deep:{theme_deep}; --theme-border:{theme_border}; }}
html, body, [class*="css"] {{ font-family:'DM Sans',sans-serif; color:var(--ink); }}
.stApp {{ background:{page_background}; }}
.main .block-container {{ padding-top:2.2rem; padding-bottom:2.5rem; }}
section[data-testid="stSidebar"] {{ background:linear-gradient(180deg,var(--theme-wash) 0%,#f8f8f4 100%); border-right:1px solid var(--theme-border); }}
#MainMenu, [data-testid="stMainMenu"] {{ visibility:hidden !important; }}
.stAppDeployButton {{ display:none !important; }}
section[data-testid="stSidebar"] *, .stApp, .stApp p, .stApp label, .stApp [data-testid="stMarkdownContainer"] {{ color:var(--ink); }}
input, textarea, [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] {{ color:var(--ink) !important; }}
div[data-baseweb="select"] * {{ color:var(--ink) !important; }}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2 {{ font-size:19px; margin-bottom:0; }}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {{ padding:10px 12px; border-radius:10px; transition:background .16s ease, transform .16s ease; }}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{ background:var(--theme-panel); transform:translateX(2px); }}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {{ background:var(--theme-panel); font-weight:700; }}
div[data-testid="stMetric"] {{ background:linear-gradient(145deg,#fff 55%,var(--theme-wash)); border:1px solid var(--theme-border); border-top:3px solid var(--theme-deep); padding:17px 20px; border-radius:15px; box-shadow:0 5px 16px #17352d0a; transition:transform .16s ease, box-shadow .16s ease; }}
div[data-testid="stMetric"]:hover {{ transform:translateY(-2px); box-shadow:0 9px 22px #17352d12; }}
div[data-testid="stMetricLabel"] {{ color:var(--muted); }}
div[data-testid="stMetricValue"] {{ color:var(--green); }}
div[data-testid="stVerticalBlockBorderWrapper"] {{ background:rgba(255,255,255,.92); border:1px solid var(--line); border-radius:15px; box-shadow:0 5px 18px #17352d08; }}
div[data-baseweb="select"]:focus-within > div {{ border-color:var(--green) !important; box-shadow:0 0 0 1px var(--green) !important; }}
div[data-baseweb="radio"] input:checked + div {{ border-color:var(--green) !important; background-color:var(--green) !important; }}
.stApp h1 {{ letter-spacing:-.035em; font-weight:700; }}
.stApp h2, .stApp h3 {{ letter-spacing:-.02em; }}
.eyebrow {{ color:var(--green); text-transform:uppercase; letter-spacing:.1em; font-size:11px; font-weight:700; }}
.subtle {{ color:var(--muted); font-size:14px; }}
button[kind="primary"] {{ background:var(--green); border-color:var(--green); }}
div.stButton > button {{ color:#17352d !important; background:#ffffff !important; border:1px solid #cbd7d2 !important; }}
div.stButton > button[kind="primary"] {{ color:#ffffff !important; background:var(--green) !important; border-color:var(--green) !important; box-shadow:0 4px 12px #087f6b26; }}
button[data-testid="stBaseButton-secondary"] {{ color:#17352d !important; background:#ffffff !important; border:1px solid #cbd7d2 !important; }}
button[data-testid="stBaseButton-primary"] {{ color:#ffffff !important; background:var(--green) !important; border:1px solid var(--green) !important; box-shadow:0 4px 12px #087f6b26; }}
div.stButton > button, button[data-testid="stBaseButton-secondary"], button[data-testid="stBaseButton-primary"] {{ border-radius:10px; transition:transform .16s ease, box-shadow .16s ease; }}
div.stButton > button:hover, button[data-testid="stBaseButton-secondary"]:hover, button[data-testid="stBaseButton-primary"]:hover {{ transform:translateY(-1px); box-shadow:0 5px 14px #17352d16; }}
[data-testid="stFileUploader"] section {{ background:#f7fbf8; border:1px dashed {accent_color}70; border-radius:12px; }}
</style>
""", unsafe_allow_html=True)

veritabani_hazirla(teacher_db_path)
exams = sinavlari_getir(teacher_db_path)
classes = siniflari_getir(teacher_db_path)
all_results = sonuclari_getir(db_path=teacher_db_path)
if "navigate_to" in st.session_state:
    st.session_state["navigation"] = st.session_state.pop("navigate_to")

with st.sidebar:
    st.markdown("<div style='font-size:27px'>📝</div>", unsafe_allow_html=True)
    st.markdown("## SınavMatik")
    st.caption(f"{profile['full_name']} · {profile['subject']}")
    st.markdown("<div class='eyebrow' style='margin:24px 0 8px'>ÇALIŞMA ALANI</div>", unsafe_allow_html=True)
    page = st.radio("Gezinme", ["Genel Bakış", "Sınıflar", "Sınav Gir", "Kâğıt Değerlendir", "Analizler", "Ayarlar"],
                    label_visibility="collapsed", key="navigation")
    st.caption("Profil ve görünüm ayarları · Ayarlar")
    st.markdown("<div style='height:30vh'></div>", unsafe_allow_html=True)
    st.markdown("---")
    st.caption("AI önerir · Öğretmen onaylar")
    if st.button("Oturumu kapat", key="logout_button"):
        for key in ("teacher_user_id", "teacher_name", "teacher_db_path", "teacher_subject", "teacher_ui_choice", "teacher_accent"):
            st.session_state.pop(key, None)
        st.rerun()

header_left, header_right = st.columns([5, 1])
with header_left:
    st.markdown(f"<span class='subtle'>SınavMatik　/　<span style='color:#172522'>{page}</span></span>", unsafe_allow_html=True)
with header_right:
    if st.button("⚙ Ayarlar", key="top_settings_button", use_container_width=True):
        st.session_state["navigate_to"] = "Ayarlar"
        st.rerun()
if selected_design != CLASSIC_DESIGN:
    st.markdown(f"<div style='display:inline-flex;align-items:center;gap:10px;margin:10px 0 4px;padding:8px 13px;border-radius:12px;background:{accent_pale};color:{accent_color};font-size:13px;font-weight:600'><span style='letter-spacing:.04em'>{subject_info['mark']}</span><span>{subject_info['description']} · {selected_design}</span></div>", unsafe_allow_html=True)
st.write("")


def sinav_etiketi(exam):
    return f"{exam['name']} · {exam['course']} · {exam['class_name']} (#{exam['id']})"


def sayfayi_isaretle(image_bytes, questions, page_no):
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)
    for question in questions:
        for mark in question.get("isaretlemeler", []):
            if int(mark.get("sayfa_no", 0)) != page_no:
                continue
            width, height = image.size
            x1 = max(0, min(width - 1, int(float(mark.get("x1", 0)) * width)))
            y1 = max(0, min(height - 1, int(float(mark.get("y1", 0)) * height)))
            x2 = max(x1 + 1, min(width - 1, int(float(mark.get("x2", 1)) * width)))
            y2 = max(y1 + 1, min(height - 1, int(float(mark.get("y2", 1)) * height)))
            errors = question.get("ogretmen_hatalari", question.get("hatalar", []))
            color = "red" if errors else "green"
            draw.rectangle((x1, y1, x2, y2), outline=color, width=max(3, width // 400))
            label = mark.get("etiket") or f"Soru {question['soru_no']}"
            draw.text((x1, max(0, y1 - 20)), label, fill=color, stroke_width=2, stroke_fill="white")
    return image


if page == "Genel Bakış":
    st.title("Genel Bakış")
    st.markdown("<p class='subtle'>Sınavlarını ve öğrenci değerlendirmelerini tek yerden takip et.</p>", unsafe_allow_html=True)
    if st.button("＋  Sınav Gir", type="primary", key="dashboard_add_exam"):
        st.session_state["navigate_to"] = "Sınav Gir"
        st.rerun()
    total_papers = len(all_results)
    total_exams = len(exams)
    average = None
    if all_results:
        percentages = []
        for result in all_results:
            earned = sum(float(q.get("ogretmen_puani", q.get("verilen_puan", 0))) for q in result["scores"])
            maximum = sum(float(q["maksimum_puan"]) for q in result["scores"])
            if maximum:
                percentages.append(100 * earned / maximum)
        average = sum(percentages) / len(percentages) if percentages else None
    m1, m2, m3 = st.columns(3)
    m1.metric("Oluşturulan sınav", total_exams)
    m2.metric("Onaylanan kâğıt", total_papers)
    m3.metric("Genel puan ortalaması", f"%{average:.1f}" if average is not None else "—")

    left, right = st.columns([1.8, 1])
    with left:
        with st.container(border=True):
            st.markdown("**Sınav performansı**")
            st.caption("Onaylanan öğrenci sonuçlarının sınav bazında puan ortalaması")
            if all_results:
                chart_rows = []
                for result in all_results:
                    earned = sum(float(q.get("ogretmen_puani", q.get("verilen_puan", 0))) for q in result["scores"])
                    maximum = sum(float(q["maksimum_puan"]) for q in result["scores"])
                    if maximum:
                        chart_rows.append({"Sınav": result["exam_name"], "Ortalama (%)": round(100 * earned / maximum, 1),
                                           "Sınıf": result["class_name"]})
                if chart_rows:
                    chart_data = pd.DataFrame(chart_rows).groupby(["Sınav", "Sınıf"], as_index=False)["Ortalama (%)"].mean()
                    chart = alt.Chart(chart_data).mark_line(point=alt.OverlayMarkDef(filled=True, size=75),
                        color="#087f6b", strokeWidth=3).encode(
                        x=alt.X("Sınav:N", sort=None, axis=alt.Axis(labelAngle=0, title=None)),
                        y=alt.Y("Ortalama (%):Q", scale=alt.Scale(domain=[0, 100]), title="Ortalama (%)"),
                        tooltip=["Sınav", "Sınıf", alt.Tooltip("Ortalama (%):Q", format=".1f")],
                    ).properties(height=280)
                    st.altair_chart(chart, width="stretch")
                else:
                    st.info("Grafik için henüz puanlı sonuç bulunmuyor.")
            else:
                st.info("İlk sınavını oluşturduğunda performans grafiğin burada görünecek.")
    with right:
        with st.container(border=True):
            st.markdown("**Değerlendirme durumu**")
            st.caption("Sistemdeki onaylı sonuçlar")
            st.markdown(f"<div style='font-size:42px;font-weight:700'>{total_papers}</div><span class='subtle'>öğrenci kâğıdı kaydedildi</span>", unsafe_allow_html=True)
            st.progress(1.0 if total_papers else 0.0, text="Öğretmen onaylı sonuç")
            class_counts = {}
            for result in all_results:
                class_counts[result["class_name"]] = class_counts.get(result["class_name"], 0) + 1
            for class_name, count in sorted(class_counts.items()):
                st.markdown(f"**{class_name}** <span style='float:right;color:#77837f'>{count} sonuç</span>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("**Son öğrenci sonuçları**")
        st.caption("Öğretmen tarafından onaylanıp kaydedilen son değerlendirmeler")
        if all_results:
            recent = []
            for result in all_results[:8]:
                earned = sum(float(q.get("ogretmen_puani", q.get("verilen_puan", 0))) for q in result["scores"])
                maximum = sum(float(q["maksimum_puan"]) for q in result["scores"])
                recent.append({"Öğrenci": result["student_name"] or result["student_id"], "Sınav": result["exam_name"],
                               "Ders": result["course"], "Sınıf": result["class_name"],
                               "Puan": f"{earned:g} / {maximum:g}", "Durum": "Onaylandı"})
            st.dataframe(pd.DataFrame(recent), hide_index=True, width="stretch")
        else:
            st.info("Henüz sonuç yok. ‘Kâğıt Değerlendir’ bölümünden ilk öğrencinin kâğıdını yükleyebilirsin.")

elif page == "Sınıflar":
    st.title("Sınıflar ve Öğrenciler")
    st.markdown("<p class='subtle'>Sınıflarını ve öğrenci listesini oluştur. AI ile okunan listeyi kaydetmeden önce düzenleyebilirsin.</p>", unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("Sınıf ekle")
        with st.form("class_form"):
            c1, c2 = st.columns(2)
            new_course = c1.text_input("Ders", placeholder="Matematik")
            new_class = c2.text_input("Sınıf / şube", placeholder="10-A")
            add_class = st.form_submit_button("Sınıfı kaydet")
        if add_class:
            if not new_course.strip() or not new_class.strip():
                st.error("Ders ve sınıf bilgilerini girin.")
            else:
                sinif_ekle(new_course, new_class, db_path=teacher_db_path)
                st.success(f"{new_course} · {new_class} sınıfı hazır.")
                st.rerun()

    classes = siniflari_getir(teacher_db_path)
    if classes:
        selected_class = st.selectbox("Öğrenci listesi düzenlenecek sınıf", classes,
            format_func=lambda c: f"{c['course']} · {c['class_name']}", key="roster_class")
        course, class_name = selected_class["course"], selected_class["class_name"]
        st.subheader("Fotoğraftan öğrenci listesi aktar")
        photo = st.camera_input("Sınıf listesinin fotoğrafını çek", key="roster_camera")
        uploaded_roster = st.file_uploader("veya liste fotoğrafını yükle", type=["png", "jpg", "jpeg", "webp"], key="roster_upload")
        roster_photo = photo or uploaded_roster
        if st.button("AI ile listeyi oku", disabled=roster_photo is None, key="read_roster"):
            try:
                raw = ogrenci_listesi_oku(roster_photo.getvalue())
                students = json.loads(raw).get("ogrenciler", [])
                st.session_state["roster_draft"] = pd.DataFrame(students, columns=["student_id", "name", "guven"])
                st.session_state["roster_draft_class"] = (course, class_name)
            except Exception as exc:
                st.error(str(exc))

        draft = st.session_state.get("roster_draft")
        if draft is not None and st.session_state.get("roster_draft_class") == (course, class_name):
            st.info("AI'nin çıkardığı satırları, özellikle numaraları ve yazımı, kaydetmeden önce düzelt.")
            edited = st.data_editor(draft, num_rows="dynamic", hide_index=True, width="stretch",
                disabled=["guven"] if "guven" in draft.columns else [], key=f"roster_edit_{course}_{class_name}")
            if st.button("Düzeltilmiş listeyi kaydet", type="primary", key="save_ai_roster"):
                count = sinif_ogrenci_listesi_kaydet(course, class_name, edited.to_dict(orient="records"), db_path=teacher_db_path)
                del st.session_state["roster_draft"]
                st.success(f"{count} öğrenci {course} · {class_name} sınıfına kaydedildi.")
                st.rerun()

        st.subheader("Kayıtlı öğrenciler")
        roster = ogrencileri_getir(course, class_name, db_path=teacher_db_path)
        roster_df = pd.DataFrame(roster, columns=["student_id", "name"])
        roster_edit = st.data_editor(roster_df, num_rows="dynamic", hide_index=True, width="stretch",
            column_config={"student_id": "Öğrenci numarası", "name": "Ad soyad"}, key=f"manual_roster_{course}_{class_name}")
        if st.button("Öğrenci listesindeki düzenlemeleri kaydet", key="save_manual_roster"):
            count = sinif_ogrenci_listesi_kaydet(course, class_name, roster_edit.to_dict(orient="records"), db_path=teacher_db_path)
            st.success(f"{count} öğrenci kaydedildi.")
            st.rerun()
    else:
        st.info("Öğrenci eklemek için önce bir sınıf oluştur.")

elif page == "Sınav Gir":
    st.title("Sınav Gir")
    st.markdown("<p class='subtle'>Sınavı tanımla; soruları yazmana gerek yok. Öğrenci kâğıdını yüklediğinde AI soruları görselden okuyacak.</p>", unsafe_allow_html=True)
    with st.form("exam_form"):
        exam_name = st.text_input("Sınav adı", placeholder="Mat Ara Sınav 1")
        exam_type = st.selectbox("Sınav türü", ["Quiz", "Ara sınav", "Final", "Diğer"])
        class_options = siniflari_getir(teacher_db_path)
        if class_options:
            selected_class = st.selectbox("Ders ve sınıf", ["Yeni sınıf oluştur"] + class_options,
                format_func=lambda c: c if isinstance(c, str) else f"{c['course']} · {c['class_name']}")
        else:
            selected_class = "Yeni sınıf oluştur"
        if selected_class == "Yeni sınıf oluştur":
            c1, c2 = st.columns(2)
            course = c1.text_input("Ders", placeholder="Matematik")
            class_name = c2.text_input("Sınıf / şube", placeholder="10-A")
        else:
            course, class_name = selected_class["course"], selected_class["class_name"]
            st.caption(f"Öğrenci listesi: {len(ogrencileri_getir(course, class_name, db_path=teacher_db_path))} kayıt")
        total_points = st.number_input("Sınavın toplam puanı", min_value=1.0, max_value=1000.0,
                                       value=100.0, step=1.0, help="Kâğıtta soru puanları yazıyorsa AI onları okur; yazmıyorsa bu toplamı sorulara dağıtır.")
        create_exam = st.form_submit_button("Sınavı oluştur ve kâğıt girişine geç", type="primary")
        if create_exam:
            if not exam_name.strip() or not course.strip() or not class_name.strip():
                st.error("Sınav adı, ders ve sınıf alanlarını doldurun.")
            else:
                new_id = sinav_ekle(exam_name, course, class_name, [], exam_type=exam_type, total_points=total_points, db_path=teacher_db_path)
                st.session_state["grade_exam_id"] = new_id
                st.session_state["navigate_to"] = "Kâğıt Değerlendir"
                st.success(f"{exam_name} oluşturuldu. Şimdi öğrenci kâğıtlarını ekleyebilirsin.")
                st.rerun()
    st.subheader("Kayıtlı sınavlar")
    if exams:
        st.dataframe(pd.DataFrame([{"Sınav": e["name"], "Tür": e.get("exam_type", "Sınav"),
            "Ders": e["course"], "Sınıf": e["class_name"], "Toplam puan": e.get("total_points", 100)} for e in exams]),
            hide_index=True, width="stretch")
    else:
        st.info("Henüz sınav oluşturulmadı.")

elif page == "Kâğıt Değerlendir":
    st.title("Kâğıt Değerlendir")
    st.markdown("<p class='subtle'>AI önerisini incele, puanları düzenle ve öğretmen onayıyla kaydet.</p>", unsafe_allow_html=True)
    if not exams:
        st.info("Önce ‘Sınav Gir’ bölümünden bir sınav tanımla.")
    else:
        preferred_id = st.session_state.pop("grade_exam_id", None)
        preferred_index = next((i for i, exam in enumerate(exams) if exam["id"] == preferred_id), 0)
        selected_exam = st.selectbox("Değerlendirilecek sınav", exams, index=preferred_index,
            format_func=sinav_etiketi, key="grade_exam")
        st.markdown(f"<div class='subtle'>{selected_exam['exam_type']}　·　{selected_exam['course']}　·　{selected_exam['class_name']}</div>", unsafe_allow_html=True)
        roster = ogrencileri_getir(selected_exam["course"], selected_exam["class_name"], db_path=teacher_db_path)
        roster_choice = st.selectbox("Sınıf listesinden öğrenci seç", ["Manuel öğrenci girişi"] + roster,
            format_func=lambda s: s if isinstance(s, str) else f"{s['student_id']} — {s['name']}",
            key=f"roster_student_{selected_exam['id']}")
        if isinstance(roster_choice, dict):
            student_id, student_name = roster_choice["student_id"], roster_choice["name"]
            st.info(f"Seçilen öğrenci: {student_name} · {student_id}")
        else:
            c1, c2 = st.columns(2)
            student_id = c1.text_input("Öğrenci numarası / benzersiz kimliği", key="student_id")
            student_name = c2.text_input("Öğrenci adı soyadı", key="student_name")
        uploads = st.file_uploader("Bu öğrencinin sınav sayfalarını yükleyin (sırasıyla seçin)",
            type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key=f"uploads_{selected_exam['id']}")
        if uploads:
            st.caption(f"{len(uploads)} sayfa seçildi. Seçim sırası sayfa sırası olarak kullanılacak.")
        has_answer_key = st.radio("Cevap anahtarı var mı?", ["Hayır", "Evet"], horizontal=True,
                                  key=f"has_key_{selected_exam['id']}")
        key_uploads = []
        if has_answer_key == "Evet":
            key_uploads = st.file_uploader("Cevap anahtarı sayfalarını yükleyin (isteğe göre birden fazla)",
                type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key=f"key_uploads_{selected_exam['id']}") or []
            st.caption("AI cevap anahtarını karşılaştırma için kullanır; aynı zamanda cevabı kendi çözümüyle de kontrol eder.")
        if st.button("AI ile soru soru değerlendir", type="primary", key="run_ai"):
            if not student_id.strip() or not student_name.strip():
                st.error("Bireysel sonucu kaydedebilmek için öğrenci numarası ve ad soyad girin.")
            elif not uploads:
                st.error("En az bir sınav sayfası yükleyin.")
            elif has_answer_key == "Evet" and not key_uploads:
                st.error("Cevap anahtarı olduğunu seçtiniz; değerlendirme için en az bir anahtar sayfası yükleyin.")
            else:
                try:
                    page_bytes = [upload.getvalue() for upload in uploads]
                    key_bytes = [upload.getvalue() for upload in key_uploads]
                    with st.spinner("Sayfalar okunuyor ve sorular değerlendiriliyor..."):
                        raw = kagit_oku(page_bytes, selected_exam["questions"], cevap_anahtari=key_bytes or None,
                                        max_puan=selected_exam.get("total_points", 100))
                    checked = ai_sonucu_kontrol_fonksiyonu(raw, selected_exam["questions"], len(page_bytes),
                                                           toplam_puan=selected_exam.get("total_points", 100))
                    if not checked["gecerli"]:
                        raise ValueError("; ".join(checked["uyarilar"]))
                    st.session_state["pending_result"] = {
                        "exam_id": selected_exam["id"], "student_id": student_id.strip(),
                        "student_name": student_name.strip(), "pages": page_bytes,
                        "result": {"sorular": checked["sorular"]},
                        "warnings": checked["uyarilar"], "token": uuid.uuid4().hex[:10],
                    }
                except Exception as exc:
                    st.error(str(exc))
        pending = st.session_state.get("pending_result")
        if pending and pending["exam_id"] == selected_exam["id"]:
            st.divider()
            st.subheader(f"Öğretmen kontrolü · {pending['student_id']}")
            st.warning("AI puanları öneridir. Görselleri ve gerekçeleri kontrol edip gerekirse puanları düzenleyin.")
            for warning in pending.get("warnings", []):
                st.warning(warning)
            reviewed = []
            for q in pending["result"].get("sorular", []):
                definition = next((item for item in selected_exam["questions"] if item["soru_no"] == q["soru_no"]), {})
                max_score = float(definition.get("maksimum_puan", q.get("maksimum_puan", 100)))
                st.markdown(f"#### Soru {q['soru_no']} · AI önerisi: {q['verilen_puan']} / {max_score}")
                if q.get("soru_ozeti"):
                    st.caption("Okunan soru: " + q["soru_ozeti"])
                st.caption(q.get("gerekce", "Gerekçe yok."))
                if q.get("anahtar_kontrolu"):
                    st.info("Cevap anahtarı kontrolü: " + q["anahtar_kontrolu"])
                if q.get("hatalar"):
                    st.error("Bulunan hatalar: " + ", ".join(q["hatalar"]))
                else:
                    st.success("AI hata bulmadı; yine de yanıtı kontrol edin.")
                if float(q.get("guven", 0)) < 0.6:
                    st.warning(f"Düşük AI güveni: {q.get('guven', 0):.0%}")
                final_score = st.number_input(f"Öğretmen puanı (en fazla {max_score})", min_value=0.0, max_value=max_score,
                    value=min(max(float(q.get("verilen_puan", 0)), 0.0), max_score), step=0.5,
                    key=f"final_{pending['token']}_{q['soru_no']}")
                corrected_errors = st.text_input("Öğretmen hata etiketleri (virgülle ayırın; yoksa boş bırakın)",
                    value=", ".join(q.get("hatalar", [])), key=f"errors_{pending['token']}_{q['soru_no']}")
                reviewed.append({**q, "maksimum_puan": max_score, "ai_puani": float(q.get("verilen_puan", 0)),
                    "ogretmen_puani": final_score,
                    "ogretmen_hatalari": [x.strip() for x in corrected_errors.split(",") if x.strip()]})
            with st.expander("AI’nin kâğıt üzerindeki konum önerilerini incele"):
                st.caption("Kırmızı kutular hata önerilerini, yeşil kutular AI'nin hata bulmadığı bölgeleri gösterir. Konumlar yaklaşık olabilir.")
                for i, image_bytes in enumerate(pending["pages"], start=1):
                    st.image(sayfayi_isaretle(image_bytes, reviewed, i), caption=f"Sayfa {i}", width="stretch")
            total = sum(item["ogretmen_puani"] for item in reviewed)
            st.metric("Öğretmen onayına göre toplam", f"{total:g} / {sum(x['maksimum_puan'] for x in reviewed):g}")
            if st.button("Öğretmen onayıyla sonucu kaydet", type="primary", key="approve_result"):
                sonuc_kaydet(pending["exam_id"], pending["student_id"], pending["student_name"], reviewed, pending["pages"], db_path=teacher_db_path)
                if pending["student_name"].strip():
                    ogrenci_ekle(selected_exam["course"], selected_exam["class_name"],
                                 pending["student_id"], pending["student_name"], db_path=teacher_db_path)
                del st.session_state["pending_result"]
                st.success("Öğrenci sonucu ve sınav sayfaları kaydedildi.")
                st.rerun()

elif page == "Ayarlar":
    st.title("Ayarlar")
    st.markdown("<p class='subtle'>Branşını, arayüzünü ve vurgu rengini buradan düzenle. Seçimler hesabına kaydedilip hemen uygulanır.</p>", unsafe_allow_html=True)
    settings_left, settings_right = st.columns([1, 1.15], gap="large")
    with settings_left:
        with st.container(border=True):
            st.subheader("Öğretmen profili")
            st.text_input("Ad soyad", value=profile["full_name"], disabled=True)
            st.text_input("E-posta", value=profile["email"], disabled=True)
            st.selectbox("Öğretmen branşı", SUBJECTS,
                index=SUBJECTS.index(profile["subject"]) if profile["subject"] in SUBJECTS else len(SUBJECTS) - 1,
                key="teacher_subject", on_change=kayitli_tercihleri_yaz)
            current_subject = st.session_state.get("teacher_subject", profile["subject"])
            design_options = [CLASSIC_DESIGN] + SUBJECT_DESIGNS[current_subject]["designs"]
            current_design = st.session_state.get("teacher_ui_choice", profile["ui_choice"])
            st.selectbox("Arayüz seçimi", design_options,
                index=design_options.index(current_design) if current_design in design_options else 0,
                key="teacher_ui_choice", on_change=kayitli_tercihleri_yaz)
            st.selectbox("Vurgu rengi", list(ACCENTS),
                index=list(ACCENTS).index(profile["accent"]) if profile["accent"] in ACCENTS else 0,
                key="teacher_accent", on_change=kayitli_tercihleri_yaz)
    with settings_right:
        current_subject = st.session_state.get("teacher_subject", profile["subject"])
        current_design = st.session_state.get("teacher_ui_choice", profile["ui_choice"])
        current_accent = st.session_state.get("teacher_accent", profile["accent"])
        current_info = SUBJECT_DESIGNS[current_subject]
        current_color, current_pale = ACCENTS[current_accent]
        current_theme = arayuz_temasi(current_subject, current_design)
        current_pattern = current_theme["pattern"] if current_theme else "radial-gradient(ellipse at 90% 0%, #e9f4ee 0, transparent 34%), #ffffff"
        current_wash = current_theme["wash"] if current_theme else "#f8f8f4"
        current_panel = current_theme["panel"] if current_theme else current_pale
        current_deep = current_theme["deep"] if current_theme else current_color
        current_border = current_theme["border"] if current_theme else f"{current_color}45"
        with st.container(border=True):
            st.subheader("Canlı önizleme")
            st.markdown(f"""
            <div style="padding:20px;border:1px solid {current_border};border-radius:15px;background:{current_pattern}">
              <div style="font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:{current_deep};font-weight:700">SınavMatik　/　Genel Bakış</div>
              <div style="margin:14px 0;padding:17px;border-radius:12px;background:rgba(255,255,255,.93);border:1px solid {current_border}">
                <div style="font-size:21px;font-weight:700;color:{current_deep}">{current_info['mark']}</div>
                <div style="margin-top:5px;font-size:13px;color:#71827d">{current_subject} · {current_design}</div>
                <div style="margin-top:15px;padding:10px 12px;border-radius:9px;background:{current_panel};color:{current_deep};font-size:13px;font-weight:700">Oluşturulan sınav　　3</div>
              </div>
              <div style="display:inline-block;padding:8px 12px;border-radius:9px;background:{current_deep};color:white;font-size:12px;font-weight:600">＋ Sınav Gir</div>
            </div>
            """, unsafe_allow_html=True)
            st.caption("Arayüz veya renk seçimini değiştirince önizleme de yenilenir.")

else:
    st.title("Sonuçlar ve Analiz")
    st.markdown("<p class='subtle'>Bireysel notları ve soru bazlı sınıf eğilimlerini incele.</p>", unsafe_allow_html=True)
    if not exams:
        st.info("Analiz için önce sınav oluşturup öğrenci sonuçlarını onaylayın.")
    else:
        selected_exam = st.selectbox("Analiz edilecek sınav", exams, format_func=sinav_etiketi, key="analysis_exam")
        individual = sonuclari_getir(exam_id=selected_exam["id"], db_path=teacher_db_path)
        if not individual:
            st.info("Bu sınav için henüz onaylanmış öğrenci sonucu yok.")
        else:
            rows = []
            for result in individual:
                total = sum(float(q.get("ogretmen_puani", q.get("verilen_puan", 0))) for q in result["scores"])
                maximum = sum(float(q["maksimum_puan"]) for q in result["scores"])
                rows.append({"Öğrenci no": result["student_id"], "Öğrenci": result["student_name"],
                             "Sınıf": result["class_name"], "Toplam": total, "Maksimum": maximum})
            st.subheader("Bireysel sınav sonuçları")
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            for result in individual:
                label = f"{result['student_name']} · {result['student_id']}" if result["student_name"] else result["student_id"]
                with st.expander(f"{label} — soru detayları ve kâğıt"):
                    details = [{"Soru": q["soru_no"], "AI önerisi": q.get("ai_puani", q.get("verilen_puan")),
                        "Öğretmen puanı": q.get("ogretmen_puani", q.get("verilen_puan")), "Maksimum": q["maksimum_puan"],
                        "Hatalar": ", ".join(q.get("ogretmen_hatalari", q.get("hatalar", []))), "Gerekçe": q.get("gerekce", "")}
                        for q in result["scores"]]
                    st.dataframe(pd.DataFrame(details), hide_index=True, width="stretch")
                    for page_no, image_bytes in enumerate(sayfa_gorsellerini_getir(result["id"], db_path=teacher_db_path), start=1):
                        st.image(sayfayi_isaretle(image_bytes, result["scores"], page_no),
                            caption=f"Onaylanan kâğıt · Sayfa {page_no}", width="stretch")
        st.subheader("Soru bazlı sınıf analizi")
        same_exam = [e for e in exams if e["name"].strip().casefold() == selected_exam["name"].strip().casefold()
                     and e["course"].strip().casefold() == selected_exam["course"].strip().casefold()
                     and (e["questions"] == selected_exam["questions"] or not e["questions"] and not selected_exam["questions"])]
        class_exam_ids = {}
        for exam in same_exam:
            class_exam_ids.setdefault(exam["class_name"], []).append(exam["id"])
        chosen_classes = st.multiselect("Karşılaştırılacak sınıflar", list(class_exam_ids), default=[selected_exam["class_name"]])
        stats = soru_istatistikleri([eid for name in chosen_classes for eid in class_exam_ids[name]], db_path=teacher_db_path)
        if stats:
            st.caption("Hata oranı tam puan alamayan öğrencilerin oranı; AI uyumu ise öğretmen puanıyla birebir eşleşme oranıdır.")
            table = pd.DataFrame(stats).rename(columns={"sinif": "Sınıf", "soru_no": "Soru", "ogrenci_sayisi": "Öğrenci sayısı",
                "hata_yapan": "Hata yapan", "hata_yuzdesi": "Hata oranı (%)",
                "ai_ogretmen_tam_uyum_yuzdesi": "AI tam puan uyumu (%)"})
            st.dataframe(table[["Sınıf", "Soru", "Öğrenci sayısı", "Hata yapan", "Hata oranı (%)", "AI tam puan uyumu (%)"]],
                hide_index=True, width="stretch")
        else:
            st.info("Seçilen sınıflarda henüz onaylı sonuç yok.")

st.markdown("<div style='height:24px'></div><span class='subtle'>Yerel MVP · Öğrenci bilgileri ve kâğıt görselleri yerel veritabanında saklanır.</span>", unsafe_allow_html=True)
