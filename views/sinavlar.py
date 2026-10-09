"""Sınavlar: sınav listesi, sınav ekleme ve sınav ayrıntısı (soru şablonu, bilgiler)."""

import pandas as pd
import streamlit as st

from ai_core import sablon_cikar
from data_handler import (
    anahtar_sayfalari_kaydet,
    anahtar_sayfalarini_getir,
    siniflari_getir,
    sinav_ekle,
    sinav_guncelle,
    sinav_sil,
    sinav_sorulari_kaydet,
    sinavlari_getir,
    sonuclari_getir,
)
from gorsel import KABUL_EDILEN_TURLER, yuklemeleri_sayfalara_cevir
from ui.ortak import (
    kart,
    SINAV_TURLERI,
    ai_calistir,
    bildir,
    bos_durum,
    git,
    rozet,
    satir_metni,
    sayfa_basligi,
    sinif_etiketi,
)

_YENI_SINIF = "Yeni sınıf oluştur…"
_TUM_SINIFLAR = "Tüm sınıflar"
_SABLON_SUTUNLARI = {
    "soru_no": st.column_config.NumberColumn("Soru", min_value=1, step=1, required=True, width="small"),
    "soru_ozeti": st.column_config.TextColumn("Soru özeti", width="large"),
    "dogru_cevap": st.column_config.TextColumn("Doğru cevap / puanlama ölçütü", width="large"),
    "maksimum_puan": st.column_config.NumberColumn("Puan", min_value=0.0, step=0.5, required=True, width="small"),
}


def _sablonu_anahtardan_cikar(owner_id, exam_id, pages, total_points):
    """Cevap anahtarını sınava kaydet ve AI ile soru şablonunu çıkar."""
    anahtar_sayfalari_kaydet(owner_id, exam_id, pages)
    data = ai_calistir(owner_id, "sablon", sablon_cikar, pages, max_puan=total_points)
    return sinav_sorulari_kaydet(owner_id, exam_id, data["sorular"])


@st.dialog("Sınav ekle", width="large")
def _sinav_ekle_penceresi(owner_id, varsayilan_sinif=None):
    classes = siniflari_getir(owner_id)
    name = st.text_input("Sınav adı", placeholder="Örn. Matematik 1. Dönem 1. Yazılı")
    c1, c2 = st.columns(2)
    exam_type = c1.selectbox("Tür", SINAV_TURLERI, index=1)
    total_points = c2.number_input("Toplam puan", min_value=1.0, max_value=1000.0, value=100.0, step=1.0)
    options = [sinif_etiketi(c) for c in classes] + [_YENI_SINIF]
    default = next((i for i, c in enumerate(classes) if c["id"] == varsayilan_sinif), 0)
    choice = st.selectbox("Sınıf", options, index=default)
    if choice == _YENI_SINIF:
        c1, c2 = st.columns(2)
        course = c1.text_input("Ders", placeholder="Matematik")
        class_name = c2.text_input("Sınıf / şube", placeholder="10-A")
    else:
        selected = classes[options.index(choice)]
        course, class_name = selected["course"], selected["class_name"]
    key_uploads = st.file_uploader(
        "Cevap anahtarı (isteğe bağlı)", type=KABUL_EDILEN_TURLER, accept_multiple_files=True,
        help="Cevap anahtarını veya boş soru kâğıdını yüklerseniz sorular, doğru cevaplar ve puanlar bir kez "
             "çıkarılır; bütün kâğıtlar aynı ölçütle değerlendirilir. Şimdi yüklemezseniz sonradan da ekleyebilirsiniz.")
    st.write("")
    _, cancel, save = st.columns([2, 1, 1])
    if cancel.button("Vazgeç", use_container_width=True):
        st.rerun()
    if save.button("Sınavı oluştur", type="primary", use_container_width=True):
        if not name.strip() or not course.strip() or not class_name.strip():
            st.error("Sınav adı, ders ve sınıf alanlarını doldurun.")
            return
        try:
            pages = yuklemeleri_sayfalara_cevir(key_uploads) if key_uploads else []
        except ValueError as exc:
            st.error(str(exc))
            return
        exam_id = sinav_ekle(owner_id, name, course, class_name, exam_type=exam_type, total_points=total_points)
        bildir(f"“{name.strip()}” oluşturuldu.")
        if pages:
            try:
                with st.spinner("Cevap anahtarından sorular çıkarılıyor…"):
                    questions = _sablonu_anahtardan_cikar(owner_id, exam_id, pages, total_points)
                bildir(f"Cevap anahtarından {len(questions)} soru çıkarıldı. Lütfen kontrol edin.", "info")
            except Exception as exc:
                bildir(f"Sınav oluşturuldu ancak cevap anahtarı okunamadı: {exc}", "warning")
        st.session_state["sinav_detay"] = exam_id
        st.rerun()


