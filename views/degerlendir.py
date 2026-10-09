"""Kâğıt Değerlendir: kâğıt yükleme, AI ön değerlendirmesi ve öğretmen onayı."""

import re
from html import escape

import pandas as pd
import streamlit as st

from ai_core import api_anahtari_var_mi, kagit_oku
from data_handler import (
    ogrenci_ekle,
    ogrencileri_getir,
    sayfa_gorsellerini_getir,
    sinav_sorulari_kaydet,
    sinavlari_getir,
    sonuc_getir,
    sonuc_kaydet,
    sonuc_sil,
    sonuclari_getir,
)
from degerlendirme import DUSUK_GUVEN, ai_sonucu_kontrol, puan_ozeti, sablon_olustur
from gorsel import KABUL_EDILEN_TURLER, dosyalari_sayfalara_cevir, sayfa_boyutu, yuklemeleri_sayfalara_cevir
from ui.ortak import (
    kart,
    ai_calistir,
    bildir,
    bos_durum,
    git,
    kalici_secim,
    ogrenci_etiketi,
    rozet,
    sayfa_basligi,
)

_GORUNUMLER = ["Kâğıt yükle", "Onay bekleyenler"]
_ATLA = "— atla —"
_MANUEL = "Listede yok (elle girin)"


def kagidi_degerlendir(owner_id, exam, student_id, student_name, pages):
    """Kâğıdı AI ile değerlendir ve onay bekleyen taslak olarak kaydet; sonuç kimliğini döndür."""
    data = ai_calistir(owner_id, "kagit", kagit_oku, pages, exam["questions"], max_puan=exam["total_points"])
    checked = ai_sonucu_kontrol(data, exam["questions"], [sayfa_boyutu(p) for p in pages], toplam_puan=exam["total_points"])
    if not checked["gecerli"]:
        raise ValueError("; ".join(checked["uyarilar"]))
    scores = [{**q, "ai_puani": q["verilen_puan"]} for q in checked["sorular"]]
    return sonuc_kaydet(owner_id, exam["id"], student_id, student_name, scores, pages,
                        approved=False, warnings=checked["uyarilar"])


def _yukleyici_sifirla(exam_id):
    key = f"upload_seq_{exam_id}"
    st.session_state[key] = st.session_state.get(key, 0) + 1


def _tek_ogrenci(owner_id, exam, roster, existing):
    exam_id = exam["id"]
    # Varsayılan olarak kâğıdı henüz girilmemiş ilk öğrenci seçilir.
    first_open = next((i for i, s in enumerate(roster) if s["student_id"] not in existing), 0)
    choice = st.selectbox("Öğrenci", roster + [_MANUEL], index=first_open, key=f"student_{exam_id}",
                          format_func=lambda s: s if isinstance(s, str) else
                          ogrenci_etiketi(s) + ("   ✓ değerlendirildi" if s["student_id"] in existing else ""))
    if isinstance(choice, dict):
        student_id, student_name = choice["student_id"], choice["name"]
    else:
        c1, c2 = st.columns(2)
        student_id = c1.text_input("Öğrenci numarası", key=f"manual_id_{exam_id}")
        student_name = c2.text_input("Öğrenci adı soyadı", key=f"manual_name_{exam_id}")
    uploads = st.file_uploader("Sınav kâğıdının sayfaları (resim veya PDF; sayfa sırasıyla seçin)",
                               type=KABUL_EDILEN_TURLER, accept_multiple_files=True,
                               key=f"uploads_{exam_id}_{st.session_state.get(f'upload_seq_{exam_id}', 0)}")
    if student_id.strip() in existing:
        st.warning("Bu öğrencinin bu sınavda kayıtlı bir sonucu var. Yeniden değerlendirirseniz önceki sonucun yerine yazılır.")
    if st.button("Değerlendir", icon=":material/auto_awesome:", type="primary", key="run_ai", disabled=not uploads):
        if not student_id.strip() or not student_name.strip():
            st.error("Öğrenci numarası ve ad soyad gerekli.")
            return
        try:
            with st.spinner("Kâğıt okunuyor ve sorular değerlendiriliyor…"):
                result_id = kagidi_degerlendir(
                    owner_id, exam, student_id, student_name, yuklemeleri_sayfalara_cevir(uploads))
        except Exception as exc:
            st.error(str(exc))
            return
        _yukleyici_sifirla(exam_id)
        st.session_state["review_result_id"] = result_id
        st.session_state["grade_view_pending"] = "Onay bekleyenler"
        st.rerun()


