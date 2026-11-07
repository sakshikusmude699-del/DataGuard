"""Each test pins a defect that was found during development (see docs/design_decisions.md)."""
from conftest import cust, item, order, write_csv


def test_regression_undelivered_order_without_delivery_date_is_valid(run, tmp_path, query):
    """Early draft rejected every row with a blank delivery date."""
    d = tmp_path / "d"
    write_csv(d, "customers", [cust("c1", "u1")])
    write_csv(d, "orders", [order("o1", "c1", status="shipped", delivered=""), order("o2", "c1", status="canceled", delivered="")])
    write_csv(d, "order_items", [item("o1", 1)])
    run(d)
    assert query("SELECT count(*) FROM silver.orders_clean")[0][0] == 2


def test_regression_customer_unique_id_repeated_across_customer_ids_is_valid(run, tmp_path, query):
    d = tmp_path / "d"
    write_csv(d, "customers", [cust("c1", "same"), cust("c2", "same")])
    write_csv(d, "orders", [order("o1", "c1"), order("o2", "c2")])
    write_csv(d, "order_items", [item("o1", 1), item("o2", 1)])
    run(d)
    assert query("SELECT count(*) FROM silver.customers_clean")[0][0] == 2
    assert query("SELECT order_count FROM gold.dim_customers")[0][0] == 2


def test_regression_multi_item_order_not_double_counted_in_revenue(run, tmp_path, query):
    d = tmp_path / "d"
    write_csv(d, "customers", [cust("c1", "u1")]); write_csv(d, "orders", [order("o1", "c1")])
    write_csv(d, "order_items", [item("o1", i, "10.00", "1.00") for i in range(1, 6)])
    run(d)
    assert float(query("SELECT sum(order_value) FROM gold.fact_orders")[0][0]) == 55.0


def test_regression_leading_zero_zip_preserved(run, tmp_path, query):
    d = tmp_path / "d"
    write_csv(d, "customers", [cust("c1", "u1", zip_="01046")]); write_csv(d, "orders", [order("o1", "c1")]); write_csv(d, "order_items", [item("o1", 1)])
    run(d)
    assert query("SELECT customer_zip_code_prefix FROM silver.customers_clean")[0][0] == "01046"


def test_regression_whitespace_padded_values_are_trimmed_not_rejected(run, tmp_path, query):
    d = tmp_path / "d"
    write_csv(d, "customers", [cust(" c1 ", "u1", state=" sp ")]); write_csv(d, "orders", [order("o1", "c1", status=" Delivered ")])
    write_csv(d, "order_items", [item("o1", 1)])
    run(d)
    assert query("SELECT customer_state FROM silver.customers_clean")[0][0] == "SP"
    assert query("SELECT count(*) FROM silver.orders_clean")[0][0] == 1


def test_regression_row_failing_multiple_rules_is_quarantined_once(run, tmp_path, query):
    d = tmp_path / "d"
    write_csv(d, "customers", [cust("c1", "u1")])
    write_csv(d, "orders", [order("o1", "zzz", status="bogus")]); write_csv(d, "order_items", [item("o9", 1)])
    run(d)
    rows = query("SELECT rejection_reason FROM audit.rejected_orders")
    assert len(rows) == 1 and "INVALID_ORDER_STATUS" in rows[0][0] and "ORPHAN_CUSTOMER_ID" in rows[0][0]
