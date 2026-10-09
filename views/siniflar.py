"""Sınıflar: sınıf listesi, sınıf ekleme ve sınıf ayrıntısı (öğrenci listesi)."""

import pandas as pd
import streamlit as st

from ai_core import api_anahtari_var_mi, ogrenci_listesi_oku
from data_handler import (
    ogrencileri_getir,
    sinif_ekle,
    sinif_ogrenci_listesi_kaydet,
    sinif_sil,
    siniflari_getir,
    sinav_ekle,
    sinav_getir,
    sinav_guncelle,
    sinavlari_getir,
    sonuclari_getir,
)
from gorsel import KABUL_EDILEN_TURLER, yuklemeleri_sayfalara_cevir
from .degerlendir import kagidi_degerlendir
from ui.ortak import kart, ai_calistir, bildir, bos_durum, git, rozet, satir_metni, sayfa_basligi, sinif_etiketi

_SUTUNLAR = {"student_id": st.column_config.TextColumn("Öğrenci numarası", required=True),
             "name": st.column_config.TextColumn("Ad soyad", required=True)}


@st.dialog("Sınıf ekle")
def _sinif_ekle_penceresi(owner_id):
    course = st.text_input("Ders", placeholder="Matematik")
    class_name = st.text_input("Sınıf / şube", placeholder="10-A")
    st.caption("Öğrenci listesini bir sonraki adımda ekleyeceksiniz.")
    _, cancel, save = st.columns([1, 1, 1.2])
    if cancel.button("Vazgeç", use_container_width=True):
        st.rerun()
    if save.button("Sınıfı oluştur", type="primary", use_container_width=True):
        if not course.strip() or not class_name.strip():
            st.error("Ders ve sınıf alanlarını doldurun.")
            return
        st.session_state["sinif_detay"] = sinif_ekle(owner_id, course, class_name)
        bildir(f"{course.strip()} · {class_name.strip()} oluşturuldu.")
        st.rerun()


def _liste(owner_id, classes):
    exam_counts = {}
    for exam in sinavlari_getir(owner_id):
        key = (exam["course"], exam["class_name"])
        exam_counts[key] = exam_counts.get(key, 0) + 1
    st.caption(f"{len(classes)} sınıf")
    for item in classes:
        badges = rozet(f"{item['ogrenci_sayisi']} öğrenci", "ok" if item["ogrenci_sayisi"] else "warn")
        badges += rozet(f"{exam_counts.get((item['course'], item['class_name']), 0)} sınav")
        with kart():
            info, action = st.columns([4.6, 1.3], vertical_alignment="center")
            with info:
                satir_metni(item["class_name"], item["course"], badges)
            if action.button("Öğrenci listesi", icon=":material/group:", key=f"open_class_{item['id']}", use_container_width=True):
                st.session_state["sinif_detay"] = item["id"]
                st.rerun()


def _fotograftan_aktar(owner_id, selected):
    class_id, course, class_name = selected["id"], selected["course"], selected["class_name"]
    st.caption("Sınıf listesinin fotoğrafını veya PDF'ini yükleyin. Numara ve adlar okunur; kaydetmeden önce kontrol edersiniz.")
    uploaded = st.file_uploader("Liste fotoğrafı veya PDF", type=KABUL_EDILEN_TURLER, accept_multiple_files=True,
                                key=f"roster_upload_{class_id}")
    photo = st.camera_input("Fotoğraf çek", key=f"roster_camera_{class_id}") if st.toggle("Kamerayla çek", key="roster_use_camera") else None
    sources = list(uploaded or []) + ([photo] if photo else [])
    if st.button("Listeyi oku", icon=":material/auto_awesome:", type="primary", disabled=not sources, key="read_roster"):
        try:
            with st.spinner("Liste okunuyor…"):
                data = ai_calistir(owner_id, "liste", ogrenci_listesi_oku, yuklemeleri_sayfalara_cevir(sources))
            st.session_state["roster_draft"] = (class_id, pd.DataFrame(data["ogrenciler"], columns=["student_id", "name", "guven"]))
        except Exception as exc:
            st.error(str(exc))

    draft_class, draft = st.session_state.get("roster_draft", (None, None))
    if draft is None or draft_class != class_id:
        return
    if draft.empty:
        st.warning("Bu görselde öğrenci bulunamadı.")
        return
    st.divider()
    st.markdown(f"**Okunan liste · {len(draft)} öğrenci**")
    st.caption("Numaraları ve yazımı kontrol edin; hatalı hücreye tıklayıp düzeltebilirsiniz.")
    edited = st.data_editor(draft, num_rows="dynamic", hide_index=True, use_container_width=True,
                            column_config={**_SUTUNLAR, "guven": st.column_config.ProgressColumn(
                                "Okuma güveni", min_value=0, max_value=1, format="%.2f")},
                            disabled=["guven"], key=f"roster_draft_edit_{class_id}")
    mode = st.radio("Kaydetme biçimi", ["Mevcut listeye ekle", "Mevcut listenin yerine yaz"], horizontal=True)
    if st.button("Listeyi kaydet", type="primary", key="save_ai_roster"):
        rows = edited[["student_id", "name"]].to_dict(orient="records")
        if mode == "Mevcut listeye ekle":
            rows = ogrencileri_getir(owner_id, course, class_name) + rows
        count = sinif_ogrenci_listesi_kaydet(owner_id, course, class_name, rows)
        del st.session_state["roster_draft"]
        bildir(f"Sınıfta artık {count} öğrenci var.")
        st.rerun()


