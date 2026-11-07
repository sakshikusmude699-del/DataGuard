import pandas as pd
import pytest
from src import data_quality as dq


def df(**cols):
    d = pd.DataFrame(cols)
    d["source_row_number"] = range(2, len(d) + 2)
    return d


def reasons_for(rules, frame):
    r, _ = dq.evaluate(frame, rules)
    return list(r)


def test_required_detects_blank_and_whitespace():
    f = df(a=["x", "", "  "])
    assert list(dq.required(f, "a")[2]) == [False, True, True]


def test_invalid_timestamp_distinguishes_missing_from_invalid():
    f = df(t=["2018-01-01 10:00:00", "", "2018-13-01 10:00:00", "garbage"])
    _, _, failed, evaluated = dq.invalid_timestamp(f, "t")
    assert list(failed) == [False, False, True, True]
    assert list(evaluated) == [True, False, True, True]    # blank is not evaluated -> not 'invalid'


def test_negative_and_non_numeric_prices():
    f = df(price=["10", "-1", "abc", "0"])
    assert list(dq.negative_number(f, "price")[2]) == [False, True, False, False]
    assert list(dq.invalid_number(f, "price")[2]) == [False, False, True, False]


def test_order_status_rule():
    f = df(order_status=["delivered", "teleported", ""])
    assert list(dq.not_in_set(f, "order_status", {"delivered"}, "X")[2]) == [False, True, False]


def test_orders_delivered_before_purchase():
    from conftest import OC, order
    f = pd.DataFrame([order("o1", "c1", delivered="2017-01-01 00:00:00")], columns=OC); f["source_row_number"] = [2]
    assert "DELIVERED_BEFORE_PURCHASE" in reasons_for(dq.orders_rules(f, {"c1"}), f)[0]


def test_missing_delivery_date_only_invalid_for_delivered_status():
    from conftest import OC, order
    rows = [order("o1", "c1", status="delivered", delivered=""), order("o2", "c1", status="shipped", delivered="")]
    f = pd.DataFrame(rows, columns=OC); f["source_row_number"] = [2, 3]
    r = reasons_for(dq.orders_rules(f, {"c1"}), f)
    assert "DELIVERED_STATUS_MISSING_DELIVERY_DATE" in r[0]
    assert r[1] == ""                      # legitimate business scenario, NOT rejected


def test_orphan_customer_rule():
    from conftest import OC, order
    f = pd.DataFrame([order("o1", "missing")], columns=OC); f["source_row_number"] = [2]
    assert "ORPHAN_CUSTOMER_ID" in reasons_for(dq.orders_rules(f, {"c1"}), f)[0]


def test_customer_state_and_city_rules():
    from conftest import CC
    f = pd.DataFrame([["c1", "u1", "1", "sp", "SP"], ["c2", "u2", "1", "sp", "S"],
                      ["c3", "u3", "1", "12345", "SP"], ["c4", "", "1", "sp", "SP"]], columns=CC)
    f["source_row_number"] = [2, 3, 4, 5]
    r = reasons_for(dq.customers_rules(f), f)
    assert r[0] == ""
    assert "MALFORMED_CUSTOMER_STATE" in r[1]
    assert "MALFORMED_CUSTOMER_CITY" in r[2]
    assert "MISSING_CUSTOMER_UNIQUE_ID" in r[3]


def test_order_item_rules():
    from conftest import IC, item
    f = pd.DataFrame([item("o1", 1), item("o1", 2, price="-3"), item("o1", 3, freight="-1"),
                      item("o1", 4, seller=""), item("zz", 1)], columns=IC)
    f["source_row_number"] = range(2, 7)
    r = reasons_for(dq.order_items_rules(f, {"o1"}), f)
    assert r[0] == "" and "NEGATIVE_PRICE" in r[1] and "NEGATIVE_FREIGHT_VALUE" in r[2]
    assert "MISSING_SELLER_ID" in r[3] and "ORPHAN_ORDER_ID" in r[4]


def test_evaluate_counts_rule_results():
    f = df(a=["x", "", ""])
    _, res = dq.evaluate(f, [dq.required(f, "a")])
    assert (res[0].rows_evaluated, res[0].rows_failed) == (3, 2)


def test_null_profile_counts():
    f = df(a=["x", "", " "], b=["1", "2", "3"])
    assert dq.null_profile(f, ["a", "b"]) == [("a", 2, 3), ("b", 0, 3)]


def test_quality_score_formula():
    rows = [("completeness", 100, 10), ("completeness", 100, 0), ("validity", 50, 5), ("uniqueness", 10, 0), ("referential", 20, 2)]
    s = dq.quality_scores(rows)
    assert s["completeness"][0] == pytest.approx(1 - 10 / 200)
    assert s["validity"][0] == pytest.approx(0.9)
    assert s["overall"][0] == pytest.approx((0.95 + 0.9 + 1.0 + 0.9) / 4)   # unweighted mean of dimensions
