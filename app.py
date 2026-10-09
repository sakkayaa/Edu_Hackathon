"""SınavMatik öğretmen paneli: giriş, oturum ve sayfa gezinmesi."""

import os
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from data_handler import (
    OTURUM_SURESI_GUN,
    kullanici_dogrula,
    kullanici_olustur,
    oturum_kullanicisi,
    oturum_olustur,
    oturum_sil,
    veritabani_hazirla,
)
from ui import ortak
from ui.stil import stili_uygula
from views import analiz, ayarlar, degerlendir, genel_bakis, siniflar, sinavlar

CEREZ = "sinavmatik_oturum"
_ASSETS = os.path.join(os.path.dirname(__file__), "assets")

st.set_page_config(page_title="S\u0131navMatik", page_icon=os.path.join(_ASSETS, "icon.svg"), layout="wide")
veritabani_hazirla()
stili_uygula()


def _cerez_yaz(token):
    """Oturum çerezini tarayıcıya yaz (boş token çerezi siler)."""
    max_age = OTURUM_SURESI_GUN * 86400 if token else 0
    components.html(
        f"<script>window.parent.document.cookie = '{CEREZ}={token}; path=/; max-age={max_age}; SameSite=Lax';</script>",
        height=0,
    )


def _giris_ekrani():
    _, center, _ = st.columns([0.3, 1.4, 0.3])
    with center:
        st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
        info, form = st.columns([1, 1], gap="large", vertical_alignment="center")
        with info:
            st.markdown("""
            <div class="login-panel">
              <div>
                <div class="login-brand">S&#305;navMatik</div>
                <div class="login-title">Sınav kâğıtlarını daha hızlı değerlendirin.</div>
                <ul class="login-list">
                  <li>Kâğıtların fotoğrafını veya PDF'ini yükleyin</li>
                  <li>Her soru için puan önerisini ve gerekçesini görün</li>
                  <li>Puanları kontrol edip onaylayın</li>
                  <li>Sınıfın hangi sorularda zorlandığını inceleyin</li>
                </ul>
              </div>
              <div class="login-foot">Son karar her zaman öğretmenindir.</div>
            </div>
            """, unsafe_allow_html=True)
        with form:
            st.markdown("## Hoş geldiniz")
            st.caption("Devam etmek için giriş yapın veya yeni hesap oluşturun.")
            login_tab, signup_tab = st.tabs(["Giriş yap", "Hesap oluştur"])
            with login_tab:
                with st.form("login_form", border=False):
                    email = st.text_input("E-posta", placeholder="ornek@okul.com")
                    password = st.text_input("Şifre", type="password")
                    submitted = st.form_submit_button("Giriş yap", type="primary", use_container_width=True)
                if submitted:
                    user, error = kullanici_dogrula(email, password)
                    if user:
                        st.session_state["authenticated_user"] = user
                        st.session_state["oturum_token"] = oturum_olustur(user["id"])
                        st.session_state["cerez_bekliyor"] = True
                        st.rerun()
                    st.error(error)
            with signup_tab:
                with st.form("signup_form", border=False):
                    full_name = st.text_input("Ad soyad")
                    signup_email = st.text_input("E-posta", placeholder="ornek@okul.com", key="signup_email")
                    signup_password = st.text_input("Şifre", type="password", placeholder="En az 8 karakter", key="signup_password")
                    signup_confirm = st.text_input("Şifre (tekrar)", type="password")
                    signup_submitted = st.form_submit_button("Hesap oluştur", type="primary", use_container_width=True)
                if signup_submitted:
                    if signup_password != signup_confirm:
                        st.error("Şifreler eşleşmiyor.")
                    else:
                        created, message = kullanici_olustur(signup_email, full_name, signup_password)
                        (st.success if created else st.error)(message)
            st.caption("Her hesap yalnızca kendi sınıflarını ve sınavlarını görür.")


# ------------------------------------------------------------------ oturum
if st.session_state.pop("cikis_yapildi", False):
    _cerez_yaz("")
elif st.session_state.get("authenticated_user") is None:
    # Sayfa yenilendiğinde oturumu tarayıcı çerezinden geri yükle.
    token = st.context.cookies.get(CEREZ)
    restored = oturum_kullanicisi(token)
    if restored:
        st.session_state["authenticated_user"] = restored
        st.session_state["oturum_token"] = token

user = st.session_state.get("authenticated_user")
if user is None:
    st.navigation([st.Page(_giris_ekrani, title="Giriş", url_path="giris", default=True)], position="hidden").run()
    st.stop()

if st.session_state.pop("cerez_bekliyor", False):
    _cerez_yaz(st.session_state["oturum_token"])


# ----------------------------------------------------------------- gezinme
def _sayfa(module, title, icon, url_path, default=False):
    def goster():
        module.goster(user)
    return st.Page(goster, title=title, icon=icon, url_path=url_path, default=default)


ortak.sayaci_sifirla()
ortak.SAYFALAR.clear()
ortak.SAYFALAR.update({
    "Genel Bakış": _sayfa(genel_bakis, "Genel Bakış", ":material/home:", "genel-bakis", default=True),
    "Sınıflar": _sayfa(siniflar, "Sınıflar", ":material/groups:", "siniflar"),
    "Sınavlar": _sayfa(sinavlar, "Sınavlar", ":material/assignment:", "sinavlar"),
    "Kâğıt Değerlendir": _sayfa(degerlendir, "Kâğıt Değerlendir", ":material/fact_check:", "degerlendir"),
    "Analizler": _sayfa(analiz, "Analizler", ":material/bar_chart:", "analizler"),
    "Ayarlar": _sayfa(ayarlar, "Ayarlar", ":material/settings:", "ayarlar"),
})

st.logo(os.path.join(_ASSETS, "logo.svg"), size="large")
page = st.navigation(list(ortak.SAYFALAR.values()))

# Kenar çubuğundan başka sayfaya geçilince açık detay görünümlerini kapat.
by_git = st.session_state.pop("_gecis", False)
if st.session_state.get("_sayfa") != page.title and not by_git:
    for key in ortak.DETAY_ANAHTARLARI:
        st.session_state.pop(key, None)
st.session_state["_sayfa"] = page.title

with st.sidebar:
    st.markdown(f"<div class='side-user'><b>{escape(user['display_name'])}</b><span>{escape(user['email'])}</span></div>",
                unsafe_allow_html=True)
    if st.button("Oturumu kapat", icon=":material/logout:", use_container_width=True):
        oturum_sil(st.session_state.get("oturum_token"))
        st.session_state.clear()
        st.session_state["cikis_yapildi"] = True
        st.rerun()

ortak.bildirimleri_goster()
page.run()

st.markdown("<div class='foot-note'>Öğrenci bilgileri ve kâğıt görselleri bu bilgisayardaki veritabanında saklanır. "
            "Değerlendirme sırasında kâğıt görselleri Claude API'ye gönderilir.</div>", unsafe_allow_html=True)
