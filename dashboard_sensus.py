# -*- coding: utf-8 -*-
"""
Dashboard Streamlit: Sentimen Masyarakat terhadap Sensus Ekonomi 2026
Sumber data: komentar YouTube, Instagram, dan X (hasil label_indobert.py)

Jalankan:
    pip install streamlit pandas plotly
    streamlit run app.py
"""

import io
import os
import re
from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st

# ----------------------------------------------------------------------------
# Konfigurasi
# ----------------------------------------------------------------------------
DEFAULT_CSV = "dataset_labeled_indobert.csv"

st.set_page_config(
    page_title="Sentimen Sensus Ekonomi 2026",
    page_icon="📊",
    layout="wide",
)

URUTAN = ["positif", "netral", "negatif"]
WARNA = {"positif": "#2e9e6b", "netral": "#8a94a6", "negatif": "#d9534f"}

PETA_SENTIMEN = {
    "positive": "positif", "negative": "negatif", "neutral": "netral",
    "pos": "positif", "neg": "negatif", "neu": "netral",
    "positif": "positif", "negatif": "negatif", "netral": "netral",
}

STOPWORD = set("""
yang dan di ke dari ini itu untuk dengan pada adalah juga atau tidak ada akan
sudah saya aku kita kami kamu anda dia mereka nya lah kah pun sih deh dong ya
yg dgn utk tdk gak ga nggak ngga enggak aja saja udah udh sdh bisa bs mau jadi
jd karena krn tapi tp kalau kalo kl jika agar supaya sebagai oleh dalam lebih
sangat banget bgt lagi lg masih mah nih tuh si para sama sm mohon harus hrs
apa siapa kapan dimana bagaimana kenapa gimana kok kan lho loh yaa ye yah
sensus ekonomi bps https http www com rt amp
""".split())

KANDIDAT = {
    "teks": ["teks", "text", "komentar", "comment", "full_text", "content", "isi"],
    "teks_bersih": ["teks_bersih", "teks_tanpa_stem", "clean_text", "teks_clean"],
    "sentimen": ["sentimen", "sentiment", "label"],
    "skor": ["skor_confidence", "confidence", "score", "skor"],
    "platform": ["platform", "sumber", "source", "media", "channel"],
    "tanggal": ["tanggal", "date", "created_at", "timestamp", "waktu", "published_at", "datetime"],
}


