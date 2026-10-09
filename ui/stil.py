"""Uygulamanın ortak görsel stili.

Renkler ve köşe yarıçapı .streamlit/config.toml temasından gelir; burada
yalnızca tema ayarlarının yetmediği düzen ve bileşen stilleri bulunur.
"""

import streamlit as st

_CSS = """
<style>
:root { --ink:#1c2430; --muted:#667085; --line:#dfe3e8; --accent:#17604f; --accent-soft:#e7f1ee;
        --warn:#8a5a00; --warn-soft:#fdf3dc; --danger:#b3261e; --danger-soft:#fbe9e7; --surface:#ffffff; }
/* Simge fontunu ezmemek için yazı tipi yalnızca metin öğelerine uygulanır. */
html, body, .stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button p, .stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stMetricValue"] {
  font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.block-container { max-width:1180px; padding-top:2.2rem; padding-bottom:4rem; }
header[data-testid="stHeader"] { background:transparent; }
h1 { font-size:1.75rem !important; font-weight:700 !important; letter-spacing:-.02em; padding:0 !important; }
h2 { font-size:1.25rem !important; font-weight:650 !important; letter-spacing:-.01em; }
h3 { font-size:1.05rem !important; font-weight:650 !important; }

/* Kenar çubuğu */
section[data-testid="stSidebar"] { border-right:1px solid var(--line); }
[data-testid="stSidebarNav"] a { border-radius:8px; padding:.5rem .65rem; margin:1px 0; }
[data-testid="stSidebarNav"] a span { font-size:.95rem; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background:var(--accent-soft); }
[data-testid="stSidebarNav"] a[aria-current="page"] span { color:var(--accent); font-weight:650; }
[data-testid="stLogo"] { height:2.2rem; }
.side-user { margin-top:.5rem; padding:.75rem .1rem 0; border-top:1px solid var(--line); }
.side-user b { display:block; font-size:.9rem; color:var(--ink); }
.side-user span { font-size:.78rem; color:var(--muted); }

/* Kartlar */
[class*="st-key-kart-"] { background:var(--surface); }
div[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
div[data-testid="stMetricLabel"] p { color:var(--muted); font-size:.82rem; }
div[data-testid="stMetricValue"] { font-size:1.6rem; font-weight:700; }

/* Sayfa başlığı */
.page-sub { color:var(--muted); font-size:.95rem; margin:.15rem 0 0; }
.page-head-gap { height:.9rem; }

/* Liste satırları */
.row-title { font-size:1rem; font-weight:650; color:var(--ink); line-height:1.3; }
.row-meta { font-size:.84rem; color:var(--muted); margin-top:2px; }
.badge { display:inline-block; padding:2px 9px; margin:2px 6px 2px 0; border-radius:999px; font-size:.76rem; font-weight:600;
         background:#eef0f3; color:#475467; white-space:nowrap; }
.badge.ok { background:var(--accent-soft); color:var(--accent); }
.badge.warn { background:var(--warn-soft); color:var(--warn); }
.badge.danger { background:var(--danger-soft); color:var(--danger); }
.bar { height:6px; border-radius:99px; background:#e9ecef; overflow:hidden; margin-top:8px; max-width:220px; }
.bar > i { display:block; height:100%; background:var(--accent); border-radius:99px; }

/* Boş durum */
.empty { text-align:center; padding:2.6rem 1rem 1rem; }
.empty-icon { width:56px; height:56px; margin:0 auto 14px; border-radius:14px; background:var(--accent-soft); color:var(--accent);
              display:grid; place-items:center; font-size:26px; font-weight:700; }
.empty h3 { margin:0 0 6px; padding:0; }
.empty p { color:var(--muted); max-width:460px; margin:0 auto; font-size:.93rem; }

/* Adım kartları */
.step-no { width:28px; height:28px; border-radius:50%; background:var(--accent); color:#fff; display:grid; place-items:center;
           font-weight:700; font-size:.85rem; margin-bottom:10px; }
.step-no.done { background:var(--accent-soft); color:var(--accent); }
.step-title { font-weight:650; font-size:1rem; }
.step-text { color:var(--muted); font-size:.86rem; margin:4px 0 2px; min-height:2.6em; }

/* Bilgi şeridi (sınav özeti) */
.info-strip { display:flex; flex-wrap:wrap; gap:6px 22px; padding:10px 14px; border:1px solid var(--line); border-radius:10px;
              background:var(--surface); font-size:.88rem; color:var(--muted); }
.info-strip b { color:var(--ink); font-weight:650; }

/* Soru kartı (öğretmen kontrolü) */
.q-head { display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin-bottom:4px; }
.q-head b { font-size:1rem; } .q-head span { color:var(--muted); font-size:.8rem; }
.q-line { font-size:.87rem; margin:4px 0; color:#344054; line-height:1.45; }
.q-line i { display:inline-block; min-width:124px; color:var(--muted); font-style:normal; font-weight:600; font-size:.74rem;
            letter-spacing:.03em; text-transform:uppercase; }

/* Giriş ekranı */
.login-panel { min-height:430px; border-radius:14px; padding:40px; background:var(--accent); color:#fff;
               display:flex; flex-direction:column; justify-content:space-between; }
.login-panel * { color:#fff !important; }
.login-brand { font-size:1.05rem; font-weight:700; letter-spacing:.01em; }
.login-title { font-size:1.9rem; line-height:1.2; font-weight:700; letter-spacing:-.02em; margin:26px 0 18px; }
.login-list { margin:0; padding:0; list-style:none; }
.login-list li { padding:7px 0 7px 26px; position:relative; font-size:.95rem; opacity:.95; }
.login-list li::before { content:"✓"; position:absolute; left:0; font-weight:700; }
.login-foot { font-size:.8rem; opacity:.8; }
body:has(.login-panel) section[data-testid="stSidebar"], body:has(.login-panel) [data-testid="stSidebarCollapsedControl"] { display:none; }

.foot-note { color:var(--muted); font-size:.78rem; margin-top:2.5rem; padding-top:1rem; border-top:1px solid var(--line); }
@media (max-width:640px) { .block-container { padding:1rem 1rem 2rem; } }
</style>
"""


def stili_uygula():
    st.markdown(_CSS, unsafe_allow_html=True)
