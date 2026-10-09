"""Genel Bakış: başlangıç adımları, yapılacaklar, özet ve son sınavlar."""

import altair as alt
import pandas as pd
import streamlit as st

from data_handler import siniflari_getir, sinavlari_getir, sonuclari_getir
from degerlendirme import puan_ozeti, yuzde
from ui.ortak import kart, git, rozet, satir_metni, sayfa_basligi, yerel_tarih

_ADIMLAR = [
    ("Sınıfınızı ekleyin", "Dersinizi, sınıfınızı ve öğrenci listenizi girin.", "Sınıflara git", "Sınıflar"),
    ("Sınav ekleyin", "Sınavın adını girin; isterseniz cevap anahtarını yükleyin.", "Sınavlara git", "Sınavlar"),
    ("Kâğıtları değerlendirin", "Kâğıtları yükleyin, puan önerilerini kontrol edip onaylayın.", "Değerlendirmeye git",
     "Kâğıt Değerlendir"),
]


def _baslangic_adimlari(done_flags):
    """İlk kullanımda ne yapılacağını sırayla gösteren üç adım."""
    st.subheader("Başlarken")
    current = next((i for i, done in enumerate(done_flags) if not done), len(done_flags))
    for index, (column, (title, text, label, target)) in enumerate(zip(st.columns(3), _ADIMLAR)):
        with column, kart():
            done = done_flags[index]
            st.markdown(f"<div class='step-no {'done' if done else ''}'>{'✓' if done else index + 1}</div>"
                        f"<div class='step-title'>{title}</div><div class='step-text'>{text}</div>", unsafe_allow_html=True)
            if st.button(label, key=f"adim_{index}", use_container_width=True,
                         type="primary" if index == current else "secondary", disabled=index > current):
                git(target)


def goster(user):
    owner_id = user["id"]
    exams = sinavlari_getir(owner_id)
    classes = siniflari_getir(owner_id)
    approved = sonuclari_getir(owner_id, sirala="tarih")
    drafts = sonuclari_getir(owner_id, approved=False)

    add_exam, _ = sayfa_basligi(f"Merhaba, {user['display_name'].split()[0]}", "Sınıflarınızın ve sınavlarınızın özeti.",
                                eylem="Sınav ekle" if classes else None)
    if add_exam:
        git("Sınavlar", sinav_ekle_ac=True)

    done_flags = [bool(classes), bool(exams), bool(approved)]
    if not all(done_flags):
        _baslangic_adimlari(done_flags)
        if not exams:
            return
        st.write("")

    if drafts:
        with kart():
            left, right = st.columns([4, 1.3], vertical_alignment="center")
            left.markdown(f"**{len(drafts)} kâğıt onayınızı bekliyor.**  \nPuan önerileri hazır; kontrol edip onayladığınızda "
                          "sonuçlara eklenir.")
            if right.button("Kâğıtları incele", type="primary", use_container_width=True, icon=":material/fact_check:"):
                git("Kâğıt Değerlendir", grade_exam_id=drafts[0]["exam_id"], grade_view_pending="Onay bekleyenler")

    percentages = [p for p in (yuzde(r["scores"]) for r in approved) if p is not None]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sınıf", len(classes))
    m2.metric("Sınav", len(exams))
    m3.metric("Onaylanan kâğıt", len(approved))
    m4.metric("Genel ortalama", f"%{sum(percentages) / len(percentages):.0f}" if percentages else "—")

    st.write("")
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        st.subheader("Son sınavlar")
        roster_size = {(c["course"], c["class_name"]): c["ogrenci_sayisi"] for c in classes}
        for exam in exams[:4]:
            done = sum(1 for r in approved if r["exam_id"] == exam["id"])
            waiting = sum(1 for r in drafts if r["exam_id"] == exam["id"])
            size = roster_size.get((exam["course"], exam["class_name"]), 0)
            badges = rozet(f"{done} / {size} onaylı" if size else f"{done} onaylı")
            if waiting:
                badges += rozet(f"{waiting} onay bekliyor", "warn")
            with kart():
                info, action = st.columns([3.2, 1.2], vertical_alignment="center")
                with info:
                    satir_metni(exam["name"], f"{exam['course']} · {exam['class_name']} · {exam['exam_type']}", badges,
                                oran=done / size if size else None)
                if action.button("Değerlendir", key=f"ozet_sinav_{exam['id']}", use_container_width=True):
                    git("Kâğıt Değerlendir", grade_exam_id=exam["id"],
                        **({"grade_view_pending": "Onay bekleyenler"} if waiting else {}))
        if len(exams) > 4:
            if st.button(f"Tüm sınavları gör ({len(exams)})", type="tertiary", icon=":material/arrow_forward:"):
                git("Sınavlar")

    with right:
        st.subheader("Son onaylanan kâğıtlar")
        if approved:
            rows = []
            for result in approved[:6]:
                earned, maximum = puan_ozeti(result["scores"])
                moment = yerel_tarih(result["updated_at"])
                rows.append({"Öğrenci": result["student_name"] or result["student_id"], "Sınav": result["exam_name"],
                             "Puan": f"{earned:g} / {maximum:g}", "Tarih": moment.strftime("%d.%m %H:%M") if moment else ""})
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            if st.button("Sonuçları incele", type="tertiary", icon=":material/arrow_forward:"):
                git("Analizler")
        else:
            st.caption("Henüz onaylanan kâğıt yok.")

    chart_rows = [{"Sınav": r["exam_name"], "Sınıf": f"{r['course']} · {r['class_name']}", "Tarih": r["exam_created_at"],
                   "Ortalama (%)": yuzde(r["scores"])} for r in approved]
    chart_rows = [row for row in chart_rows if row["Ortalama (%)"] is not None]
    if chart_rows:
        st.write("")
        st.subheader("Sınav ortalamaları")
        data = (pd.DataFrame(chart_rows).groupby(["Sınav", "Sınıf", "Tarih"], as_index=False)["Ortalama (%)"]
                .mean().sort_values("Tarih"))
        many_classes = data["Sınıf"].nunique() > 1
        with kart():
            st.altair_chart(alt.Chart(data).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=42).encode(
                x=alt.X("Sınav:N", sort=None, axis=alt.Axis(labelAngle=0, title=None)), xOffset="Sınıf:N",
                y=alt.Y("Ortalama (%):Q", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("Sınıf:N", legend=alt.Legend(orient="bottom", title=None) if many_classes else None,
                                scale=alt.Scale(range=["#17604f", "#c58a1b", "#3b6fb6", "#8a5fa8", "#b5564e"])),
                tooltip=["Sınav", "Sınıf", alt.Tooltip("Ortalama (%):Q", format=".1f")],
            ).properties(height=230), use_container_width=True)
