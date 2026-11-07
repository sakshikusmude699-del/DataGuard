import pandas as pd
from datetime import datetime
from src import transformations as tf
from conftest import OC, IC, CC, order, item, cust

NOW = datetime(2024, 1, 1)


def with_lineage(df):
    df["source_file"] = "f.csv"; df["source_row_number"] = range(2, len(df) + 2); return df


def test_standardize_trims_whitespace():
    d = pd.DataFrame({"a": ["  x ", "y"]})
    assert list(tf.standardize(d, ["a"])["a"]) == ["x", "y"]


def test_clean_customers_normalizes_case():
    d = with_lineage(pd.DataFrame([cust("c1", "u1", "sp", "SAO PAULO")], columns=CC))
    out = tf.clean_customers(d, "r", NOW)
    assert out["customer_state"][0] == "SP" and out["customer_city"][0] == "sao paulo"


def test_clean_orders_types_and_rank():
    d = with_lineage(pd.DataFrame([order("o1", "c1", status="Delivered")], columns=OC))
    out = tf.clean_orders(d, "r", NOW)
    assert out["order_status"][0] == "delivered" and out["status_rank"][0] == 6
    assert out["order_purchase_timestamp"][0] == pd.Timestamp("2018-01-01 10:00:00")


def test_clean_orders_blank_optional_timestamp_becomes_null():
    d = with_lineage(pd.DataFrame([order("o1", "c1", status="shipped", delivered="")], columns=OC))
    assert pd.isna(tf.clean_orders(d, "r", NOW)["order_delivered_customer_date"][0])


def test_clean_items_numeric_types():
    d = with_lineage(pd.DataFrame([item("o1", 1, "10.456", "1")], columns=IC))
    out = tf.clean_order_items(d, "r", NOW)
    assert out["order_item_id"][0] == 1 and out["price"][0] == 10.46