def _degerlendirmeye_git(owner_id, course, class_name, student, class_exams):
    """Öğrenciyi seçerek mevcut sınavı aç; yoksa kâğıttan kurulacak boş şablonlu sınav oluştur."""
    if class_exams:
        exam_id = class_exams[0]["id"]
    else:
        exam_id = sinav_ekle(owner_id, "Kâğıttan oluşturulan sınav", course, class_name,
                             questions=[], total_points=100)
        bildir("Bu sınıf için 100 puanlık boş bir sınav oluşturuldu. Sorular ilk kâğıttan okunacak.", "info")
    _kagit_yukleme_penceresi(owner_id, exam_id, student)


def _sonucu_gor(owner_id, result):
    """Kayıtlı kâğıdı, AI yanıtlarını ve düzenlenebilir puanlamayı aç."""
    st.session_state.pop("review_edit_id", None)
    st.session_state.pop("review_result_id", None)
    state = {"grade_exam_id": result["exam_id"], "grade_view_pending": "Onay bekleyenler"}
    if result["approved"]:
        state["review_edit_id"] = result["id"]
    else:
        state["review_result_id"] = result["id"]
    git("Kâğıt Değerlendir", **state)


@st.dialog("Öğrenci kâğıdını değerlendir", width="large")
def _kagit_yukleme_penceresi(owner_id, exam_id, student):
    exam = sinav_getir(owner_id, exam_id)
    if exam is None:
        st.error("Sınav bulunamadı. Sayfayı yenileyip yeniden deneyin.")
        return

    st.markdown(f"**{student['name']}** · {student['student_id']}  ")
    st.caption(exam["name"])
    if not exam["questions"]:
        total_points = st.number_input("Sınav toplam puanı", min_value=1.0, max_value=1000.0,
                                       value=float(exam["total_points"]), step=5.0,
                                       key=f"class_total_points_{exam_id}")
        st.info("Bu sınavda soru şablonu yok. Sorular ve puanlar bu kâğıttan okunacak; ilk kâğıdı onayladığınızda şablon oluşacak.")
    else:
        total_points = float(exam["total_points"])
    st.caption(f"Toplam puan: {total_points:g}")

    existing = next((result for result in sonuclari_getir(owner_id, exam_id=exam_id, approved=None)
                     if result["student_id"] == student["student_id"]), None)
    if existing:
        st.warning("Bu öğrencinin bu sınavda kayıtlı sonucu var. Yeniden değerlendirirseniz önceki sonucun yerine yazılır.")

    uploads = st.file_uploader("Sınav kâğıdının sayfaları (resim veya PDF; sayfa sırasıyla seçin)",
                               type=KABUL_EDILEN_TURLER, accept_multiple_files=True,
                               key=f"class_uploads_{exam_id}_{student['student_id']}")
    api_ready = api_anahtari_var_mi()
    if not api_ready:
        st.error("Claude API anahtarı tanımlı değil; kâğıdı değerlendirmek için anahtar gerekli.")
    if st.button("Kâğıdı değerlendir", icon=":material/auto_awesome:", type="primary",
                 disabled=not uploads or not api_ready, key=f"class_run_ai_{exam_id}_{student['student_id']}"):
        try:
            with st.spinner("Kâğıt okunuyor ve sorular değerlendiriliyor…"):
                if total_points != float(exam["total_points"]):
                    sinav_guncelle(owner_id, exam_id, exam["name"], exam["exam_type"], total_points)
                    exam["total_points"] = total_points
                result_id = kagidi_degerlendir(
                    owner_id, exam, student["student_id"], student["name"], yuklemeleri_sayfalara_cevir(uploads))
        except Exception as exc:
            st.error(str(exc))
            return
        git("Kâğıt Değerlendir", grade_exam_id=exam_id, grade_view_pending="Onay bekleyenler",
            review_result_id=result_id)


