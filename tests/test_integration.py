import json
import duckdb
import pytest
from conftest import cust, item, order, write_csv
from src import reconciliation
from src.ingestion import IngestionError
from src.pipeline import PipelineError, run_pipeline
from src.schema_validation import SchemaValidationError


def test_full_pipeline_persists_and_reconciles(run, raw_dir, query, expected, report_dir):
    s = run(raw_dir)
    assert s.status == "SUCCESS" and s.reconciliation_status == "PASS"
    assert s.counts["input"] == sum(expected["source_rows"].values())
    assert s.counts["silver"] == sum(expected["valid_rows"].values())
    assert s.counts["rejected"] == sum(expected["rejected_rows"].values())
    assert s.counts["gold"] == expected["gold"]["fact_orders_rows"]
    assert query("SELECT count(*) FROM audit.reconciliation WHERE status='FAIL'")[0][0] == 0
    assert (report_dir / f"quality_report_{s.run_id}.json").exists()
    rep = json.loads((report_dir / f"quality_report_{s.run_id}.json").read_text())
    assert {q["dimension"] for q in rep["quality_scores"]} == {"completeness", "validity", "uniqueness", "referential", "overall"}


def test_pipeline_runs_audit_row_is_complete(run, raw_dir, query):
    s = run(raw_dir)
    row = query("SELECT execution_status, start_time, end_time, input_count, bronze_count, silver_count, gold_count, "
                "rejected_count, duplicate_count, execution_duration, failure_reason FROM audit.pipeline_runs WHERE run_id=?", [s.run_id])[0]
    assert row[0] == "SUCCESS" and all(v is not None for v in row[1:10]) and row[10] is None


def test_data_survives_connection_restart(run, raw_dir, db_path):
    run(raw_dir)
    con = duckdb.connect(str(db_path), read_only=True)
    assert con.execute("SELECT count(*) FROM gold.fact_orders").fetchall()[0][0] == 3


def test_quality_metrics_are_derived_not_hardcoded(run, raw_dir, query):
    run(raw_dir)
    scores = dict(query("SELECT dimension, score FROM audit.quality_scores"))
    assert 0 < scores["referential"] < 1 and 0 < scores["uniqueness"] < 1 and 0 < scores["overall"] < 1


# ---------------- negative tests -----------------------------------------
def test_missing_input_file(run, tmp_path):
    with pytest.raises(PipelineError):
        run(tmp_path / "nothing_here")


def test_empty_input_file_fails_run_and_is_audited(run, raw_dir, query):
    (raw_dir / "olist_orders_dataset.csv").write_text("")
    with pytest.raises(IngestionError):
        run(raw_dir)
    status, reason = query("SELECT execution_status, failure_reason FROM audit.pipeline_runs")[0]
    assert status == "FAILED" and "empty" in reason
    assert query("SELECT count(*) FROM bronze.customers_raw")[0][0] == 0      # nothing partially loaded


def test_missing_required_column_fails_before_any_write(run, raw_dir, query):
    write_csv(raw_dir, "orders", [["o1", "c1"]], columns=["order_id", "customer_id"])
    with pytest.raises(SchemaValidationError):
        run(raw_dir)
    assert query("SELECT count(*) FROM bronze.orders_raw")[0][0] == 0
    assert query("SELECT status FROM audit.schema_checks WHERE table_name='orders'")[0][0] == "FAIL"


def test_unexpected_column_warns_and_run_succeeds(run, raw_dir, query):
    cols = ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
            "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date", "surprise"]
    write_csv(raw_dir, "orders", [order("o1", "c1") + ["x"]], columns=cols)
    assert run(raw_dir).status == "SUCCESS"
    assert query("SELECT status FROM audit.schema_checks WHERE table_name='orders'")[0][0] == "WARN"
    assert "x" in query("SELECT _extra_json FROM bronze.orders_raw")[0][0]


def test_malformed_csv_fails_run(run, raw_dir):
    (raw_dir / "olist_customers_dataset.csv").write_text(
        "customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_state\nc1,u1,1,x,SP,extra,extra\n")
    with pytest.raises(IngestionError):
        run(raw_dir)


# ---------------- failure / retry / atomicity -----------------------------
def test_failure_before_gold_rolls_back_everything_atomic(run, raw_dir, query):
    def boom(stage):
        if stage == "gold":
            raise RuntimeError("simulated crash")
    with pytest.raises(RuntimeError):
        run(raw_dir, fault_hook=boom)
    assert query("SELECT execution_status, failure_reason FROM audit.pipeline_runs")[0][0] == "FAILED"
    assert query("SELECT count(*) FROM silver.customers_clean")[0][0] == 0          # silver rolled back
    assert query("SELECT count(*) FROM audit.rejected_orders")[0][0] == 0           # quarantine rolled back
    assert query("SELECT count(*) FROM information_schema.tables WHERE table_schema='gold'")[0][0] == 0
    assert query("SELECT count(*) FROM bronze.orders_raw")[0][0] == 8               # raw data preserved
    assert query("SELECT count(*) FROM audit.processed_files")[0][0] == 0           # files NOT marked processed


def test_restart_after_failure_completes_successfully(run, raw_dir, query):
    def boom(stage):
        if stage == "silver:orders":
            raise RuntimeError("crash mid-silver")
    with pytest.raises(RuntimeError):
        run(raw_dir, fault_hook=boom)
    s = run(raw_dir)                                                                 # plain restart, no flags
    assert s.status == "SUCCESS"
    assert query("SELECT count(*) FROM bronze.orders_raw")[0][0] == 8               # bronze not duplicated by restart
    assert query("SELECT count(*) FROM gold.fact_orders")[0][0] == 3


def test_failure_leaves_previous_gold_untouched(run, tmp_path, raw_dir, query):
    run(raw_dir)
    before = query("SELECT count(*), sum(order_value) FROM gold.fact_orders")
    d2 = tmp_path / "b2"
    write_csv(d2, "customers", [cust("c9", "u9")]); write_csv(d2, "orders", [order("o9", "c9")]); write_csv(d2, "order_items", [item("o9", 1)])
    def boom(stage):
        if stage == "reconciliation":
            raise RuntimeError("late failure")
    with pytest.raises(RuntimeError):
        run(d2, fault_hook=boom)
    assert query("SELECT count(*), sum(order_value) FROM gold.fact_orders") == before


def test_transient_error_is_retried(run, raw_dir, monkeypatch):
    import src.monitoring as m
    monkeypatch.setattr(m, "RETRY_BACKOFF_SECONDS", 0)
    calls = {"n": 0}
    def flaky(stage):
        if stage == "gold" and calls["n"] == 0:
            calls["n"] += 1
            raise OSError("transient disk hiccup")
    assert run(raw_dir, fault_hook=flaky).status == "SUCCESS"
    assert calls["n"] == 1


def test_reconciliation_failure_aborts_and_rolls_back(run, raw_dir, query, monkeypatch):
    monkeypatch.setattr(reconciliation, "check_layers", lambda con: [("forced mismatch", 1, 2)])
    with pytest.raises(reconciliation.ReconciliationError):
        run(raw_dir)
    assert query("SELECT count(*) FROM silver.orders_clean")[0][0] == 0
    assert query("SELECT execution_status FROM audit.pipeline_runs")[0][0] == "FAILED"