def _sayimlar(owner_id):
    """Sınav kimliği -> (onaylı, onay bekleyen) kâğıt sayıları."""
    counts = {}
    for result in sonuclari_getir(owner_id, approved=None):
        done, waiting = counts.get(result["exam_id"], (0, 0))
        counts[result["exam_id"]] = (done + 1, waiting) if result["approved"] else (done, waiting + 1)
    return counts


def _liste(owner_id, exams):
    classes = siniflari_getir(owner_id)
    roster_size = {(c["course"], c["class_name"]): c["ogrenci_sayisi"] for c in classes}
    counts = _sayimlar(owner_id)

    shown = exams
    if len(classes) > 1:
        c1, _ = st.columns([1.2, 3])
        labels = [_TUM_SINIFLAR] + [sinif_etiketi(c) for c in classes]
        picked = c1.selectbox("Sınıfa göre filtrele", labels, label_visibility="collapsed", key="sinav_filtre")
        if picked != _TUM_SINIFLAR:
            shown = [e for e in exams if sinif_etiketi(e) == picked]
    st.caption(f"{len(shown)} sınav")

    for exam in shown:
        done, waiting = counts.get(exam["id"], (0, 0))
        size = roster_size.get((exam["course"], exam["class_name"]), 0)
        badges = rozet(f"{len(exam['questions'])} soru", "ok") if exam["questions"] else rozet("Soru şablonu yok", "warn")
        badges += rozet(f"{done} / {size} onaylı" if size else f"{done} onaylı")
        if waiting:
            badges += rozet(f"{waiting} onay bekliyor", "warn")
        with kart():
            info, b1, b2 = st.columns([4.2, 1.15, 1], vertical_alignment="center")
            with info:
                satir_metni(exam["name"], f"{exam['course']} · {exam['class_name']} · {exam['exam_type']} · "
                                          f"{float(exam['total_points']):g} puan", badges,
                            oran=done / size if size else None)
            if b1.button("Değerlendir", icon=":material/fact_check:", key=f"grade_{exam['id']}", use_container_width=True,
                         type="primary" if waiting else "secondary"):
                git("Kâğıt Değerlendir", grade_exam_id=exam["id"],
                    **({"grade_view_pending": "Onay bekleyenler"} if waiting else {}))
            if b2.button("Düzenle", icon=":material/edit:", key=f"open_{exam['id']}", use_container_width=True):
                st.session_state["sinav_detay"] = exam["id"]
                st.rerun()