def _sinif_sinavi(owner_id, exam):
    exam_id = exam["id"]
    to_grade, back = sayfa_basligi(
        exam["name"], f"{exam['course']} · {exam['class_name']} · {exam['exam_type']} · "
        f"{float(exam['total_points']):g} puan",
        eylem="Kâğıt değerlendir", eylem_ikon=":material/fact_check:", geri="Sınıf sınavları")
    if back:
        st.session_state.pop("sinif_sinav_detay", None)
        st.rerun()
    if to_grade:
        git("Kâğıt Değerlendir", grade_exam_id=exam_id)

    students = ogrencileri_getir(owner_id, exam["course"], exam["class_name"])
    results = {result["student_id"]: result
               for result in sonuclari_getir(owner_id, exam_id=exam_id, approved=None)}
    if not students:
        st.info("Bu sınıfın henüz öğrenci listesi yok.")
        return

    heading = st.columns([1.0, 2.2, 2.7, 1.5], vertical_alignment="center")
    for col, label in zip(heading, ["Numara", "Ad soyad", "Değerlendirme", ""]):
        col.markdown(f"**{label}**")
    for student in students:
        columns = st.columns([1.0, 2.2, 2.7, 1.5], vertical_alignment="center")
        columns[0].write(student["student_id"])
        columns[1].write(student["name"])
        result = results.get(student["student_id"])
        if result is None:
            columns[2].write("Değerlendirilmedi")
        else:
            score = sum(float(q.get("ogretmen_puani", q.get("verilen_puan", 0))) for q in result["scores"])
            status = "Onaylandı" if result["approved"] else "Onay bekliyor"
            columns[2].write(f"{status} · {score:g} puan")
        button_label = "Görüntüle" if result is not None else "Değerlendir"
        if columns[3].button(button_label, key=f"class_exam_grade_{exam_id}_{student['student_id']}",
                             use_container_width=True):
            if result is not None:
                _sonucu_gor(owner_id, result)
            else:
                _kagit_yukleme_penceresi(owner_id, exam_id, student)
        st.divider()


