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

