import streamlit as st
from components import theme
from components.db import DatabaseUnavailable, q

theme.setup("Rejected Records", "Quarantined records with original values, lineage and the rule(s) that failed them.")
theme.sidebar_header(); theme.refresh_button()
try:
    df = q("""SELECT record_id, 'orders' AS source_table, source_file, source_row_number, rejection_reason, run_id, rejection_timestamp FROM audit.rejected_orders
              UNION ALL SELECT record_id, 'customers', source_file, source_row_number, rejection_reason, run_id, rejection_timestamp FROM audit.rejected_customers
              UNION ALL SELECT record_id, 'order_items', source_file, source_row_number, rejection_reason, run_id, rejection_timestamp FROM audit.rejected_order_items""")
except DatabaseUnavailable as e:
    st.error(str(e)); st.stop()
if df.empty:
    st.success("The quarantine is empty: no records have been rejected."); st.stop()

c = st.columns(4)
tables = c[0].multiselect("Source table", sorted(df["source_table"].unique()))
runs_f = c[1].multiselect("Run ID", sorted(df["run_id"].unique(), reverse=True))
reasons = sorted({r for s in df["rejection_reason"] for r in s.split(";")})
reason_f = c[2].multiselect("Rejection reason", reasons)
text = c[3].text_input("Search record identifier")
if tables: df = df[df["source_table"].isin(tables)]
if runs_f: df = df[df["run_id"].isin(runs_f)]
if reason_f: df = df[df["rejection_reason"].apply(lambda s: any(r in s.split(";") for r in reason_f))]
if text: df = df[df["record_id"].str.contains(text, case=False, regex=False)]

st.caption(f"{len(df):,} records match")
if df.empty:
    st.warning("No rejected records match the current filters.")
else:
    st.dataframe(df.head(5000), use_container_width=True, hide_index=True)
    if len(df) > 5000:
        st.caption("Showing the first 5,000 rows; the download contains all matching rows.")
    st.download_button("Download as CSV", df.to_csv(index=False).encode("utf-8"), "rejected_records.csv", "text/csv")