def _detay(owner_id, exam):
    exam_id = exam["id"]
    done, waiting = _sayimlar(owner_id).get(exam_id, (0, 0))
    graded = done + waiting
    to_grade, back = sayfa_basligi(
        exam["name"], f"{exam['course']} · {exam['class_name']} · {exam['exam_type']} · {float(exam['total_points']):g} puan",
        eylem="Kâğıt değerlendir", eylem_ikon=":material/fact_check:", geri="Sınavlar")
    if back:
        st.session_state.pop("sinav_detay", None)
        st.rerun()
    if to_grade:
        git("Kâğıt Değerlendir", grade_exam_id=exam_id)

    tab_template, tab_info, tab_delete = st.tabs(["Soru şablonu", "Sınav bilgileri", "Sınavı sil"])

    with tab_template:
        if exam["questions"]:
            st.caption("Bütün kâğıtlar bu sorulara ve puanlara göre değerlendirilir. Tabloyu düzenleyip kaydedebilirsiniz.")
        else:
            st.info("Bu sınavın soru şablonu henüz yok. Üç yoldan biriyle oluşturabilirsiniz: aşağıdan cevap anahtarı "
                    "yükleyin, tabloyu elle doldurun veya boş bırakın. Boş bırakırsanız şablon, onayladığınız ilk "
                    "kâğıttan kendiliğinden oluşur.")
        template_df = pd.DataFrame(exam["questions"], columns=list(_SABLON_SUTUNLARI)).astype(
            {"soru_no": "Int64", "soru_ozeti": "string", "dogru_cevap": "string", "maksimum_puan": "float64"})
        edited = st.data_editor(template_df, num_rows="dynamic", hide_index=True, use_container_width=True,
                                column_config=_SABLON_SUTUNLARI, key=f"template_{exam_id}_{len(exam['questions'])}")
        total = float(pd.to_numeric(edited["maksimum_puan"], errors="coerce").fillna(0).sum())
        if len(edited) and abs(total - float(exam["total_points"])) > 0.001:
            st.warning(f"Soru puanlarının toplamı {total:g}; sınavın toplam puanı {float(exam['total_points']):g}.")
        if st.button("Şablonu kaydet", type="primary", key="save_template"):
            saved = sinav_sorulari_kaydet(owner_id, exam_id, edited.to_dict(orient="records"))
            bildir(f"Soru şablonu kaydedildi ({len(saved)} soru).")
            if graded:
                bildir("Daha önce değerlendirilen kâğıtlar eski puanlarıyla kalır.", "info")
            st.rerun()

        st.divider()
        st.markdown("**Cevap anahtarından çıkar**")
        stored = anahtar_sayfalarini_getir(owner_id, exam_id)
        if stored:
            st.caption(f"Bu sınav için {len(stored)} sayfalık cevap anahtarı kayıtlı.")
            st.image(stored, width=140)
        uploads = st.file_uploader("Cevap anahtarı veya boş soru kâğıdı (resim veya PDF)", type=KABUL_EDILEN_TURLER,
                                   accept_multiple_files=True, key=f"key_upload_{exam_id}")
        if exam["questions"]:
            st.caption("Çıkarılan sorular mevcut şablonun yerine yazılır.")
        if st.button("Soruları çıkar", icon=":material/auto_awesome:", disabled=not (uploads or stored), key="extract_template"):
            try:
                with st.spinner("Sorular çıkarılıyor…"):
                    pages = yuklemeleri_sayfalara_cevir(uploads) if uploads else stored
                    questions = _sablonu_anahtardan_cikar(owner_id, exam_id, pages, exam["total_points"])
                bildir(f"{len(questions)} soru çıkarıldı. Lütfen kontrol edin.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with tab_info:
        with st.form(f"exam_info_{exam_id}", border=False):
            new_name = st.text_input("Sınav adı", value=exam["name"])
            c1, c2 = st.columns(2)
            type_index = SINAV_TURLERI.index(exam["exam_type"]) if exam["exam_type"] in SINAV_TURLERI else len(SINAV_TURLERI) - 1
            new_type = c1.selectbox("Tür", SINAV_TURLERI, index=type_index)
            new_total = c2.number_input("Toplam puan", min_value=1.0, max_value=1000.0, value=float(exam["total_points"]), step=1.0)
            st.caption(f"Sınıf: {exam['course']} · {exam['class_name']}. Sınıf sonradan değiştirilemez.")
            if st.form_submit_button("Kaydet", type="primary"):
                if not new_name.strip():
                    st.error("Sınav adı boş olamaz.")
                else:
                    sinav_guncelle(owner_id, exam_id, new_name, new_type, new_total)
                    bildir("Sınav bilgileri güncellendi.")
                    st.rerun()

    with tab_delete:
        st.warning(f"“{exam['name']}” sınavı, {graded} öğrenci sonucu ve kâğıt görselleriyle birlikte kalıcı olarak silinir. "
                   "Bu işlem geri alınamaz.")
        confirm = st.checkbox("Bu sınavı ve bütün sonuçlarını silmek istiyorum", key=f"exam_delete_ok_{exam_id}")
        if st.button("Sınavı sil", icon=":material/delete:", disabled=not confirm, key="delete_exam"):
            sinav_sil(owner_id, exam_id)
            st.session_state.pop("sinav_detay", None)
            bildir(f"“{exam['name']}” silindi.")
            st.rerun()


def goster(user):
    owner_id = user["id"]
    exams = sinavlari_getir(owner_id)
    by_id = {e["id"]: e for e in exams}

    detail = by_id.get(st.session_state.get("sinav_detay"))
    if detail:
        _detay(owner_id, detail)
        return

    add, _ = sayfa_basligi("Sınavlar", "Sınavlarınızı buradan yönetin.", eylem="Sınav ekle" if exams else None)
    if not exams:
        add = bos_durum("＋", "Henüz sınav eklemediniz",
                        "Sınavın adını ve sınıfını girin; isterseniz cevap anahtarını da yükleyin. "
                        "Sonra öğrenci kâğıtlarını yükleyip değerlendirmeye başlayabilirsiniz.",
                        eylem="Sınav ekle", key="bos_sinav_ekle")
    preset = st.session_state.pop("sinav_ekle_ac", None)
    if add or preset is not None:
        _sinav_ekle_penceresi(owner_id, preset if isinstance(preset, int) and not isinstance(preset, bool) else None)
    if exams:
        _liste(owner_id, exams)
