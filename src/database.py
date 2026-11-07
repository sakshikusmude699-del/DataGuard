"""DuckDB connection + DDL for bronze / silver / gold / audit schemas."""
from pathlib import Path
import duckdb
from .config import TABLES


def connect(path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path = str(path)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(path, read_only=read_only)


_LINEAGE = "source_file VARCHAR, source_file_hash VARCHAR, source_row_number BIGINT"


def _bronze_ddl(spec):
    cols = ", ".join(f"{c} VARCHAR" for c in spec["columns"])
    return (f"CREATE TABLE IF NOT EXISTS {spec['bronze']} ({cols}, _extra_json VARCHAR, {_LINEAGE}, "
            "ingestion_timestamp TIMESTAMP, run_id VARCHAR, "
            "PRIMARY KEY (source_file_hash, source_row_number))")


def _rejected_ddl(spec):
    cols = ", ".join(f"{c} VARCHAR" for c in spec["columns"])
    return (f"CREATE TABLE IF NOT EXISTS {spec['rejected']} (record_id VARCHAR, {cols}, {_LINEAGE}, "
            "run_id VARCHAR, rejection_reason VARCHAR, rejection_timestamp TIMESTAMP, "
            "PRIMARY KEY (source_file_hash, source_row_number))")


SILVER_DDL = [
    """CREATE TABLE IF NOT EXISTS silver.customers_clean (
        customer_id VARCHAR PRIMARY KEY, customer_unique_id VARCHAR NOT NULL,
        customer_zip_code_prefix VARCHAR, customer_city VARCHAR, customer_state VARCHAR,
        source_file VARCHAR, source_row_number BIGINT, run_id VARCHAR, processed_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS silver.orders_clean (
        order_id VARCHAR PRIMARY KEY, customer_id VARCHAR NOT NULL, order_status VARCHAR NOT NULL,
        status_rank INTEGER, order_purchase_timestamp TIMESTAMP NOT NULL, order_approved_at TIMESTAMP,
        order_delivered_carrier_date TIMESTAMP, order_delivered_customer_date TIMESTAMP,
        order_estimated_delivery_date TIMESTAMP,
        source_file VARCHAR, source_row_number BIGINT, run_id VARCHAR, processed_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS silver.order_items_clean (
        order_id VARCHAR NOT NULL, order_item_id INTEGER NOT NULL, product_id VARCHAR NOT NULL,
        seller_id VARCHAR NOT NULL, shipping_limit_date TIMESTAMP, price DECIMAL(12,2) NOT NULL,
        freight_value DECIMAL(12,2) NOT NULL,
        source_file VARCHAR, source_row_number BIGINT, run_id VARCHAR, processed_at TIMESTAMP,
        PRIMARY KEY (order_id, order_item_id))""",
]

AUDIT_DDL = [
    """CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
        run_id VARCHAR PRIMARY KEY, start_time TIMESTAMP, end_time TIMESTAMP, execution_status VARCHAR,
        input_count BIGINT, bronze_count BIGINT, silver_count BIGINT, gold_count BIGINT,
        rejected_count BIGINT, duplicate_count BIGINT, execution_duration DOUBLE,
        failure_reason VARCHAR, data_source VARCHAR, reconciliation_status VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS audit.processed_files (
        file_hash VARCHAR PRIMARY KEY, table_name VARCHAR, source_file VARCHAR, run_id VARCHAR,
        row_count BIGINT, processed_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS audit.schema_checks (
        run_id VARCHAR, table_name VARCHAR, status VARCHAR, missing_columns VARCHAR,
        unexpected_columns VARCHAR, checked_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS audit.table_run_stats (
        run_id VARCHAR, table_name VARCHAR, source_rows BIGINT, bronze_rows BIGINT, valid_rows BIGINT,
        rejected_rows BIGINT, duplicate_rows BIGINT)""",
    """CREATE TABLE IF NOT EXISTS audit.rule_results (
        run_id VARCHAR, table_name VARCHAR, rule_name VARCHAR, dimension VARCHAR,
        rows_evaluated BIGINT, rows_failed BIGINT)""",
    """CREATE TABLE IF NOT EXISTS audit.null_profile (
        run_id VARCHAR, table_name VARCHAR, column_name VARCHAR, null_count BIGINT, total_rows BIGINT)""",
    """CREATE TABLE IF NOT EXISTS audit.quality_scores (
        run_id VARCHAR, dimension VARCHAR, score DOUBLE, rows_evaluated BIGINT, rows_failed BIGINT)""",
    """CREATE TABLE IF NOT EXISTS audit.reconciliation (
        run_id VARCHAR, check_name VARCHAR, expected VARCHAR, actual VARCHAR, status VARCHAR)""",
]


def init_schema(con) -> None:
    for s in ("bronze", "silver", "gold", "audit"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
    for spec in TABLES.values():
        con.execute(_bronze_ddl(spec))
        con.execute(_rejected_ddl(spec))
    for ddl in SILVER_DDL + AUDIT_DDL:
        con.execute(ddl)


def table_exists(con, qualified: str) -> bool:
    schema, name = qualified.split(".")
    return con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema=? AND table_name=?",
                       [schema, name]).fetchall()[0][0] > 0
