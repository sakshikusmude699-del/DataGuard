"""DataGuard dashboard entrypoint. Run: streamlit run streamlit_app/app.py"""
import streamlit as st

st.set_page_config(page_title="DataGuard", layout="wide", initial_sidebar_state="expanded")

nav = st.navigation([
    st.Page("pages/overview.py", title="Executive Overview", default=True),
    st.Page("pages/data_quality.py", title="Data Quality"),
    st.Page("pages/rejected.py", title="Rejected Records"),
    st.Page("pages/monitoring.py", title="Pipeline Monitoring"),
    st.Page("pages/explorer.py", title="Data Explorer"),
])
nav.run()
