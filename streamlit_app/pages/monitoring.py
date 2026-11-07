import plotly.express as px
import streamlit as st
from components import theme
from components.db import DatabaseUnavailable, q

theme.setup("Pipeline Monitoring", "Execution history, reconciliation outcomes and failure diagnostics.")
theme.sidebar_header(); theme.refresh_button()
try:
    runs = q("SELECT * FROM audit.pipeline_runs ORDER BY start_time DESC")
except DatabaseUnavailable as e:
    st.error(str(e)); st.stop()
if runs.empty:
    st.info("No runs recorded yet."); st.stop()

status = st.multiselect("Execution status", sorted(runs["execution_status"].unique()), default=sorted(runs["execution_status"].unique()))
view = runs[runs["execution_status"].isin(status)]
c = st.columns(4)
theme.stat(c[0], "Runs", f"{len(runs):,}")
theme.stat(c[1], "Successful", f"{(runs.execution_status == 'SUCCESS').sum():,}", cls="dg-ok")
theme.stat(c[2], "Failed", f"{(runs.execution_status == 'FAILED').sum():,}", cls="dg-bad" if (runs.execution_status == 'FAILED').any() else "")
theme.stat(c[3], "Skipped (no new data)", f"{(runs.execution_status == 'SKIPPED_NO_NEW_DATA').sum():,}")

st.markdown("### Run history")
cols = ["run_id", "execution_status", "start_time", "end_time", "execution_duration", "input_count", "bronze_count",
        "silver_count", "gold_count", "rejected_count", "duplicate_count", "reconciliation_status", "data_source", "failure_reason"]
st.dataframe(view[cols], use_container_width=True, hide_index=True)

ok = runs[runs["execution_status"] == "SUCCESS"]
if not ok.empty:
    st.plotly_chart(px.bar(ok.sort_values("start_time"), x="start_time", y="execution_duration", title="Execution duration (s), successful runs",
                           labels={"start_time": "", "execution_duration": "seconds"}), use_container_width=True)

failed = runs[runs["failure_reason"].notna()]
if not failed.empty:
    st.markdown("### Failures")
    st.dataframe(failed[["run_id", "start_time", "failure_reason"]], use_container_width=True, hide_index=True)

st.markdown("### Reconciliation")
rid = st.selectbox("Run", ok["run_id"].tolist() if not ok.empty else [])
if rid:
    rec = q("SELECT check_name, expected, actual, status FROM audit.reconciliation WHERE run_id = ?", (rid,))
    st.dataframe(rec, use_container_width=True, hide_index=True)