_TR_SADE = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def _sade(text):
    """Karşılaştırma için küçük harfe çevir ve Türkçe harfleri sadeleştir (Çelik = celik)."""
    return text.replace("İ", "i").replace("I", "i").casefold().translate(_TR_SADE)


def _dosyadan_ogrenci(filename, roster):
    """Dosya adında numarası veya adı geçen öğrenciyi bul."""
    stem = _sade(filename.rsplit(".", 1)[0])
    tokens = set(re.split(r"[^0-9a-z]+", stem))
    for student in roster:
        if _sade(student["student_id"]) in tokens:
            return student
    for student in roster:
        parts = _sade(student["name"]).split()
        if parts and all(part in tokens for part in parts):
            return student
    return None


def _toplu(owner_id, exam, roster, existing):
    exam_id = exam["id"]
    if not roster:
        st.info("Toplu yükleme için önce “Sınıflar” bölümünden bu sınıfın öğrenci listesini oluşturun.")
        return
    st.caption("Her dosya bir öğrencinin kâğıdıdır; çok sayfalı kâğıtlar için PDF kullanın. Dosya adında öğrenci numarası "
               "veya adı geçiyorsa (örn. 101.pdf, ayse kaya.jpg) öğrenci kendiliğinden eşleşir.")
    uploads = st.file_uploader("Öğrenci kâğıtları", type=KABUL_EDILEN_TURLER, accept_multiple_files=True,
                               key=f"batch_{exam_id}_{st.session_state.get(f'upload_seq_{exam_id}', 0)}")
    if not uploads:
        return
    labels = {ogrenci_etiketi(s): s for s in roster}
    rows = []
    for upload in uploads:
        match = _dosyadan_ogrenci(upload.name, roster)
        rows.append({"Dosya": upload.name, "Öğrenci": ogrenci_etiketi(match) if match else _ATLA})
    mapping = st.data_editor(
        pd.DataFrame(rows), hide_index=True, use_container_width=True, disabled=["Dosya"],
        column_config={"Öğrenci": st.column_config.SelectboxColumn("Öğrenci", options=[_ATLA] + list(labels), required=True)},
        key=f"batch_map_{exam_id}_{len(uploads)}_{st.session_state.get(f'upload_seq_{exam_id}', 0)}")
    chosen = [label for label in mapping["Öğrenci"] if label != _ATLA]
    duplicates = sorted({label for label in chosen if chosen.count(label) > 1})
    if duplicates:
        st.error("Aynı öğrenci birden fazla dosyaya atanmış: " + ", ".join(duplicates))
    overwrite = [label for label in chosen if labels[label]["student_id"] in existing]
    if overwrite:
        st.warning(f"{len(overwrite)} öğrencinin kayıtlı sonucu var; yeniden değerlendirilirse üzerine yazılır.")
    if st.button(f"{len(chosen)} kâğıdı değerlendir", icon=":material/auto_awesome:", type="primary", key="run_batch",
                 disabled=not chosen or bool(duplicates)):
        progress = st.progress(0.0, text="Başlıyor...")
        done, failures = 0, []
        jobs = [(upload, labels[label]) for upload, label in zip(uploads, mapping["Öğrenci"]) if label != _ATLA]
        for index, (upload, student) in enumerate(jobs):
            progress.progress(index / len(jobs), text=f"{student['name']} değerlendiriliyor ({index + 1}/{len(jobs)})...")
            try:
                pages = dosyalari_sayfalara_cevir([(upload.name, upload.getvalue())])
                kagidi_degerlendir(owner_id, exam, student["student_id"], student["name"], pages)
                done += 1
            except Exception as exc:
                failures.append(f"{student['name']} ({upload.name}): {exc}")
        progress.empty()
        if done:
            bildir(f"{done} kâğıt değerlendirildi ve onayınızı bekliyor.")
            _yukleyici_sifirla(exam_id)
            st.session_state["grade_view_pending"] = "Onay bekleyenler"
        for failure in failures:
            bildir(failure, "error")
        st.rerun()


