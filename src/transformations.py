"""Standardization and typed Silver construction. Pure functions (no DB access)."""
import pandas as pd
from .config import STATUS_RANK, TS_FORMAT

_LINEAGE = ["source_file", "source_row_number"]


def standardize(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Trim whitespace on all source text columns. Done BEFORE validation so ' sp ' is not rejected."""
    out = df.copy()
    for c in columns:
        out[c] = out[c].fillna("").astype(str).str.strip()
    return out


def _ts(s):
    return pd.to_datetime(s, format=TS_FORMAT, errors="coerce")


def clean_customers(df, run_id, now):
    out = pd.DataFrame({
        "customer_id": df["customer_id"], "customer_unique_id": df["customer_unique_id"],
        "customer_zip_code_prefix": df["customer_zip_code_prefix"].replace("", None),
        "customer_city": df["customer_city"].str.lower(), "customer_state": df["customer_state"].str.upper(),
    })
    return _add_lineage(out, df, run_id, now)


def clean_orders(df, run_id, now):
    out = pd.DataFrame({"order_id": df["order_id"], "customer_id": df["customer_id"],
                        "order_status": df["order_status"].str.lower()})
    out["status_rank"] = out["order_status"].map(STATUS_RANK).astype("int32")
    for c in ("order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
              "order_delivered_customer_date", "order_estimated_delivery_date"):
        out[c] = _ts(df[c])
    return _add_lineage(out, df, run_id, now)


def clean_order_items(df, run_id, now):
    out = pd.DataFrame({
        "order_id": df["order_id"], "order_item_id": pd.to_numeric(df["order_item_id"]).astype("int32"),
        "product_id": df["product_id"], "seller_id": df["seller_id"],
        "shipping_limit_date": _ts(df["shipping_limit_date"]),
        "price": pd.to_numeric(df["price"]).round(2), "freight_value": pd.to_numeric(df["freight_value"]).round(2),
    })
    return _add_lineage(out, df, run_id, now)


def _add_lineage(out, src, run_id, now):
    out["source_file"] = src["source_file"].values
    out["source_row_number"] = src["source_row_number"].values
    out["run_id"], out["processed_at"] = run_id, now
    return out.reset_index(drop=True)
