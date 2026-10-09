"""Analizler: sınav sonuçları, soru ve hata analizi, öğrenci gelişimi, dışa aktarma."""

from collections import Counter
from io import BytesIO

import altair as alt
import pandas as pd
import streamlit as st

from data_handler import (
    ogrencileri_getir,
    sayfa_gorsellerini_getir,
    siniflari_getir,
    sinavlari_getir,
    sonuc_sil,
    sonuclari_getir,
    soru_istatistikleri,
)
from degerlendirme import puan_ozeti, son_puan, yuzde
from gorsel import sayfayi_isaretle
from ui.ortak import bildir, bos_durum, git, kalici_secim, sayfa_basligi, sinav_etiketi, sinif_etiketi

_MOR, _YESIL, _MERCAN = "#17604f", "#c58a1b", "#b5564e"


def _sonuc_tablosu(results):
    """Öğrenci başına bir satır: toplam, yüzde ve soru soru puanlar."""
    rows = []
    for result in results:
        earned, maximum = puan_ozeti(result["scores"])
        row = {"Öğrenci no": result["student_id"], "Öğrenci": result["student_name"],
               "Toplam": earned, "Maksimum": maximum, "Yüzde": round(100 * earned / maximum, 1) if maximum else None}
        for q in sorted(result["scores"], key=lambda q: int(q["soru_no"])):
            row[f"S{q['soru_no']}"] = son_puan(q)
        rows.append(row)
    return pd.DataFrame(rows)


def _excel(table, stats):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Notlar", index=False)
        if not stats.empty:
            stats.to_excel(writer, sheet_name="Soru analizi", index=False)
    return buffer.getvalue()