def _soru_karti(q, token):
    """Bir sorunun puan önerisini göster, öğretmen girişlerini al ve güncel soru kaydını döndür."""
    number = q["soru_no"]
    ai_score = float(q.get("ai_puani", q.get("verilen_puan", 0)))
    with kart():
        confidence = float(q.get("guven", 0))
        st.markdown(f"<div class='q-head'><b>Soru {number}</b><span>Önerilen puan: {ai_score:g} / "
                    f"{float(q['maksimum_puan']):g}</span></div>", unsafe_allow_html=True)
        lines = [("Soru", q.get("soru_ozeti")), ("Öğrenci cevabı", q.get("ogrenci_cevabi")),
                 ("Doğru cevap", q.get("dogru_cevap")), ("Gerekçe", q.get("gerekce"))]
        st.markdown("".join(f"<div class='q-line'><i>{label}</i>{escape(str(text))}</div>" for label, text in lines if text),
                    unsafe_allow_html=True)
        tags = "".join(rozet(e, "danger") for e in q.get("hatalar", [])) or rozet("Hata bulunmadı", "ok")
        if confidence < DUSUK_GUVEN:
            tags += rozet("Emin değil — dikkatle kontrol edin", "warn")
        st.markdown(f"<div style='margin:6px 0 2px'>{tags}</div>", unsafe_allow_html=True)
        if q.get("anahtar_kontrolu"):
            st.warning("Cevap anahtarı uyarısı: " + q["anahtar_kontrolu"])

        c1, c2, c3 = st.columns([1, 1, 2.4])
        maximum = c1.number_input("Tam puan", min_value=0.0, max_value=1000.0,
                                  value=float(q["maksimum_puan"]), step=0.5,
                                  key=f"max_{token}_{number}")
        current = min(max(float(q.get("ogretmen_puani", q.get("verilen_puan", 0))), 0.0), maximum)
        final = c2.number_input("Puan", min_value=0.0, max_value=maximum, value=current, step=0.5,
                                key=f"final_{token}_{number}_{maximum:g}")
        errors = c3.text_input("Hata türleri (virgülle ayırın)",
                               value=", ".join(q.get("ogretmen_hatalari", q.get("hatalar", []))),
                               key=f"errors_{token}_{number}")
    return {**q, "maksimum_puan": maximum, "ai_puani": ai_score, "ogretmen_puani": final,
            "ogretmen_hatalari": [x.strip() for x in errors.split(",") if x.strip()]}


