"""Silver publication (validate -> quarantine -> MERGE) and Gold builds."""
from dataclasses import dataclass, field
import pandas as pd
from .config import TABLES
from . import data_quality as dq
from . import transformations as tf


@dataclass
class TableResult:
    table: str
    source_rows: int = 0
    valid_rows: int = 0
    rejected_rows: int = 0
    duplicate_rows: int = 0
    rule_results: list = field(default_factory=list)
    null_profile: list = field(default_factory=list)


def _ids(con, qualified, col):
    return set(con.execute(f"SELECT {col} FROM {qualified}").df()[col])


def merge_silver(con, qualified: str, df: pd.DataFrame, keys, update_condition: str = "") -> None:
    """Transactional upsert. Inserts new keys; updates existing keys (optionally only if condition)."""
    cols = list(df.columns)
    on = " AND ".join(f"tgt.{k} = src.{k}" for k in keys)
    sets = ", ".join(f"{c} = src.{c}" for c in cols if c not in keys)
    cond = f" AND {update_condition}" if update_condition else ""
    con.register("silver_batch", df)
    try:
        con.execute(f"""MERGE INTO {qualified} AS tgt USING silver_batch AS src ON ({on})
            WHEN MATCHED{cond} THEN UPDATE SET {sets}
            WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({', '.join('src.' + c for c in cols)})""")
    finally:
        con.unregister("silver_batch")


def _quarantine(con, table, df, reasons, run_id, now, file_hash):
    spec = TABLES[table]
    bad = df[reasons != ""].copy()
    # Re-processing a file replaces (not appends to) its quarantine rows -> idempotent.
    con.execute(f"DELETE FROM {spec['rejected']} WHERE source_file_hash = ?", [file_hash])
    if bad.empty:
        return
    keys = spec["keys"]
    # Vectorized (was a row-wise DataFrame.apply(axis=1): ~50% of Silver time at 100k orders, see README benchmark).
    parts = [bad[k].where(bad[k].str.strip() != "", "<missing>") for k in keys]
    bad["record_id"] = parts[0] if len(parts) == 1 else parts[0].str.cat(parts[1:], sep="|")
    bad["run_id"], bad["rejection_reason"] = run_id, reasons[reasons != ""]
    bad["rejection_timestamp"] = now
    cols = ["record_id"] + spec["columns"] + ["source_file", "source_file_hash", "source_row_number",
                                              "run_id", "rejection_reason", "rejection_timestamp"]
    con.register("rej_batch", bad[cols])
    try:
        con.execute(f"INSERT INTO {spec['rejected']} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM rej_batch")
    finally:
        con.unregister("rej_batch")


def process_table(con, table: str, bronze_df: pd.DataFrame, run_id: str, now, file_hash: str) -> TableResult:
    spec = TABLES[table]
    df = tf.standardize(bronze_df, spec["columns"])
    if table == "orders":
        df["order_status"] = df["order_status"].str.lower()   # status is case-insensitive by definition
    if table == "customers":
        rules = dq.customers_rules(df)
    elif table == "orders":
        rules = dq.orders_rules(df, _ids(con, "silver.customers_clean", "customer_id"))
    else:
        rules = dq.order_items_rules(df, _ids(con, "silver.orders_clean", "order_id"))
    reasons, results = dq.evaluate(df, rules)
    _quarantine(con, table, bronze_df, reasons, run_id, now, file_hash)  # raw values, not standardized

    valid = df[reasons == ""]
    if not valid.empty:
        if table == "customers":
            merge_silver(con, spec["silver"], tf.clean_customers(valid, run_id, now), spec["keys"])
        elif table == "orders":
            # Late/out-of-order protection: never move an order backwards in its lifecycle.
            merge_silver(con, spec["silver"], tf.clean_orders(valid, run_id, now), spec["keys"],
                         "src.status_rank >= tgt.status_rank")
        else:
            merge_silver(con, spec["silver"], tf.clean_order_items(valid, run_id, now), spec["keys"])
    dup_rows = sum(r.rows_failed for r in results if r.dimension == "uniqueness")
    return TableResult(table, len(df), len(valid), int((reasons != "").sum()), dup_rows, results,
                       dq.null_profile(df, spec["columns"]))