def _sinav_analizi(owner_id, exams):
    by_id = {e["id"]: e for e in exams}
    exam_id = kalici_secim(st.selectbox, "Sınav", list(by_id), "analysis_exam", format_func=lambda i: sinav_etiketi(by_id[i]))
    exam = by_id[exam_id]
    results = sonuclari_getir(owner_id, exam_id=exam_id)
    drafts = sonuclari_getir(owner_id, exam_id=exam_id, approved=False)
    roster = ogrencileri_getir(owner_id, exam["course"], exam["class_name"])
    if drafts:
        st.warning(f"{len(drafts)} kâğıt onay bekliyor; onaylanana kadar buradaki sonuçlara eklenmez.")
    if not results:
        if bos_durum("✓", "Bu sınavda onaylanmış kâğıt yok", "Kâğıtları yükleyip onayladığınızda notlar ve soru "
                     "analizi burada görünür.", eylem="Kâğıt değerlendir", key="bos_analiz_sinav",
                     eylem_ikon=":material/fact_check:"):
            git("Kâğıt Değerlendir", grade_exam_id=exam_id)
        return

    table = _sonuc_tablosu(results)
    percents = table["Yüzde"].dropna()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Onaylı kâğıt", f"{len(results)} / {len(roster)}" if roster else len(results))
    m2.metric("Sınıf ortalaması", f"%{percents.mean():.1f}" if len(percents) else "—")
    m3.metric("En yüksek", f"%{percents.max():.1f}" if len(percents) else "—")
    m4.metric("En düşük", f"%{percents.min():.1f}" if len(percents) else "—")

    graded_ids = {r["student_id"] for r in results} | {r["student_id"] for r in drafts}
    missing = [s for s in roster if s["student_id"] not in graded_ids]
    if missing:
        with st.expander(f"Kâğıdı girilmemiş {len(missing)} öğrenci"):
            st.write(", ".join(f"{s['name']} ({s['student_id']})" for s in missing))

    # Sınıf karşılaştırması: aynı ders + sınav adı + aynı soru şablonu
    same = [e for e in exams if e["name"].casefold() == exam["name"].casefold()
            and e["course"].casefold() == exam["course"].casefold() and e["questions"] == exam["questions"]]
    class_exam_ids = {}
    for e in same:
        class_exam_ids.setdefault(e["class_name"], []).append(e["id"])
    chosen = [exam["class_name"]]
    if len(class_exam_ids) > 1:
        chosen = st.multiselect("Soru analizinde karşılaştırılacak sınıflar", list(class_exam_ids),
                                default=[exam["class_name"]], key=f"compare_{exam_id}")
    stats = pd.DataFrame(soru_istatistikleri(owner_id, [i for name in chosen for i in class_exam_ids[name]]))
    stats_table = stats.rename(columns={
        "sinif": "Sınıf", "soru_no": "Soru", "ogrenci_sayisi": "Öğrenci sayısı", "hata_yapan": "Tam puan alamayan",
        "hata_yuzdesi": "Hata oranı (%)", "basari_yuzdesi": "Ortalama başarı (%)",
        "ai_ogretmen_tam_uyum_yuzdesi": "Öneriyle aynı puan (%)"})

    tab_notes, tab_questions, tab_errors, tab_papers = st.tabs(["Notlar", "Soru analizi", "Hata türleri", "Kâğıtlar"])

    with tab_notes:
        st.dataframe(table, hide_index=True, use_container_width=True)
        file_stem = f"{exam['name']}_{exam['class_name']}".replace(" ", "_").replace("/", "-")
        d1, d2, _ = st.columns([1, 1, 3])
        d1.download_button("Excel indir", icon=":material/download:", data=_excel(table, stats_table), file_name=f"{file_stem}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        d2.download_button("CSV indir", icon=":material/download:", data=table.to_csv(index=False).encode("utf-8-sig"), file_name=f"{file_stem}.csv",
                           mime="text/csv", use_container_width=True)
        if len(percents) > 1:
            st.markdown("**Not dağılımı**")
            bins = pd.cut(percents, bins=[0, 25, 45, 55, 70, 85, 100], include_lowest=True,
                          labels=["0–25", "25–45", "45–55", "55–70", "70–85", "85–100"])
            dist = bins.value_counts(sort=False).rename_axis("Başarı aralığı (%)").reset_index(name="Öğrenci")
            st.altair_chart(alt.Chart(dist).mark_bar(color=_MOR, cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
                x=alt.X("Başarı aralığı (%):N", sort=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Öğrenci:Q", axis=alt.Axis(tickMinStep=1)), tooltip=["Başarı aralığı (%)", "Öğrenci"],
            ).properties(height=220), use_container_width=True)

    with tab_questions:
        if stats.empty:
            st.info("Seçilen sınıflarda henüz onaylı sonuç yok.")
        else:
            st.caption("Ortalama başarı: soruda alınan puanın alınabilecek puana oranı. Hata oranı: tam puan alamayan "
                       "öğrencilerin oranı. Öneriyle aynı puan: önerilen puanı değiştirmeden onayladığınız kâğıtların oranı.")
            chart_data = stats_table.dropna(subset=["Ortalama başarı (%)"])
            st.altair_chart(alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
                x=alt.X("Soru:O", axis=alt.Axis(labelAngle=0)), xOffset="Sınıf:N",
                y=alt.Y("Ortalama başarı (%):Q", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("Sınıf:N", legend=alt.Legend(orient="bottom", title=None) if len(chosen) > 1 else None,
                                scale=alt.Scale(range=[_MOR, _YESIL, _MERCAN, "#e0b252", "#5b9bd5"])),
                tooltip=["Sınıf", "Soru", "Ortalama başarı (%)", "Hata oranı (%)"],
            ).properties(height=240), use_container_width=True)
            st.dataframe(stats_table, hide_index=True, use_container_width=True)
            if exam["questions"]:
                with st.expander("Soru şablonu"):
                    st.dataframe(pd.DataFrame(exam["questions"]).rename(columns={
                        "soru_no": "Soru", "soru_ozeti": "Soru özeti", "maksimum_puan": "Puan",
                        "dogru_cevap": "Doğru cevap"}), hide_index=True, use_container_width=True)

    with tab_errors:
        counter = Counter()
        per_question = Counter()
        for result in results:
            for q in result["scores"]:
                for tag in q.get("ogretmen_hatalari", q.get("hatalar", [])):
                    counter[tag.strip().casefold()] += 1
                    per_question[(tag.strip().casefold(), int(q["soru_no"]))] += 1
        if not counter:
            st.info("Onaylı kâğıtlarda hata etiketi yok.")
        else:
            st.caption("Onaylı kâğıtlardaki hata etiketlerinin kaç kez görüldüğü. Sınıfın genel eksiklerini gösterir.")
            tags = pd.DataFrame(counter.most_common(15), columns=["Hata türü", "Adet"])
            st.altair_chart(alt.Chart(tags).mark_bar(color=_MERCAN, cornerRadiusTopRight=6, cornerRadiusBottomRight=6).encode(
                y=alt.Y("Hata türü:N", sort="-x", title=None), x=alt.X("Adet:Q", axis=alt.Axis(tickMinStep=1)),
                tooltip=["Hata türü", "Adet"]).properties(height=max(120, 32 * len(tags))), use_container_width=True)
            detail = pd.DataFrame([{"Hata türü": tag, "Soru": qno, "Adet": n} for (tag, qno), n in per_question.items()])
            st.dataframe(detail.pivot_table(index="Hata türü", columns="Soru", values="Adet", fill_value=0, aggfunc="sum"),
                         use_container_width=True)

    with tab_papers:
        by_result = {r["id"]: r for r in results}
        result_id = st.selectbox("Öğrenci", list(by_result), key=f"paper_pick_{exam_id}",
                                 format_func=lambda i: f"{by_result[i]['student_name'] or by_result[i]['student_id']} · {by_result[i]['student_id']}")
        result = by_result[result_id]
        earned, maximum = puan_ozeti(result["scores"])
        c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="center")
        c1.markdown(f"**Toplam: {earned:g} / {maximum:g}**")
        if c2.button("Puanları düzenle", icon=":material/edit:", use_container_width=True, key=f"edit_{result_id}"):
            git("Kâğıt Değerlendir", grade_exam_id=exam_id, grade_view="Onay bekleyenler",
                review_edit_id=result_id, review_result_id=result_id)
        with c3.popover("Sonucu sil", icon=":material/delete:", use_container_width=True):
            st.write("Bu öğrencinin sonucu ve kâğıt görselleri kalıcı olarak silinir.")
            if st.button("Evet, sil", key=f"del_{result_id}"):
                sonuc_sil(owner_id, result_id)
                bildir("Sonuç silindi.", "info")
                st.rerun()
        st.dataframe(pd.DataFrame([{
            "Soru": q["soru_no"], "Önerilen puan": q.get("ai_puani"), "Verilen puan": son_puan(q),
            "Maksimum": q["maksimum_puan"], "Hatalar": ", ".join(q.get("ogretmen_hatalari", q.get("hatalar", []))),
            "Öğrenci cevabı": q.get("ogrenci_cevabi", ""), "Gerekçe": q.get("gerekce", "")} for q in result["scores"]]),
            hide_index=True, use_container_width=True)
        pages = sayfa_gorsellerini_getir(owner_id, result_id)
        columns = st.columns(2)
        for number, image_bytes in enumerate(pages, start=1):
            columns[(number - 1) % len(columns)].image(sayfayi_isaretle(image_bytes, result["scores"], number),
                                                       caption=f"Sayfa {number}", use_container_width=True)