def _inceleme(owner_id, exam, result, siradaki_id):
    """Bir sonucun öğretmen kontrol ekranı."""
    token = f"{result['id']}_{result['updated_at']}"
    pages = sayfa_gorsellerini_getir(owner_id, result["id"])
    sablon_var = bool(exam["questions"])
    if result["approved"]:
        st.info("Onaylanmış bir sonucu düzenliyorsunuz. Değişiklikler “Onayla ve kaydet” ile geçerli olur.")
    for warning in result.get("warnings", []):
        st.warning(warning)
    if not sablon_var:
        st.info("Bu sınavın soru şablonu yok. Soruların tam puanlarını burada düzeltebilirsiniz; onayladığınızda bu yapı "
                "sınavın şablonu olur ve sonraki kâğıtlar aynı sorularla değerlendirilir.")

    status_items = []
    for q in result["scores"]:
        score = float(q.get("ogretmen_puani", q.get("verilen_puan", 0)) or 0)
        maximum = float(q.get("maksimum_puan", 0) or 0)
        errors = q.get("ogretmen_hatalari", q.get("hatalar", []))
        correct = score >= maximum and not errors
        partial = score > 0 and not correct
        symbol = "✓" if correct else ("×" if score <= 0 else "•")
        color = "#167653" if correct else ("#c77700" if partial else "#c43d3d")
        bg = "#e6f4ee" if correct else ("#fff2d9" if partial else "#fdecec")
        status_items.append(
            f"<span style='display:inline-flex;align-items:center;gap:6px;margin:0 8px 8px 0;"
            f"padding:5px 9px;border-radius:999px;background:{bg};color:{color};font-size:0.9rem'>"
            f"Soru {escape(str(q['soru_no']))} <b style='font-size:1rem'>{symbol}</b></span>"
        )
    st.markdown("**Soru durumları**", unsafe_allow_html=True)
    st.markdown("".join(status_items), unsafe_allow_html=True)

    st.markdown("**Öğrenci kâğıdı**")
    if not pages:
        st.caption("Bu sonuç için kayıtlı kâğıt görseli yok.")
    for number, image_bytes in enumerate(pages, start=1):
        st.image(image_bytes, caption=f"Sayfa {number}", use_container_width=True)

    st.divider()
    st.markdown("**Sorular ve AI değerlendirmesi**")
    reviewed = [_soru_karti(q, token) for q in result["scores"]]

    earned, maximum = puan_ozeti(reviewed)
    exam_total = float(exam["total_points"])
    points_match = abs(maximum - exam_total) <= 0.001
    if not points_match:
        st.warning(f"Soru puanları toplamı {maximum:g}; sınav toplamı {exam_total:g}. "
                   "Onaylayabilmek için soruların “Tam puan” değerlerini sınav toplamına eşitleyin.")
    with kart():
        total, b1, b2, b3 = st.columns([1.6, 1.6, 1, 1], vertical_alignment="center")
        total.markdown(f"<div class='row-meta'>Toplam puan</div><div style='font-size:1.5rem;font-weight:700'>"
                       f"{earned:g} / {maximum:g}</div>", unsafe_allow_html=True)
        if b1.button("Onayla ve kaydet", icon=":material/check:", type="primary", use_container_width=True,
                     disabled=not points_match, key=f"approve_{token}"):
            sinav_sorulari_kaydet(owner_id, exam["id"], sablon_olustur(reviewed))
            sonuc_kaydet(owner_id, exam["id"], result["student_id"], result["student_name"], reviewed,
                         approved=True, warnings=[])
            ogrenci_ekle(owner_id, exam["course"], exam["class_name"], result["student_id"], result["student_name"])
            bildir("Düzeltilen tam puanlar bu sınavın şablonuna kaydedildi.", "info")
            bildir(f"{result['student_name'] or result['student_id']}: {earned:g} / {maximum:g} onaylandı.")
            st.session_state.pop("review_edit_id", None)
            st.session_state["review_result_id"] = siradaki_id
            if siradaki_id is None:
                st.session_state["grade_view_pending"] = "Kâğıt yükle"
            st.rerun()
        if b2.button("Sonraki", icon=":material/arrow_forward:", use_container_width=True, key=f"skip_{token}",
                     disabled=siradaki_id is None):
            st.session_state["review_result_id"] = siradaki_id
            st.rerun()
        with b3.popover("Sil", icon=":material/delete:", use_container_width=True):
            st.write("Bu öğrencinin sonucu ve kâğıt görselleri kalıcı olarak silinir.")
            if st.button("Evet, sil", key=f"delete_{token}"):
                sonuc_sil(owner_id, result["id"])
                bildir("Sonuç silindi.", "info")
                st.session_state.pop("review_edit_id", None)
                st.session_state["review_result_id"] = siradaki_id
                st.rerun()


