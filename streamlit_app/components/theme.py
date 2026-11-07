"""Visual system: warm off-white, charcoal type, slate secondary text, teal accent.
Red is reserved for failures/rejections, green for passing validations."""
import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio
from .db import DatabaseUnavailable, runs

INK, SLATE, ACCENT, RULE, PAPER = "#1F2328", "#5B6572", "#1F6F78", "#D9D4C9", "#F7F5F0"
OK, BAD = "#2E7D4F", "#B3261E"

_CSS = f"""
<style>
html, body, [class*="css"] {{ font-family: "Inter", "Helvetica Neue", Arial, sans-serif; color:{INK}; }}
.block-container {{ padding-top: 2.2rem; max-width: 1240px; }}
h1, h2, h3 {{ font-family: Georgia, "Times New Roman", serif; font-weight: 600; letter-spacing: -0.01em; color:{INK}; }}
h1 {{ font-size: 1.9rem; margin-bottom: .15rem; }}
h3 {{ font-size: 1.1rem; border-bottom: 1px solid {RULE}; padding-bottom: .35rem; margin-top: 1.6rem; }}
section[data-testid="stSidebar"] {{ border-right: 1px solid {RULE}; }}
.dg-brand {{ font-family: Georgia, serif; font-size: 1.35rem; font-weight: 700; letter-spacing: .01em; }}
.dg-sub {{ color:{SLATE}; font-size:.78rem; text-transform: uppercase; letter-spacing: .08em; }}
.dg-lede {{ color:{SLATE}; margin-bottom: 1.2rem; }}
.dg-stat {{ border-top: 2px solid {INK}; padding-top: .45rem; }}
.dg-stat .l {{ color:{SLATE}; font-size:.72rem; text-transform: uppercase; letter-spacing: .08em; }}
.dg-stat .v {{ font-family: Georgia, serif; font-size: 1.7rem; line-height: 1.2; }}
.dg-stat .n {{ color:{SLATE}; font-size:.75rem; }}
.dg-ok {{ color:{OK}; }} .dg-bad {{ color:{BAD}; }}
</style>
"""

_TEMPLATE = go.layout.Template(layout=dict(
    font=dict(family="Inter, Helvetica Neue, Arial, sans-serif", color=INK, size=12),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", colorway=[ACCENT, "#7A8794", "#B7A98A", INK],
    xaxis=dict(gridcolor=RULE, linecolor=RULE, zeroline=False), yaxis=dict(gridcolor=RULE, linecolor=RULE, zeroline=False),
    margin=dict(l=10, r=10, t=36, b=10), title=dict(font=dict(size=13, color=INK), x=0), legend=dict(orientation="h", y=-0.2)))
pio.templates["dataguard"] = _TEMPLATE
pio.templates.default = "dataguard"


def setup(title: str, lede: str = ""):
    st.markdown(_CSS, unsafe_allow_html=True)
    st.title(title)
    if lede:
        st.markdown(f'<div class="dg-lede">{lede}</div>', unsafe_allow_html=True)


def stat(col, label, value, note="", cls=""):
    col.markdown(f'<div class="dg-stat"><div class="l">{label}</div><div class="v {cls}">{value}</div>'
                 f'<div class="n">{note}</div></div>', unsafe_allow_html=True)


def sidebar_header():
    st.sidebar.markdown('<div class="dg-brand">DataGuard</div><div class="dg-sub">Pipeline quality and DataOps</div>',
                        unsafe_allow_html=True)


def refresh_button():
    if st.sidebar.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


def run_selector(include_all=False):
    """Sidebar run filter. Returns selected run_id (or None for 'All runs')."""
    try:
        r = runs()
    except DatabaseUnavailable as e:
        st.error(str(e)); st.stop()
    if r.empty:
        st.info("No pipeline runs recorded yet. Run `python scripts/run_pipeline.py` to populate the database."); st.stop()
    ok = r[r["execution_status"] == "SUCCESS"]
    options = ok["run_id"].tolist()
    if include_all:
        options = ["All runs"] + options
    if not options:
        st.warning("No successful runs yet; see Pipeline Monitoring for failures."); st.stop()
    choice = st.sidebar.selectbox("Run", options, help="Successful runs only")
    return None if choice == "All runs" else choice


def fmt_pct(x):
    return "n/a" if x is None or x != x else f"{100 * x:.2f}%"
