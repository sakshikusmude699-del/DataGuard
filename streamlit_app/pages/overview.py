import pandas as pd
import plotly.express as px
import streamlit as st
from components import theme
from components.db import DatabaseUnavailable, q, runs

theme.setup("Executive Overview", "Current state of the Olist e-commerce pipeline: volume, quality and delivery health.")
theme.sidebar_header(); theme.refresh_button()
run_id = theme.run_selector()

try:
    stats = q("SELECT * FROM audit.table_run_stats WHERE run_id = ?", (run_id,))
    scores = q("SELECT dimension, score FROM audit.quality_scores WHERE run_id = ?", (run_id,))
    run = runs().query("run_id == @run_id").iloc[0]
    fact = q("SELECT * FROM gold.fact_orders")
    sales = q("SELECT * FROM gold.sales_summary")
except DatabaseUnavailable as e:
    st.error(str(e)); st.stop()

src, valid, rej = int(stats["source_rows"].sum()), int(stats["valid_rows"].sum()), int(stats["rejected_rows"].sum())
overall = scores.set_index("dimension")["score"].get("overall")
c = st.columns(6)
theme.stat(c[0], "Source records", f"{src:,}", "selected run")
theme.stat(c[1], "Valid", f"{valid:,}", f"{valid / src:.1%} of source" if src else "", "dg-ok")
theme.stat(c[2], "Rejected", f"{rej:,}", f"{rej / src:.1%} of source" if src else "", "dg-bad" if rej else "")
theme.stat(c[3], "Quality score", theme.fmt_pct(overall), "mean of four dimensions")
theme.stat(c[4], "Pipeline status", run["execution_status"].title(), f"reconciliation {run['reconciliation_status']}",
           "dg-ok" if run["execution_status"] == "SUCCESS" else "dg-bad")
theme.stat(c[5], "Last executed", pd.Timestamp(run["end_time"]).strftime("%d %b %Y"), pd.Timestamp(run["end_time"]).strftime("%H:%M UTC"))

st.markdown("### Filters")
f1, f2 = st.columns(2)
if fact.empty:
    st.info("Gold tables are empty: no valid orders were published."); st.stop()
dmin, dmax = fact["order_purchase_timestamp"].min().date(), fact["order_purchase_timestamp"].max().date()
dates = f1.date_input("Purchase date range", (dmin, dmax), min_value=dmin, max_value=dmax)
statuses = f2.multiselect("Order status", sorted(fact["order_status"].unique()), default=sorted(fact["order_status"].unique()))
if len(dates) == 2:
    fact = fact[(fact["order_purchase_timestamp"].dt.date >= dates[0]) & (fact["order_purchase_timestamp"].dt.date <= dates[1])]
fact = fact[fact["order_status"].isin(statuses)]
if fact.empty:
    st.warning("No orders match the current filters."); st.stop()

st.markdown("### Orders and revenue")
a, b = st.columns(2)
monthly = fact.groupby("purchase_month").agg(orders=("order_id", "count"), revenue=("items_revenue", "sum")).reset_index()
monthly["revenue"] = monthly["revenue"].astype(float)
a.plotly_chart(px.line(monthly, x="purchase_month", y="orders", title="Orders per month").update_traces(line_width=2), use_container_width=True)
b.plotly_chart(px.area(monthly, x="purchase_month", y="revenue", title="Item revenue per month").update_traces(line_width=2), use_container_width=True)

a, b = st.columns(2)
by_status = fact.groupby("order_status").size().reset_index(name="orders").sort_values("orders")
a.plotly_chart(px.bar(by_status, x="orders", y="order_status", orientation="h", title="Orders by status"), use_container_width=True)
vr = stats.melt(id_vars="table_name", value_vars=["valid_rows", "rejected_rows"], var_name="kind", value_name="rows")
vr["kind"] = vr["kind"].map({"valid_rows": "Valid", "rejected_rows": "Rejected"})
fig = px.bar(vr, x="table_name", y="rows", color="kind", barmode="group", title="Valid versus rejected records (selected run)",
             color_discrete_map={"Valid": theme.OK, "Rejected": theme.BAD}, labels={"table_name": "", "kind": ""})
b.plotly_chart(fig, use_container_width=True)

st.markdown("### System health")
late = q("SELECT 100.0*sum(late_orders)/NULLIF(sum(delivered_orders),0) AS p FROM gold.delivery_performance")["p"].iloc[0]
recon_fail = q("SELECT count(*) AS n FROM audit.reconciliation WHERE run_id = ? AND status <> 'PASS'", (run_id,))["n"].iloc[0]
recent_fail = q("SELECT count(*) AS n FROM audit.pipeline_runs WHERE execution_status = 'FAILED'")["n"].iloc[0]
st.markdown(
    f"- Run `{run_id}` finished **{run['execution_status'].lower()}** in {run['execution_duration']:.1f} s with "
    f"{recon_fail} failed reconciliation checks.\n"
    f"- {rej:,} of {src:,} source records were quarantined ({rej / src:.2%}); every one is traceable on the Rejected Records page.\n"
    f"- Late delivery rate across published orders: {late:.1f}%.\n"
    f"- Failed runs recorded in history: {recent_fail}.")