# ------------------------------- GOLD ---------------------------------------
GOLD_SQL = {
"gold.fact_orders": """
CREATE OR REPLACE TABLE gold.fact_orders AS
WITH items AS (  -- pre-aggregate the one-to-many table BEFORE joining so order values are never double counted
  SELECT order_id, COUNT(*) AS item_count, SUM(price) AS items_revenue, SUM(freight_value) AS freight_total
  FROM silver.order_items_clean GROUP BY order_id)
SELECT o.order_id, o.customer_id, c.customer_unique_id, c.customer_state, c.customer_city,
  o.order_status, o.order_purchase_timestamp,
  CAST(date_trunc('month', o.order_purchase_timestamp) AS DATE) AS purchase_month,
  o.order_delivered_customer_date, o.order_estimated_delivery_date,
  COALESCE(i.item_count, 0) AS item_count,
  COALESCE(i.items_revenue, 0)::DECIMAL(14,2) AS items_revenue,
  COALESCE(i.freight_total, 0)::DECIMAL(14,2) AS freight_total,
  (COALESCE(i.items_revenue, 0) + COALESCE(i.freight_total, 0))::DECIMAL(14,2) AS order_value,
  CASE WHEN o.order_delivered_customer_date IS NOT NULL
       THEN date_diff('second', o.order_purchase_timestamp, o.order_delivered_customer_date) / 86400.0 END AS delivery_days,
  CASE WHEN o.order_delivered_customer_date IS NOT NULL AND o.order_estimated_delivery_date IS NOT NULL
       THEN o.order_delivered_customer_date > o.order_estimated_delivery_date END AS is_late
FROM silver.orders_clean o
JOIN silver.customers_clean c ON c.customer_id = o.customer_id
LEFT JOIN items i ON i.order_id = o.order_id""",
"gold.dim_customers": """
CREATE OR REPLACE TABLE gold.dim_customers AS
SELECT c.customer_unique_id,
  COUNT(DISTINCT c.customer_id) AS customer_id_count,
  COALESCE(arg_max(c.customer_state, f.order_purchase_timestamp), min(c.customer_state)) AS customer_state,
  COALESCE(arg_max(c.customer_city, f.order_purchase_timestamp), min(c.customer_city)) AS customer_city,
  COUNT(f.order_id) AS order_count,
  COALESCE(SUM(f.order_value), 0)::DECIMAL(14,2) AS total_spent,
  MIN(f.order_purchase_timestamp) AS first_purchase, MAX(f.order_purchase_timestamp) AS last_purchase,
  COUNT(f.order_id) > 1 AS is_repeat_customer
FROM silver.customers_clean c LEFT JOIN gold.fact_orders f ON f.customer_id = c.customer_id
GROUP BY c.customer_unique_id""",
"gold.sales_summary": """
CREATE OR REPLACE TABLE gold.sales_summary AS
SELECT purchase_month, order_status, customer_state,
  COUNT(*) AS total_orders, SUM(items_revenue) AS total_revenue, SUM(freight_total) AS total_freight,
  SUM(order_value) AS total_order_value,
  SUM(order_value) / NULLIF(COUNT(*) FILTER (WHERE item_count > 0), 0) AS avg_order_value
FROM gold.fact_orders GROUP BY purchase_month, order_status, customer_state""",
"gold.delivery_performance": """
CREATE OR REPLACE TABLE gold.delivery_performance AS
SELECT purchase_month, customer_state,
  COUNT(*) AS delivered_orders, AVG(delivery_days) AS avg_delivery_days,
  COUNT(*) FILTER (WHERE is_late) AS late_orders,
  100.0 * COUNT(*) FILTER (WHERE is_late) / NULLIF(COUNT(*) FILTER (WHERE is_late IS NOT NULL), 0) AS late_delivery_pct
FROM gold.fact_orders WHERE order_delivered_customer_date IS NOT NULL
GROUP BY purchase_month, customer_state""",
}


def build_gold(con) -> int:
    """Rebuild Gold from Silver. Caller wraps this in a transaction so a failure leaves old Gold intact."""
    for sql in GOLD_SQL.values():
        con.execute(sql)
    return con.execute("SELECT count(*) FROM gold.fact_orders").fetchall()[0][0]