def goster(user):
    owner_id = user["id"]
    sayfa_basligi("Kâğıt değerlendir", "Önce sınavı seçin, sonra öğrenci kâğıtlarını yükleyin veya sonuçları onaylayın.")
    exams = sinavlari_getir(owner_id)
    if not exams:
        if bos_durum("＋", "Önce bir sınav ekleyin", "Kâğıt değerlendirmek için bir sınava ihtiyacınız var. "
                     "Sınavı ekledikten sonra öğrenci kâğıtlarını buradan yükleyebilirsiniz.",
                     eylem="Sınav ekle", key="bos_degerlendir"):
            git("Sınavlar", sinav_ekle_ac=True)
        return
    if not api_anahtari_var_mi():
        st.error("Değerlendirme servisi bağlı değil: Claude API anahtarı tanımlanmamış. Ayrıntı için “Ayarlar” sayfasına bakın.")

    by_id = {e["id"]: e for e in exams}
    preferred = st.session_state.pop("grade_exam_id", None)
    if preferred in by_id:
        st.session_state["grade_exam"] = preferred
    if "grade_view_pending" in st.session_state:
        st.session_state["grade_view"] = st.session_state.pop("grade_view_pending")

    exam_id = kalici_secim(
        st.selectbox, "İşlem yapılacak sınav", list(by_id), "grade_exam",
        format_func=lambda i: (f"{by_id[i]['name']} · {by_id[i]['course']} · {by_id[i]['class_name']} · "
                               f"{by_id[i]['exam_type']}"))
    exam = by_id[exam_id]
    st.markdown(f"### {exam['name']}")
    st.caption(f"{exam['course']} · {exam['class_name']} · {exam['exam_type']} · "
               f"{float(exam['total_points']):g} puan")
    roster = ogrencileri_getir(owner_id, exam["course"], exam["class_name"])
    preferred_student_id = st.session_state.pop("grade_student_id", None)
    preferred_student = next((student for student in roster
                              if student["student_id"] == preferred_student_id), None)
    if preferred_student is not None:
        st.session_state[f"student_{exam_id}"] = preferred_student
        st.session_state[f"upload_mode_{exam_id}"] = "Tek öğrenci"
    approved = sonuclari_getir(owner_id, exam_id=exam_id)
    drafts = sonuclari_getir(owner_id, exam_id=exam_id, approved=False)
    existing = {r["student_id"] for r in approved + drafts}

    done_text = f"{len(approved)} / {len(roster)}" if roster else str(len(approved))
    template_text = f"{len(exam['questions'])} soru" if exam["questions"] else "henüz yok"
    st.markdown(f"<div class='info-strip'><span>Onaylanan kâğıt <b>{done_text}</b></span>"
                f"<span>Onay bekleyen <b>{len(drafts)}</b></span><span>Soru şablonu <b>{template_text}</b></span>"
                f"<span>Toplam puan <b>{float(exam['total_points']):g}</b></span></div>", unsafe_allow_html=True)
    st.write("")

    view = kalici_secim(st.segmented_control, "Görünüm", _GORUNUMLER, "grade_view", label_visibility="collapsed",
                        format_func=lambda v: f"{v} ({len(drafts)})" if v == "Onay bekleyenler" and drafts else v)

    if view == "Kâğıt yükle":
        if not exam["questions"]:
            st.info("Bu sınavın soru şablonu yok. İlk kâğıtta sorular ve puanlar kâğıttan okunur; o kâğıdı onayladığınızda "
                    "şablon oluşur. Toplu yüklemeden önce bir kâğıdı onaylamanız veya sınava cevap anahtarı eklemeniz önerilir.")
        with kart():
            mode = st.radio("Yükleme biçimi", ["Tek öğrenci", "Toplu (her dosya bir öğrenci)"], horizontal=True,
                            key=f"upload_mode_{exam_id}")
            if mode == "Tek öğrenci":
                _tek_ogrenci(owner_id, exam, roster, existing)
            else:
                _toplu(owner_id, exam, roster, existing)
        return

    # Onay bekleyenler: taslaklar ve (Analizler'den "düzenle" ile açılmış) onaylı sonuç
    queue = list(drafts)
    edit_id = st.session_state.get("review_edit_id")
    if edit_id:
        editing = sonuc_getir(owner_id, edit_id)
        if editing is not None and editing["exam_id"] == exam_id and editing["approved"]:
            queue.insert(0, editing)
        else:
            st.session_state.pop("review_edit_id", None)
    target = st.session_state.pop("review_result_id", None)
    if not queue:
        if bos_durum("✓", "Onay bekleyen kâğıt yok", "Bu sınavda değerlendirilip onayınızı bekleyen kâğıt bulunmuyor.",
                     eylem="Kâğıt yükle", key="bos_onay", eylem_ikon=":material/upload:"):
            st.session_state["grade_view_pending"] = "Kâğıt yükle"
            st.rerun()
        return
    by_result = {r["id"]: r for r in queue}
    ids = list(by_result)
    if target in by_result:
        st.session_state["review_pick"] = target
    elif st.session_state.get("review_pick") not in by_result:
        st.session_state["review_pick"] = ids[0]
    picked = st.selectbox(
        "Öğrenci", ids, key="review_pick",
        format_func=lambda i: f"{by_result[i]['student_name'] or by_result[i]['student_id']} · {by_result[i]['student_id']}"
                              + ("  (onaylı, düzenleniyor)" if by_result[i]["approved"] else ""))
    position = ids.index(picked)
    next_draft = next((i for i in ids[position + 1:] + ids[:position] if not by_result[i]["approved"]), None)
    _inceleme(owner_id, exam, by_result[picked], next_draft)
