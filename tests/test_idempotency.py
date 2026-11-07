"""Reliability: reruns, upserts, late-arriving and out-of-order data."""
import shutil
from conftest import cust, item, order, write_csv


def counts(query):
    return {t: query(f"SELECT count(*) FROM {t}")[0][0] for t in
            ("bronze.orders_raw", "silver.orders_clean", "silver.order_items_clean", "silver.customers_clean",
             "audit.rejected_orders", "gold.fact_orders")}


def test_same_files_twice_is_skipped_and_changes_nothing(run, raw_dir, query):
    first = run(raw_dir); before = counts(query)
    second = run(raw_dir)
    assert first.status == "SUCCESS" and second.status == "SKIPPED_NO_NEW_DATA"
    assert counts(query) == before


def test_forced_reprocess_creates_no_duplicates(run, raw_dir, query):
    run(raw_dir); before = counts(query)
    again = run(raw_dir, force=True)
    assert again.status == "SUCCESS" and counts(query) == before


def test_renamed_copy_of_same_content_is_still_skipped(run, raw_dir, tmp_path):
    run(raw_dir)
    copy = tmp_path / "copy"; shutil.copytree(raw_dir, copy)
    assert run(copy).status == "SKIPPED_NO_NEW_DATA"        # identity = content hash, not path


def test_redelivered_key_with_new_values_is_upserted_not_duplicated(run, tmp_path, query):
    d1 = tmp_path / "b1"; d2 = tmp_path / "b2"
    for d, status, deliv in ((d1, "shipped", ""), (d2, "delivered", "2018-01-05 10:00:00")):
        write_csv(d, "customers", [cust("c1", "u1")])
        write_csv(d, "orders", [order("o1", "c1", status=status, delivered=deliv)])
        write_csv(d, "order_items", [item("o1", 1)])
    run(d1); run(d2)
    assert query("SELECT count(*), max(order_status) FROM silver.orders_clean") == [(1, "delivered")]


def test_out_of_order_older_status_does_not_regress_order(run, tmp_path, query):
    d1 = tmp_path / "b1"; d2 = tmp_path / "b2"
    for d, status, deliv in ((d1, "delivered", "2018-01-05 10:00:00"), (d2, "shipped", "")):
        write_csv(d, "customers", [cust("c1", "u1")])
        write_csv(d, "orders", [order("o1", "c1", status=status, delivered=deliv)])
        write_csv(d, "order_items", [item("o1", 1)])
    run(d1); run(d2)       # stale 'shipped' record arrives AFTER 'delivered'
    assert query("SELECT order_status FROM silver.orders_clean")[0][0] == "delivered"


def test_late_arriving_parent_then_backfill_recovers_orphans(run, tmp_path, query):
    late = tmp_path / "b1"
    write_csv(late, "customers", [cust("c1", "u1")])
    write_csv(late, "orders", [order("o1", "c1")])
    write_csv(late, "order_items", [item("o1", 1), item("o2", 1)])      # o2's order has not arrived yet
    run(late)
    assert query("SELECT count(*) FROM silver.order_items_clean")[0][0] == 1
    assert query("SELECT rejection_reason FROM audit.rejected_order_items")[0][0] == "ORPHAN_ORDER_ID"
    arrive = tmp_path / "b2"                                             # parent order arrives late
    write_csv(arrive, "customers", [cust("c1", "u1")])
    write_csv(arrive, "orders", [order("o2", "c1")])
    write_csv(arrive, "order_items", [item("o1", 1), item("o2", 1)])    # items file re-sent (different hash? same content as b1 -> use force)
    run(arrive, force=True)
    assert query("SELECT count(*) FROM silver.order_items_clean")[0][0] == 2
    assert query("SELECT count(*) FROM silver.orders_clean")[0][0] == 2
    assert query("SELECT count(*) FROM audit.rejected_order_items")[0][0] == 0   # backfill cleared the quarantine


def test_new_file_content_is_processed_alongside_skipped_files(run, tmp_path, query):
    d = tmp_path / "b1"
    write_csv(d, "customers", [cust("c1", "u1")]); write_csv(d, "orders", [order("o1", "c1")]); write_csv(d, "order_items", [item("o1", 1)])
    run(d)
    write_csv(d, "orders", [order("o1", "c1"), order("o2", "c1")]); write_csv(d, "order_items", [item("o1", 1), item("o2", 1)])
    r = run(d)       # customers unchanged (skipped); orders + items changed (processed)
    assert r.status == "SUCCESS" and query("SELECT count(*) FROM silver.orders_clean")[0][0] == 2
    assert query("SELECT count(*) FROM silver.customers_clean")[0][0] == 1
