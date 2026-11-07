import plotly.express as px
import streamlit as st
from components import theme
from components.db import DatabaseUnavailable, q

theme.setup("Data Quality", "Four dimensions, each derived from rule-level pass rates. Formulas are documented in docs/design_decisions.md.")
theme.sidebar_header(); theme.refresh_button()
run_id = theme.run_selector()
try:
    scores = q("SELECT dimension, score, rows_evaluated, rows_failed FROM audit.quality_scores WHERE run_id = ?", (run_id,)).set_index("dimension")
    rules = q("SELECT table_name, rule_name, dimension, rows_evaluated, rows_failed FROM audit.rule_results WHERE run_id = ?", (run_id,))
    nulls = q("SELECT table_name, column_name, null_count, total_rows FROM audit.null_profile WHERE run_id = ?", (run_id,))
    schema = q("SELECT table_name, status, missing_columns, unexpected_columns FROM audit.schema_checks WHERE run_id = ?", (run_id,))
    trend = q("""SELECT r.start_time, s.dimension, s.score FROM audit.quality_scores s
                 JOIN audit.pipeline_runs r USING (run_id) ORDER BY r.start_time""")
except DatabaseUnavailable as e:
    st.error(str(e)); st.stop()

c = st.columns(5)
for col, dim in zip(c, ["completeness", "validity", "uniqueness", "referential", "overall"]):
    v = scores["score"].get(dim)
    theme.stat(col, dim.replace("referential", "referential integrity"), theme.fmt_pct(v),
               f"{int(scores['rows_failed'].get(dim, 0)):,} failed checks" if dim in scores.index else "")

st.markdown("### Validation rule failures")
failing = rules[rules["rows_failed"] > 0].sort_values("rows_failed")
if failing.empty:
    st.success("No validation rule failed in this run.")
else:
    failing = failing.assign(rule=failing["table_name"] + " / " + failing["rule_name"])
    fig = px.bar(failing, x="rows_failed", y="rule", color="dimension", orientation="h", labels={"rows_failed": "Rows failed", "rule": ""})
    fig.update_layout(height=max(260, 28 * len(failing)))
    st.plotly_chart(fig, use_container_width=True)
with st.expander("All rule results"):
    st.dataframe(rules.assign(pass_rate=1 - rules["rows_failed"] / rules["rows_evaluated"].clip(lower=1)), use_container_width=True, hide_index=True)

a, b = st.columns(2)
with a:
    st.markdown("### Null-value distribution")
    n = nulls.assign(pct=100 * nulls["null_count"] / nulls["total_rows"].clip(lower=1), field=lambda d: d["table_name"] + "." + d["column_name"])
    n = n[n["null_count"] > 0].sort_values("pct")
    if n.empty:
        st.success("No missing values in any source column.")
    else:
        st.plotly_chart(px.bar(n, x="pct", y="field", orientation="h", labels={"pct": "% missing", "field": ""}), use_container_width=True)
with b:
    st.markdown("### Duplicate records")
    dup = rules[rules["dimension"] == "uniqueness"][["table_name", "rule_name", "rows_failed"]]
    st.dataframe(dup.rename(columns={"rows_failed": "duplicate rows"}), use_container_width=True, hide_index=True)

st.markdown("### Schema validation")
st.dataframe(schema, use_container_width=True, hide_index=True)

st.markdown("### Quality across runs")
trend = trend[trend["dimension"] != "overall"] if st.toggle("Hide overall score", value=False) else trend
if len(trend["start_time"].unique()) < 2:
    st.info("Only one run recorded; a trend appears after the pipeline has run at least twice on new data.")
st.plotly_chart(px.line(trend, x="start_time", y="score", color="dimension", markers=True, labels={"start_time": "", "score": "Score"}), use_container_width=True)
