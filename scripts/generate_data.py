"""Synthetic Olist-shaped data for performance/reliability tests. NOT Kaggle data.

Every synthetic id starts with 'syn' and output goes to data/synthetic/<n>/ plus a MANIFEST.json,
so synthetic records can never be confused with the real dataset.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import SYNTHETIC_DIR, TABLES

STATUSES = ["delivered"] * 90 + ["shipped", "canceled", "invoiced", "processing", "created", "approved", "unavailable"]
STATES = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "GO", "PE", "CE"]
CITIES = ["sao paulo", "rio de janeiro", "belo horizonte", "porto alegre", "curitiba", "florianopolis"]
FMT = "%Y-%m-%d %H:%M:%S"


def _id(prefix, i):
    return f"syn{prefix}{i:028x}"


def generate(n_orders: int, out_dir=None, seed: int = 42, anomaly_rate: float = 0.02):
    """anomaly_rate: fraction of rows (per anomaly type) that get a controlled defect. 0 => fully clean."""
    rng = np.random.default_rng(seed)
    out = Path(out_dir or SYNTHETIC_DIR / str(n_orders)); out.mkdir(parents=True, exist_ok=True)
    n_cust = max(1, int(n_orders * 0.9))
    cust_ids = [_id("c", i) for i in range(n_cust)]
    uniq = rng.integers(0, max(1, int(n_cust * 0.95)), n_cust)
    customers = pd.DataFrame({
        "customer_id": cust_ids, "customer_unique_id": [_id("u", int(u)) for u in uniq],
        "customer_zip_code_prefix": rng.integers(1000, 99999, n_cust).astype(str),
        "customer_city": rng.choice(CITIES, n_cust), "customer_state": rng.choice(STATES, n_cust)})

    order_ids = [_id("o", i) for i in range(n_orders)]
    purchase = pd.Timestamp("2017-01-01") + pd.to_timedelta(rng.integers(0, 600 * 86400, n_orders), unit="s")
    delivered = purchase + pd.to_timedelta(rng.integers(2 * 86400, 25 * 86400, n_orders), unit="s")
    estimated = purchase + pd.to_timedelta(rng.integers(10 * 86400, 30 * 86400, n_orders), unit="s")
    status = rng.choice(STATUSES, n_orders)
    is_deliv = status == "delivered"
    orders = pd.DataFrame({
        "order_id": order_ids, "customer_id": rng.choice(cust_ids, n_orders), "order_status": status,
        "order_purchase_timestamp": purchase.strftime(FMT),
        "order_approved_at": (purchase + pd.to_timedelta(3600, unit="s")).strftime(FMT),
        "order_delivered_carrier_date": np.where(is_deliv, (purchase + pd.to_timedelta(86400, unit="s")).strftime(FMT), ""),
        "order_delivered_customer_date": np.where(is_deliv, delivered.strftime(FMT), ""),
        "order_estimated_delivery_date": estimated.strftime(FMT)})

    n_items_per = rng.choice([1, 1, 1, 2, 3], n_orders)
    rows = [(oid, k + 1) for oid, n in zip(order_ids, n_items_per) for k in range(n)]
    n_items = len(rows)
    items = pd.DataFrame(rows, columns=["order_id", "order_item_id"])
    items["product_id"] = [_id("p", int(i)) for i in rng.integers(0, 3000, n_items)]
    items["seller_id"] = [_id("s", int(i)) for i in rng.integers(0, 300, n_items)]
    items["shipping_limit_date"] = (pd.Timestamp("2017-01-05") + pd.to_timedelta(rng.integers(0, 600 * 86400, n_items), unit="s")).strftime(FMT)
    items["price"] = rng.gamma(2.0, 45.0, n_items).round(2).astype(str)
    items["freight_value"] = rng.gamma(2.0, 8.0, n_items).round(2).astype(str)

    manifest = {"synthetic": True, "seed": seed, "n_orders": n_orders, "anomaly_rate": anomaly_rate, "injected": {}}
    if anomaly_rate > 0:
        def pick(df): return rng.choice(len(df), max(1, int(len(df) * anomaly_rate)), replace=False)
        def note(k, idx): manifest["injected"][k] = int(len(idx))
        i = pick(orders); orders.loc[i, "customer_id"] = "syn_missing_customer"; note("orders_orphan_customer", i)
        i = pick(orders); orders.loc[i, "order_status"] = "teleported"; note("orders_invalid_status", i)
        i = pick(orders); orders.loc[i, "order_purchase_timestamp"] = "2017-13-45 99:99:99"; note("orders_invalid_purchase_ts", i)
        i = pick(orders); orders.loc[i, "order_delivered_customer_date"] = "2000-01-01 00:00:00"; orders.loc[i, "order_status"] = "delivered"; note("orders_delivered_before_purchase", i)
        i = pick(orders); orders.loc[i, "order_id"] = ""; note("orders_null_order_id", i)
        dup = orders.iloc[pick(orders)]; orders = pd.concat([orders, dup], ignore_index=True); note("orders_duplicate_rows", dup)
        i = pick(customers); customers.loc[i, "customer_state"] = ""; note("customers_null_state", i)
        dup = customers.iloc[pick(customers)]; customers = pd.concat([customers, dup], ignore_index=True); note("customers_duplicate_rows", dup)
        i = pick(items); items.loc[i, "price"] = "-10.00"; note("items_negative_price", i)
        i = pick(items); items.loc[i, "freight_value"] = "-1.50"; note("items_negative_freight", i)
        i = pick(items); items.loc[i, "seller_id"] = ""; note("items_null_seller", i)
        i = pick(items); items.loc[i, "order_id"] = "syn_missing_order"; note("items_orphan_order", i)
        dup = items.iloc[pick(items)]; items = pd.concat([items, dup], ignore_index=True); note("items_duplicate_composite_key", dup)

    for t, df in (("orders", orders), ("customers", customers), ("order_items", items)):
        df[TABLES[t]["columns"]].to_csv(out / TABLES[t]["filename"], index=False)
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    return out, manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--orders", type=int, nargs="+", default=[1000, 10000, 100000])
    p.add_argument("--seed", type=int, default=42); p.add_argument("--anomaly-rate", type=float, default=0.02)
    a = p.parse_args()
    for n in a.orders:
        print(generate(n, seed=a.seed, anomaly_rate=a.anomaly_rate))