def _detay(owner_id, selected):
    class_id, course, class_name = selected["id"], selected["course"], selected["class_name"]
    class_exams = [exam for exam in sinavlari_getir(owner_id)
                   if exam["course"] == course and exam["class_name"] == class_name]
    exam_detail_id = st.session_state.get("sinif_sinav_detay")
    exam_detail = next((exam for exam in class_exams if exam["id"] == exam_detail_id), None)
    if exam_detail is not None:
        _sinif_sinavi(owner_id, exam_detail)
        return
    if exam_detail_id is not None:
        st.session_state.pop("sinif_sinav_detay", None)

    add_exam, back = sayfa_basligi(f"{class_name} · {course}", f"{selected['ogrenci_sayisi']} öğrenci",
                                   eylem="Bu sınıfa sınav ekle", geri="Sınıflar")
    if back:
        st.session_state.pop("sinif_detay", None)
        st.session_state.pop("sinif_sinav_detay", None)
        git("Sınıflar")
    if add_exam:
        git("Sınavlar", sinav_ekle_ac=class_id)

    # Öğrenci listesi, sınıf detayına girince açılan ilk bölüm olsun.
    tab_list, tab_exams, tab_photo, tab_delete = st.tabs(
        ["Öğrenci listesi", "Sınavlar", "Fotoğraftan aktar", "Sınıfı sil"])
    with tab_exams:
        if not class_exams:
            st.info("Bu sınıf için henüz sınav veya quiz eklenmemiş.")
        for exam in class_exams:
            results = sonuclari_getir(owner_id, exam_id=exam["id"], approved=None)
            approved_count = sum(bool(result["approved"]) for result in results)
            waiting_count = len(results) - approved_count
            badges = rozet(f"{approved_count} onaylı")
            if waiting_count:
                badges += rozet(f"{waiting_count} onay bekliyor", "warn")
            if not exam["questions"]:
                badges += rozet("Soru şablonu yok", "warn")
            with kart():
                info, action = st.columns([4, 1.5], vertical_alignment="center")
                with info:
                    satir_metni(exam["name"], f"{exam['exam_type']} · {float(exam['total_points']):g} puan", badges)
                if action.button("Öğrenci listesi", icon=":material/group:", key=f"class_exam_{exam['id']}",
                                 use_container_width=True):
                    st.session_state["sinif_sinav_detay"] = exam["id"]
                    st.rerun()

    with tab_list:
        if not selected["ogrenci_sayisi"]:
            st.info("Bu sınıfta henüz öğrenci yok. Aşağıdaki tabloya yazarak ekleyin veya “Fotoğraftan aktar” sekmesini kullanın.")
        st.caption("Öğrenci eklemek için tablonun sonundaki boş satıra yazın. Kâğıt yüklemek için öğrencinin yanındaki "
                   "“Değerlendir” düğmesini kullanın.")
        students = ogrencileri_getir(owner_id, course, class_name)
        class_exams = [exam for exam in sinavlari_getir(owner_id)
                       if exam["course"] == course and exam["class_name"] == class_name]
        summaries = {}
        latest_result = {}
        for result in sonuclari_getir(owner_id, approved=None):
            if result["course"] != course or result["class_name"] != class_name:
                continue
            score = sum(float(q.get("ogretmen_puani", q.get("verilen_puan", 0))) for q in result["scores"])
            status = "Onaylı" if result["approved"] else "Taslak"
            entry = f"{result['exam_name']} · Kâğıt · {score:g} puan · {status}"
            summaries.setdefault(result["student_id"], []).append((result["exam_created_at"], entry))
            current = latest_result.get(result["student_id"])
            if current is None or result["updated_at"] > current["updated_at"]:
                latest_result[result["student_id"]] = result

        if students:
            heading = st.columns([1.0, 2.2, 5.6], vertical_alignment="center")
            heading[0].markdown("**Numara**")
            heading[1].markdown("**Ad soyad**")
            heading[2].markdown("**Sınav kâğıtları ve değerlendirme sonuçları**")
            for student in students:
                columns = st.columns([1.0, 2.2, 5.6], vertical_alignment="center")
                columns[0].write(student["student_id"])
                columns[1].write(student["name"])
                entries = [entry for _, entry in sorted(
                    summaries.get(student["student_id"], []), reverse=True)]
                result_col, action_col = columns[2].columns([4.2, 1.4], vertical_alignment="center")
                if entries:
                    result_col.write("\n\n".join(entries))
                existing_result = latest_result.get(student["student_id"])
                button_label = "Görüntüle" if existing_result else "Değerlendir"
                button_icon = ":material/visibility:" if existing_result else ":material/auto_awesome:"
                if action_col.button(button_label, icon=button_icon,
                                     key=f"grade_student_{class_id}_{student['student_id']}", use_container_width=True):
                    if existing_result:
                        _sonucu_gor(owner_id, existing_result)
                    else:
                        _degerlendirmeye_git(owner_id, course, class_name, student, class_exams)
                st.divider()

        roster_df = pd.DataFrame(students, columns=["student_id", "name"]).astype(str)
        roster_edit = st.data_editor(roster_df, num_rows="dynamic", hide_index=True, use_container_width=True,
                                     column_config=_SUTUNLAR, key=f"manual_roster_{class_id}")
        if st.button("Öğrenci listesini kaydet", type="primary", key="save_manual_roster"):
            count = sinif_ogrenci_listesi_kaydet(
                owner_id, course, class_name, roster_edit.to_dict(orient="records"))
            bildir(f"{count} öğrenci kaydedildi.")
            st.rerun()
    with tab_photo:
        _fotograftan_aktar(owner_id, selected)
    with tab_delete:
        st.warning(f"{sinif_etiketi(selected)} sınıfı, öğrenci listesi ve bu sınıfa ait bütün sınavlar, sonuçlar ve "
                   "kâğıt görselleri kalıcı olarak silinir. Bu işlem geri alınamaz.")
        confirm = st.checkbox("Bu sınıfı ve bağlı bütün verileri silmek istiyorum", key=f"class_delete_ok_{class_id}")
        if st.button("Sınıfı sil", icon=":material/delete:", disabled=not confirm, key="delete_class"):
            sinif_sil(owner_id, course, class_name)
            st.session_state.pop("sinif_detay", None)
            bildir(f"{sinif_etiketi(selected)} silindi.")
            st.rerun()


def goster(user):
    owner_id = user["id"]
    classes = siniflari_getir(owner_id)
    by_id = {c["id"]: c for c in classes}

    detail = by_id.get(st.session_state.get("sinif_detay"))
    if detail:
        _detay(owner_id, detail)
        return

    add, _ = sayfa_basligi("Sınıflar", "Sınıflarınızı ve öğrenci listelerinizi buradan yönetin.",
                           eylem="Sınıf ekle" if classes else None)
    if not classes:
        add = bos_durum("＋", "Henüz sınıf eklemediniz",
                        "Önce dersinizi ve sınıfınızı ekleyin, ardından öğrenci listesini girin. "
                        "Listeyi elle yazabilir veya fotoğrafından okutabilirsiniz.",
                        eylem="Sınıf ekle", key="bos_sinif_ekle")
    if add:
        _sinif_ekle_penceresi(owner_id)
    if classes:
        _liste(owner_id, classes)
