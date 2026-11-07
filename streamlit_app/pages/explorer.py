import streamlit as st
from components import theme
from components.db import DatabaseUnavailable, q

theme.setup("Data Explorer", "Inspect Bronze, Silver and Gold tables. Read-only.")
theme.sidebar_header(); theme.refresh_button()
try:
    tables = q("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('bronze','silver','gold') ORDER BY 1, 2")
except DatabaseUnavailable as e:
    st.error(str(e)); st.stop()
if tables.empty:
    st.info("No tables found. Run the pipeline first."); st.stop()

c = st.columns([1, 2, 1])
layer = c[0].selectbox("Layer", sorted(tables["table_schema"].unique(), key=["bronze", "silver", "gold"].index))
name = c[1].selectbox("Table", tables[tables["table_schema"] == layer]["table_name"].tolist())
limit = c[2].select_slider("Preview rows", [100, 500, 1000, 5000], value=500)
full = f"{layer}.{name}"          # identifiers come from information_schema, never from free text
total = q(f"SELECT count(*) AS n FROM {full}")["n"].iloc[0]
df = q(f"SELECT * FROM {full} LIMIT {int(limit)}")
if df.empty:
    st.warning(f"{full} is empty."); st.stop()

col = st.selectbox("Filter column (optional)", ["(none)"] + list(df.columns))
text = st.text_input("Contains text", disabled=col == "(none)")
view = df if col == "(none)" or not text else df[df[col].astype(str).str.contains(text, case=False, regex=False)]
st.caption(f"{total:,} rows in {full}; showing {len(view):,} of the first {len(df):,}")
st.dataframe(view, use_container_width=True, hide_index=True)
if layer != "bronze" or total <= 200_000:
    full_df = q(f"SELECT * FROM {full}")
    st.download_button("Download full table as CSV", full_df.to_csv(index=False).encode("utf-8"), f"{layer}_{name}.csv", "text/csv")
else:
    st.caption("Bronze table too large for in-browser download; query the DuckDB file directly.")