def _ogrenci_gelisimi(owner_id):
    classes = siniflari_getir(owner_id)
    if not classes:
        st.info("Henüz sınıf yok.")
        return
    by_id = {c["id"]: c for c in classes}
    class_id = kalici_secim(st.selectbox, "Sınıf", list(by_id), "progress_class", format_func=lambda i: sinif_etiketi(by_id[i]))
    selected = by_id[class_id]
    results = [r for r in sonuclari_getir(owner_id)
               if r["course"] == selected["course"] and r["class_name"] == selected["class_name"]]
    if not results:
        st.info("Bu sınıfta henüz onaylı sonuç yok.")
        return
    rows = [{"Öğrenci no": r["student_id"], "Öğrenci": r["student_name"] or r["student_id"], "Sınav": r["exam_name"],
             "Tarih": r["exam_created_at"], "Başarı (%)": round(yuzde(r["scores"]), 1)}
            for r in results if yuzde(r["scores"]) is not None]
    data = pd.DataFrame(rows).sort_values("Tarih")
    exam_order = list(dict.fromkeys(data["Sınav"]))

    st.markdown("**Sınıf özeti**")
    pivot = data.pivot_table(index=["Öğrenci no", "Öğrenci"], columns="Sınav", values="Başarı (%)", aggfunc="mean")
    pivot = pivot.reindex(columns=exam_order)
    pivot["Ortalama"] = pivot.mean(axis=1).round(1)
    st.dataframe(pivot.reset_index(), hide_index=True, use_container_width=True)

    students = dict(zip(data["Öğrenci no"], data["Öğrenci"]))
    student_id = st.selectbox("Öğrenci", list(students), format_func=lambda i: f"{students[i]} · {i}", key=f"progress_student_{class_id}")
    own = data[data["Öğrenci no"] == student_id].assign(Seri=students[student_id])
    avg = data.groupby("Sınav", as_index=False)["Başarı (%)"].mean().assign(Seri="Sınıf ortalaması")
    chart = alt.Chart(pd.concat([own[["Sınav", "Başarı (%)", "Seri"]], avg])).mark_line(
        point=alt.OverlayMarkDef(filled=True, size=80), strokeWidth=3).encode(
        x=alt.X("Sınav:N", sort=exam_order, axis=alt.Axis(labelAngle=0, title=None)),
        y=alt.Y("Başarı (%):Q", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("Seri:N", legend=alt.Legend(orient="bottom", title=None),
                        scale=alt.Scale(domain=[students[student_id], "Sınıf ortalaması"], range=[_MOR, "#b8bfc6"])),
        tooltip=["Seri", "Sınav", alt.Tooltip("Başarı (%):Q", format=".1f")]).properties(height=260)
    st.altair_chart(chart, use_container_width=True)


def goster(user):
    owner_id = user["id"]
    sayfa_basligi("Analizler", "Notları, soruların başarı durumunu ve öğrenci gelişimini inceleyin.")
    exams = sinavlari_getir(owner_id)
    if not exams:
        if bos_durum("＋", "Henüz incelenecek sonuç yok", "Bir sınav ekleyip öğrenci kâğıtlarını onayladığınızda notlar "
                     "ve analizler burada görünür.", eylem="Sınav ekle", key="bos_analiz"):
            git("Sınavlar", sinav_ekle_ac=True)
        return
    tab_exam, tab_progress = st.tabs(["Sınav analizi", "Öğrenci gelişimi"])
    with tab_exam:
        _sinav_analizi(owner_id, exams)
    with tab_progress:
        _ogrenci_gelisimi(owner_id)
