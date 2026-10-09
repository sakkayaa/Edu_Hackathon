"""Ayarlar: şifre ve veri yönetimi."""

import streamlit as st

from data_handler import hesap_verilerini_sil, sifre_degistir
from ui.ortak import kart, bildir, sayfa_basligi


def goster(user):
    owner_id = user["id"]
    sayfa_basligi("Ayarlar", "Hesap ve veri yönetimi.")

    with kart():
        st.subheader("Şifre değiştir")
        with st.form("password_form", clear_on_submit=True):
            current = st.text_input("Mevcut şifre", type="password")
            c1, c2 = st.columns(2)
            new = c1.text_input("Yeni şifre", type="password", placeholder="En az 8 karakter")
            confirm = c2.text_input("Yeni şifre (tekrar)", type="password")
            submitted = st.form_submit_button("Şifreyi güncelle", type="primary")
        if submitted:
            if new != confirm:
                st.error("Yeni şifreler eşleşmiyor.")
            else:
                ok, message = sifre_degistir(owner_id, current, new)
                (st.success if ok else st.error)(message)
                if ok:
                    st.caption("Diğer cihazlardaki oturumların kapatıldı; sayfayı yenilersen yeniden giriş yapman gerekir.")

    with kart():
        st.subheader("Verilerimi sil")
        st.warning("Bütün sınıfların, öğrenci listelerin, sınavların, sonuçların ve kâğıt görsellerin kalıcı olarak silinir. "
                   "Hesabın açık kalır. Bu işlem geri alınamaz.")
        confirm_text = st.text_input("Onaylamak için SİL yaz", key="wipe_confirm")
        if st.button("Bütün verilerimi sil", disabled=confirm_text.strip() != "SİL"):
            hesap_verilerini_sil(owner_id)
            st.session_state.pop("wipe_confirm", None)
            bildir("Bütün verilerin silindi.", "info")
            st.rerun()
