# Design decisions

**DuckDB.** Embedded, columnar, full SQL with transactions and `MERGE INTO`; zero infrastructure and reproducible with `pip install`. Trade-off: single writer, not a shared warehouse.
**Pandas.** Row-level validation produces one reason string per row and vectorises well at this scale (hundreds of thousands of rows). Heavy set-based work (MERGE, Gold) stays in SQL. Trade-off: data is held in memory.
**Medallion.** Bronze lets any rejection be re-examined against the untouched source; Silver is the single trusted place; Gold is disposable and rebuilt, so a Gold bug never needs a data fix.

**Bronze is all text.** A malformed date or `-5.00` must survive ingestion so it can be reported, not crash a typed load. Typing happens in Silver.
**Rejected vs legitimate.** Rules reject only what is provably wrong. A blank delivery date is valid unless the status is `delivered`. Statuses and case: `" Delivered "` is trimmed and lower-cased, not rejected.
**Duplicates.** Deterministic: first occurrence by `source_row_number` wins within a batch; the rest are quarantined, never discarded. Across batches a key is an upsert.
**Idempotency.** Identity is the content hash of the file, plus PKs and MERGE at every layer. Renaming a file does not fool it; changing a byte makes it a new file.
**Out-of-order data.** `status_rank` prevents a stale record from moving an order backwards. Equal rank allows an update (corrections win).
**Quarantine stores raw values**, not the cleaned ones, so the record can be fixed at source. A row failing several rules is stored once with all reasons.
**Partial failure.** One transaction for Silver + quarantine + Gold + reconciliation + metrics. DuckDB DDL is transactional, so even `CREATE OR REPLACE` of Gold rolls back. Bronze commits separately on purpose: raw data is never lost.
**Reconciliation is a gate.** A mismatch aborts the run instead of publishing a number that cannot be trusted.
**Retries.** Only `OSError` (transient I/O) is retried. Validation or reconciliation errors are deterministic and retrying would hide bugs.
**Quality score.** Rule-level pass rates averaged per dimension, then an unweighted mean of four dimensions. Simple to explain; the unweighted mean is a choice, not a law.

## Defects found and fixed during development (pinned in tests/test_regression.py and test_ingestion.py)
1. `fetchone()` left DuckDB 2.0 results open and caused `ResourceInUseException`; all scalar reads now use `fetchall()`.
2. pandas treated an over-long CSV row as an implicit index and did not raise; an explicit field-count scan was added.
3. Status case/whitespace was validated before normalisation, rejecting `" Delivered "`; normalisation now precedes validation.
4. Quarantine stored trimmed values rather than the original; it now stores the raw Bronze values.
5. Row-wise `apply(axis=1)` for `record_id` was the top cost at 100k orders; vectorised (README section 16).

## Trade-offs
Full Gold rebuild over incremental; manual backfill over a scheduler; in-memory FK sets over joins (simpler, adequate here); unweighted score over a tuned one.
