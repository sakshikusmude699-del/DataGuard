"""Bronze -> Silver -> Gold with known-answer fixture (expected values in data/expected/)."""
from decimal import Decimal
import pytest


@pytest.fixture
def ran(run, raw_dir):
    return run(raw_dir)


def test_silver_and_rejected_counts_match_expected(ran, query, expected):
    for t, silver, rej in (("customers", "silver.customers_clean", "audit.rejected_customers"),
                           ("orders", "silver.orders_clean", "audit.rejected_orders"),
                           ("order_items", "silver.order_items_clean", "audit.rejected_order_items")):
        assert query(f"SELECT count(*) FROM {silver}")[0][0] == expected["valid_rows"][t]
        assert query(f"SELECT count(*) FROM {rej}")[0][0] == expected["rejected_rows"][t]


def test_rejection_reasons_match_expected(ran, query, expected):
    for t, rej in (("customers", "audit.rejected_customers"), ("orders", "audit.rejected_orders"),
                   ("order_items", "audit.rejected_order_items")):
        got = {}
        for (reason,) in query(f"SELECT rejection_reason FROM {rej}"):
            for r in reason.split(";"):
                got[r] = got.get(r, 0) + 1
        assert got == expected["rejection_reasons"][t], t


def test_every_rejected_row_is_traceable(ran, query):
    rows = query("SELECT source_file, source_row_number, run_id, rejection_reason, rejection_timestamp, order_id "
                 "FROM audit.rejected_orders")
    assert rows and all(all(v is not None and v != "" for v in r[:5]) for r in rows)


def test_rejected_rows_retain_original_values(ran, query):
    assert query("SELECT order_status FROM audit.rejected_orders WHERE order_id='o5'")[0][0] == "bogus"


def test_bronze_preserves_every_source_row(ran, query, expected):
    assert query("SELECT count(*) FROM bronze.orders_raw")[0][0] == expected["source_rows"]["orders"]
    assert query("SELECT count(*) FROM bronze.customers_raw WHERE customer_state='S'")[0][0] == 1  # invalid value kept raw


def test_gold_totals_do_not_double_count(ran, query, expected):
    g = expected["gold"]
    assert query("SELECT count(*) FROM gold.fact_orders")[0][0] == g["fact_orders_rows"]
    rev, fr, val = query("SELECT sum(items_revenue), sum(freight_total), sum(order_value) FROM gold.fact_orders")[0]
    assert (rev, fr, val) == (Decimal(g["items_revenue"]), Decimal(g["freight_total"]), Decimal(g["order_value"]))
    assert query("SELECT order_value FROM gold.fact_orders WHERE order_id='o1'")[0][0] == Decimal(g["o1_order_value"])
    # order o1 has two items: fact grain must stay one row per order
    assert query("SELECT count(*) FROM gold.fact_orders WHERE order_id='o1'")[0][0] == 1


def test_dim_customers_groups_by_unique_id(ran, query, expected):
    g = expected["gold"]
    assert query("SELECT count(*) FROM gold.dim_customers")[0][0] == g["dim_customers_rows"]  # c1,c2 share u1
    assert query("SELECT count(*) FROM gold.dim_customers WHERE is_repeat_customer")[0][0] == g["repeat_customers"]
    assert query("SELECT order_count FROM gold.dim_customers WHERE customer_unique_id='u1'")[0][0] == 2


def test_delivery_performance(ran, query, expected):
    g = expected["gold"]
    d, late, pct = query("SELECT sum(delivered_orders), sum(late_orders), 100.0*sum(late_orders)/sum(delivered_orders) "
                         "FROM gold.delivery_performance")[0]
    assert (d, late, pct) == (g["delivered_orders"], g["late_orders"], g["late_delivery_pct"])
    avg = query("SELECT avg(delivery_days) FROM gold.fact_orders WHERE delivery_days IS NOT NULL")[0][0]
    assert avg == pytest.approx(g["avg_delivery_days"])


def test_sales_summary_matches_fact(ran, query):
    assert query("SELECT sum(total_orders) FROM gold.sales_summary")[0][0] == query("SELECT count(*) FROM gold.fact_orders")[0][0]


def test_gold_built_only_from_silver(ran, query):
    assert query("SELECT count(*) FROM gold.fact_orders f WHERE NOT EXISTS "
                 "(SELECT 1 FROM silver.orders_clean o WHERE o.order_id=f.order_id)")[0][0] == 0
