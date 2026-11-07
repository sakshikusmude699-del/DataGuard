# Test strategy

Isolation: every test uses a temporary DuckDB file and temporary CSVs; the project database is never touched. Known-answer expectations
live in `data/expected/small_fixture_expected.json`, separate from the code that builds the input CSVs. The expected values were computed by hand.

| Category | Files | Examples |
|---|---|---|
| Unit | test_schema_validation, test_data_quality, test_duplicates, test_transformations | rule masks, missing vs invalid timestamp, quality-score formula, duplicate policy determinism |
| Integration | test_medallion, test_integration | CSV -> Bronze -> Silver -> Gold counts and revenue vs expected, persistence after reconnect, audit row complete, report written |
| Negative | test_ingestion, test_integration, test_data_quality | empty/header-only/malformed CSV, missing and unexpected columns, orphans, bad status, negative price, bad dates, duplicate keys |
| Reliability | test_idempotency, test_integration | same files twice, forced reprocess, renamed file, upsert, out-of-order, late parent + backfill, crash at gold/silver then restart, rollback leaves previous Gold intact, transient retry, reconciliation abort |
| Regression | test_regression | shipped order without delivery date stays valid; shared `customer_unique_id`; multi-item order not double counted; leading-zero zip; whitespace |
| Dashboard | test_dashboard | every page renders; missing-DB error; figures come from DB; read-only connection |

Fault injection: `run_pipeline(fault_hook=...)` calls a hook at named stages (`bronze`, `silver:<table>`, `gold`, `reconciliation`) so tests crash the pipeline deterministically.
Coverage is a diagnostic, not a goal; the uncovered lines are defensive branches (OS errors, logger fallback). Evidence: `reports/test_results.txt`.
Not tested: real Olist data, very large files, concurrent writers, browser rendering (only Streamlit's AppTest).
