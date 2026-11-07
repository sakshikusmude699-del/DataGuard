import duckdb
import pytest
from datetime import datetime
from conftest import cust, order, write_csv
from src.database import init_schema
from src.ingestion import IngestionError, file_sha256, load_bronze, read_source


def test_read_source_keeps_raw_text_and_row_numbers(tmp_path):
    write_csv(tmp_path, "customers", [cust("c1", "u1", zip_="01000"), cust("c2", "u2")])
    df, schema = read_source(tmp_path / "olist_customers_dataset.csv", "customers")
    assert schema.status == "PASS"
    assert df["customer_zip_code_prefix"].iloc[0] == "01000"      # leading zero preserved (no int coercion)
    assert list(df["source_row_number"]) == [2, 3]


def test_empty_file_rejected(tmp_path):
    (tmp_path / "olist_orders_dataset.csv").write_text("")
    with pytest.raises(IngestionError):
        read_source(tmp_path / "olist_orders_dataset.csv", "orders")


def test_header_only_file_rejected(tmp_path):
    write_csv(tmp_path, "orders", [])
    with pytest.raises(IngestionError):
        read_source(tmp_path / "olist_orders_dataset.csv", "orders")


def test_malformed_csv_rejected(tmp_path):
    p = tmp_path / "olist_customers_dataset.csv"
    p.write_text("customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_state\n"
                 "c1,u1,1,city,SP,EXTRA,FIELDS\n")
    with pytest.raises(IngestionError):
        read_source(p, "customers")


def test_missing_required_columns_reported_not_raised(tmp_path):
    write_csv(tmp_path, "customers", [["c1", "u1"]], columns=["customer_id", "customer_unique_id"])
    df, schema = read_source(tmp_path / "olist_customers_dataset.csv", "customers")
    assert df is None and schema.status == "FAIL" and "customer_state" in schema.missing


def test_unexpected_columns_preserved_as_json(tmp_path):
    cols = ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state", "new_col"]
    write_csv(tmp_path, "customers", [cust("c1", "u1") + ["hello"]], columns=cols)
    df, schema = read_source(tmp_path / "olist_customers_dataset.csv", "customers")
    assert schema.status == "WARN"
    assert "hello" in df["_extra_json"].iloc[0]


def test_bronze_load_is_idempotent(tmp_path):
    write_csv(tmp_path, "orders", [order("o1", "c1"), order("o2", "c1")])
    p = tmp_path / "olist_orders_dataset.csv"
    df, _ = read_source(p, "orders")
    con = duckdb.connect(":memory:"); init_schema(con)
    h = file_sha256(p)
    for _ in range(2):
        n = load_bronze(con, "orders", df, p.name, h, "run1", datetime(2024, 1, 1))
    assert n == 2
    assert con.execute("SELECT count(*) FROM bronze.orders_raw").fetchall()[0][0] == 2


def test_bronze_records_lineage(tmp_path):
    write_csv(tmp_path, "orders", [order("o1", "c1")])
    p = tmp_path / "olist_orders_dataset.csv"
    df, _ = read_source(p, "orders")
    con = duckdb.connect(":memory:"); init_schema(con)
    load_bronze(con, "orders", df, p.name, file_sha256(p), "runX", datetime(2024, 1, 1))
    row = con.execute("SELECT source_file, run_id, source_row_number, ingestion_timestamp FROM bronze.orders_raw").fetchall()[0]
    assert row == ("olist_orders_dataset.csv", "runX", 2, datetime(2024, 1, 1))