# ----------------------------------------------------------------------------
# Fungsi bantu
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner="Membaca data ...")
def baca_csv(data: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")


def tebak_kolom(df: pd.DataFrame, kunci: str):
    huruf_kecil = {c.lower(): c for c in df.columns}
    for k in KANDIDAT[kunci]:
        if k in huruf_kecil:
            return huruf_kecil[k]
    return None


def pilih_kolom(label, df, kunci, wajib=False):
    opsi = list(df.columns) if wajib else ["(tidak ada)"] + list(df.columns)
    tebakan = tebak_kolom(df, kunci)
    idx = opsi.index(tebakan) if tebakan in opsi else 0
    hasil = st.sidebar.selectbox(label, opsi, index=idx, key=f"kol_{kunci}")
    return None if hasil == "(tidak ada)" else hasil


def normalisasi_platform(nilai):
    if pd.isna(nilai):
        return "Lainnya"
    s = str(nilai).strip().lower()
    if "youtube" in s or s in ("yt", "ytb"):
        return "YouTube"
    if "insta" in s or s == "ig":
        return "Instagram"
    if "twitter" in s or s in ("x", "x.com", "tweet"):
        return "X"
    return str(nilai).strip()


def top_kata(seri_teks, n=15):
    hitung = Counter()
    for t in seri_teks.dropna().astype(str):
        for w in re.findall(r"[a-z]{3,}", t.lower()):
            if w not in STOPWORD:
                hitung[w] += 1
    return pd.DataFrame(hitung.most_common(n), columns=["kata", "frekuensi"])


def persen(x, total):
    return f"{(x / total * 100):.1f}%" if total else "0%"


# ----------------------------------------------------------------------------
# Sidebar: sumber data
# ----------------------------------------------------------------------------
st.sidebar.title("⚙️ Pengaturan")
upload = st.sidebar.file_uploader("Unggah CSV hasil pelabelan", type="csv")

if upload is not None:
    df_mentah = baca_csv(upload.getvalue())
elif os.path.exists(DEFAULT_CSV):
    with open(DEFAULT_CSV, "rb") as f:
        df_mentah = baca_csv(f.read())
    st.sidebar.caption(f"Memakai file lokal: `{DEFAULT_CSV}`")
else:
    st.title("📊 Dashboard Sentimen Sensus Ekonomi 2026")
    st.info(
        f"Letakkan `{DEFAULT_CSV}` di folder yang sama dengan `app.py`, "
        "atau unggah file CSV lewat sidebar."
    )
    st.stop()

st.sidebar.markdown("**Pemetaan kolom**")
kol_sent = pilih_kolom("Kolom sentimen", df_mentah, "sentimen", wajib=True)
kol_teks = pilih_kolom("Kolom teks asli", df_mentah, "teks")
kol_bersih = pilih_kolom("Kolom teks untuk analisis kata", df_mentah, "teks_bersih")
kol_skor = pilih_kolom("Kolom confidence", df_mentah, "skor")
kol_plat = pilih_kolom("Kolom platform", df_mentah, "platform")
kol_tgl = pilih_kolom("Kolom tanggal", df_mentah, "tanggal")

# ----------------------------------------------------------------------------
# Siapkan data
# ----------------------------------------------------------------------------
df = df_mentah.copy()
df["_sentimen"] = (
    df[kol_sent].astype(str).str.strip().str.lower().map(PETA_SENTIMEN).fillna("netral")
)
if kol_plat:
    df["_platform"] = df[kol_plat].map(normalisasi_platform)
if kol_tgl:
    df["_tanggal"] = pd.to_datetime(df[kol_tgl], errors="coerce", utc=True).dt.tz_localize(None)
if kol_skor:
    df["_skor"] = pd.to_numeric(df[kol_skor], errors="coerce")
kol_kata = kol_bersih or kol_teks

# ----------------------------------------------------------------------------
# Sidebar: filter
# ----------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("**Filter**")

if kol_plat:
    daftar_plat = sorted(df["_platform"].unique())
    pilih_plat = st.sidebar.multiselect("Platform", daftar_plat, default=daftar_plat)
    df = df[df["_platform"].isin(pilih_plat)]

pilih_sent = st.sidebar.multiselect("Sentimen", URUTAN, default=URUTAN)
df = df[df["_sentimen"].isin(pilih_sent)]

if kol_tgl and df["_tanggal"].notna().any():
    tmin, tmax = df["_tanggal"].min().date(), df["_tanggal"].max().date()
    if tmin < tmax:
        rentang = st.sidebar.date_input("Rentang tanggal", (tmin, tmax), min_value=tmin, max_value=tmax)
        if isinstance(rentang, tuple) and len(rentang) == 2:
            mulai, akhir = pd.Timestamp(rentang[0]), pd.Timestamp(rentang[1]) + pd.Timedelta(days=1)
            df = df[df["_tanggal"].isna() | ((df["_tanggal"] >= mulai) & (df["_tanggal"] < akhir))]

if kol_skor and df["_skor"].notna().any():
    min_skor = st.sidebar.slider("Confidence minimum", 0.0, 1.0, 0.0, 0.05)
    df = df[df["_skor"].fillna(1.0) >= min_skor]

# ----------------------------------------------------------------------------
# Header + KPI
# ----------------------------------------------------------------------------
st.title("📊 Sentimen Masyarakat terhadap Sensus Ekonomi 2026")
st.caption("Komentar dari YouTube, Instagram, dan X · dilabeli dengan model IndoBERT/RoBERTa Indonesia")

total = len(df)
if total == 0:
    st.warning("Tidak ada data yang cocok dengan filter saat ini.")
    st.stop()

n = df["_sentimen"].value_counts().reindex(URUTAN, fill_value=0)
indeks = (n["positif"] - n["negatif"]) / total * 100

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total komentar", f"{total:,}".replace(",", "."))
k2.metric("😊 Positif", f"{n['positif']:,}".replace(",", "."), persen(n["positif"], total))
k3.metric("😐 Netral", f"{n['netral']:,}".replace(",", "."), persen(n["netral"], total))
k4.metric("😠 Negatif", f"{n['negatif']:,}".replace(",", "."), persen(n["negatif"], total))
k5.metric(
    "Indeks sentimen",
    f"{indeks:+.1f}",
    help="(positif − negatif) / total × 100. Rentang −100 sampai +100.",
)

tab1, tab2, tab3, tab4 = st.tabs(["Ringkasan", "Tren waktu", "Kata dominan", "Data"])

# ----------------------------------------------------------------------------
# Tab 1: Ringkasan
# ----------------------------------------------------------------------------
with tab1:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Distribusi sentimen")
        d = n.reset_index()
        d.columns = ["sentimen", "jumlah"]
        fig = px.pie(
            d, names="sentimen", values="jumlah", hole=0.5,
            color="sentimen", color_discrete_map=WARNA,
            category_orders={"sentimen": URUTAN},
        )
        fig.update_traces(textinfo="percent+label", sort=False)
        fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        if kol_plat:
            st.subheader("Sentimen per platform")
            mode = st.radio("Tampilan", ["Persentase", "Jumlah"], horizontal=True, key="mode_plat")
            g = df.groupby(["_platform", "_sentimen"]).size().reset_index(name="jumlah")
            if mode == "Persentase":
                g["nilai"] = g["jumlah"] / g.groupby("_platform")["jumlah"].transform("sum") * 100
                sumbu = "Persentase (%)"
            else:
                g["nilai"] = g["jumlah"]
                sumbu = "Jumlah komentar"
            fig = px.bar(
                g, x="_platform", y="nilai", color="_sentimen",
                color_discrete_map=WARNA, category_orders={"_sentimen": URUTAN},
                labels={"_platform": "Platform", "nilai": sumbu, "_sentimen": "Sentimen"},
                barmode="stack", text_auto=".0f",
            )
            fig.update_layout(margin=dict(t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.subheader("Distribusi sentimen (bar)")
            fig = px.bar(
                d, x="sentimen", y="jumlah", color="sentimen",
                color_discrete_map=WARNA, category_orders={"sentimen": URUTAN}, text_auto=True,
            )
            fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Pilih kolom platform di sidebar untuk melihat perbandingan antar platform.")

    if kol_plat:
        st.subheader("Volume komentar per platform")
        v = df["_platform"].value_counts().reset_index()
        v.columns = ["platform", "jumlah"]
        fig = px.bar(v, x="jumlah", y="platform", orientation="h", text_auto=True)
        fig.update_layout(yaxis=dict(autorange="reversed"), margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    if kol_skor and df["_skor"].notna().any():
        st.subheader("Kepercayaan model (confidence)")
        c3, c4 = st.columns(2)
        with c3:
            fig = px.histogram(
                df, x="_skor", color="_sentimen", nbins=30,
                color_discrete_map=WARNA, category_orders={"_sentimen": URUTAN},
                labels={"_skor": "Skor confidence", "_sentimen": "Sentimen"},
                barmode="overlay", opacity=0.7,
            )
            fig.update_layout(margin=dict(t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        with c4:
            fig = px.box(
                df, x="_sentimen", y="_skor", color="_sentimen",
                color_discrete_map=WARNA, category_orders={"_sentimen": URUTAN},
                labels={"_skor": "Skor confidence", "_sentimen": "Sentimen"},
            )
            fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        rendah = (df["_skor"] < 0.6).mean() * 100
        st.caption(
            f"{rendah:.1f}% prediksi punya confidence di bawah 0,6 — label ini lebih rawan salah, "
            "pertimbangkan untuk dicek manual."
        )

# ----------------------------------------------------------------------------
# Tab 2: Tren waktu
# ----------------------------------------------------------------------------
with tab2:
    if not kol_tgl or df["_tanggal"].notna().sum() == 0:
        st.info(
            "Kolom tanggal belum dipilih atau tidak bisa dibaca. "
            "Pilih kolom tanggal di sidebar (bagian *Pemetaan kolom*) untuk melihat tren."
        )
    else:
        dt = df.dropna(subset=["_tanggal"])
        cA, cB = st.columns([1, 2])
        gran = cA.radio("Agregasi", ["Harian", "Mingguan", "Bulanan"], index=1, horizontal=True)
        tampil = cB.radio("Tampilkan", ["Jumlah komentar", "Indeks sentimen"], horizontal=True)
        freq = {"Harian": "D", "Mingguan": "W", "Bulanan": "MS"}[gran]

        pivot = (
            dt.groupby([pd.Grouper(key="_tanggal", freq=freq), "_sentimen"])
            .size().unstack(fill_value=0).reindex(columns=URUTAN, fill_value=0)
        )

        if tampil == "Jumlah komentar":
            long = pivot.reset_index().melt(id_vars="_tanggal", var_name="sentimen", value_name="jumlah")
            fig = px.line(
                long, x="_tanggal", y="jumlah", color="sentimen", markers=True,
                color_discrete_map=WARNA, category_orders={"sentimen": URUTAN},
                labels={"_tanggal": "Tanggal", "jumlah": "Jumlah komentar"},
            )
        else:
            tot = pivot.sum(axis=1).replace(0, pd.NA)
            idx = ((pivot["positif"] - pivot["negatif"]) / tot * 100).reset_index()
            idx.columns = ["_tanggal", "indeks"]
            fig = px.line(idx, x="_tanggal", y="indeks", markers=True,
                          labels={"_tanggal": "Tanggal", "indeks": "Indeks sentimen"})
            fig.add_hline(y=0, line_dash="dot", line_color="gray")
        fig.update_layout(margin=dict(t=10, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

        if kol_plat:
            st.subheader("Volume komentar per platform dari waktu ke waktu")
            vp = (
                dt.groupby([pd.Grouper(key="_tanggal", freq=freq), "_platform"])
                .size().reset_index(name="jumlah")
            )
            fig = px.area(vp, x="_tanggal", y="jumlah", color="_platform",
                          labels={"_tanggal": "Tanggal", "jumlah": "Jumlah", "_platform": "Platform"})
            fig.update_layout(margin=dict(t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)

        sisa = len(df) - len(dt)
        if sisa:
            st.caption(f"{sisa} baris tanpa tanggal valid tidak ikut dalam grafik tren.")

# ----------------------------------------------------------------------------
# Tab 3: Kata dominan
# ----------------------------------------------------------------------------
with tab3:
    if not kol_kata:
        st.info("Pilih kolom teks di sidebar untuk analisis kata.")
    else:
        top_n = st.slider("Jumlah kata teratas", 5, 30, 15)
        kolom = st.columns(3)
        for col, s in zip(kolom, URUTAN):
            with col:
                st.markdown(f"**{s.capitalize()}**")
                sub = df[df["_sentimen"] == s]
                if sub.empty:
                    st.caption("Tidak ada data.")
                    continue
                tk = top_kata(sub[kol_kata], top_n)
                fig = px.bar(tk, x="frekuensi", y="kata", orientation="h",
                             color_discrete_sequence=[WARNA[s]])
                fig.update_layout(
                    yaxis=dict(autorange="reversed"),
                    margin=dict(t=10, b=10, l=0, r=0), height=420,
                )
                st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"Dihitung dari kolom `{kol_kata}` dengan daftar stopword sederhana. "
            "Tambahkan kata ke `STOPWORD` di app.py kalau masih ada kata umum yang mengganggu."
        )

# ----------------------------------------------------------------------------
# Tab 4: Data
# ----------------------------------------------------------------------------
with tab4:
    cari = st.text_input("Cari kata dalam komentar")
    tampil_df = df
    if cari and kol_teks:
        tampil_df = df[df[kol_teks].astype(str).str.contains(cari, case=False, na=False, regex=False)]
        st.caption(f"{len(tampil_df)} komentar cocok.")

    if kol_skor and tampil_df["_skor"].notna().any():
        with st.expander("Komentar dengan confidence tertinggi per sentimen"):
            for s in URUTAN:
                sub = tampil_df[tampil_df["_sentimen"] == s].nlargest(5, "_skor")
                if sub.empty or not kol_teks:
                    continue
                st.markdown(f"**{s.capitalize()}**")
                for _, r in sub.iterrows():
                    st.write(f"- ({r['_skor']:.2f}) {str(r[kol_teks])[:300]}")

    kolom_tampil = [c for c in [kol_plat, kol_tgl, kol_teks, "_sentimen", kol_skor] if c]
    st.dataframe(
        tampil_df[kolom_tampil].rename(columns={"_sentimen": "sentimen (norm)"}),
        use_container_width=True, height=450,
    )
    st.download_button(
        "⬇️ Unduh data terfilter (CSV)",
        tampil_df.drop(columns=[c for c in tampil_df.columns if c.startswith("_")]).to_csv(index=False).encode("utf-8-sig"),
        file_name="sentimen_terfilter.csv",
        mime="text/csv",
    )