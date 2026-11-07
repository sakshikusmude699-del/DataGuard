"""Central pipeline runner.

Stages: validate inputs -> run_id -> Bronze (own tx, raw data always preserved) ->
        ONE atomic tx { Silver MERGE + quarantine + Gold rebuild + reconciliation + metrics }.
Any failure inside the atomic tx rolls everything back: Silver/Gold/audit stay at the previous consistent state.
"""
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from . import ingestion, medallion, monitoring, reconciliation, reporting
from .config import DB_PATH, PROCESS_ORDER, RAW_DIR, REPORTS_DIR, TABLES
from .database import connect, init_schema
from .monitoring import log, utcnow
from .schema_validation import SchemaValidationError, assert_schema


class PipelineError(Exception):
    pass


@dataclass
class RunSummary:
    run_id: str
    status: str
    counts: dict
    reconciliation_status: str | None = None


def validate_inputs(raw_dir: Path):
    paths = {t: Path(raw_dir) / TABLES[t]["filename"] for t in PROCESS_ORDER}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise PipelineError(f"Missing input files: {missing}")
    return paths


def run_pipeline(db_path=DB_PATH, raw_dir=RAW_DIR, force=False, data_source="kaggle",
                 report_dir=REPORTS_DIR, fault_hook=None) -> RunSummary:
    """fault_hook(stage) lets tests inject failures at named stages."""
    hook = fault_hook or (lambda stage: None)
    t0 = time.monotonic()
    con = connect(db_path)
    init_schema(con)
    run_id = monitoring.new_run_id()
    monitoring.start_run(con, run_id, data_source)
    log("run_started", run_id=run_id, data_source=data_source, force=force)
    counts = {"input": 0, "bronze": 0, "silver": 0, "gold": None, "rejected": 0, "duplicates": 0}
    try:
        paths = validate_inputs(Path(raw_dir))
        now = utcnow()

        # 1. Read + schema-validate every file BEFORE writing anything.
        loaded, schema_rows = {}, []
        for t in PROCESS_ORDER:
            df, schema = ingestion.read_source(paths[t], t)
            schema_rows.append(schema)
            loaded[t] = df
        for s in schema_rows:
            con.execute("INSERT INTO audit.schema_checks VALUES (?,?,?,?,?,?)",
                        [run_id, s.table, s.status, ",".join(s.missing), ",".join(s.unexpected), now])
        for s in schema_rows:
            assert_schema(s)
        schema_rows_for_report = []  # already persisted above; don't double-insert

        # 2. Decide what is new (idempotency on file content hash).
        todo = {}
        for t in PROCESS_ORDER:
            h = ingestion.file_sha256(paths[t])
            seen = con.execute("SELECT count(*) FROM audit.processed_files WHERE file_hash=?", [h]).fetchall()[0][0]
            if seen and not force:
                log("file_already_processed_skipped", table=t, file_hash=h)
            else:
                todo[t] = h
        if not todo:
            monitoring.finish_run(con, run_id, "SKIPPED_NO_NEW_DATA", t0, counts)
            log("run_finished", run_id=run_id, status="SKIPPED_NO_NEW_DATA")
            return RunSummary(run_id, "SKIPPED_NO_NEW_DATA", counts)

        # 3. Bronze (own transaction): raw data is kept even if later stages fail.
        hook("bronze")
        bronze_counts = {}
        con.begin()
        try:
            for t in PROCESS_ORDER:
                if t in todo:
                    bronze_counts[t] = ingestion.load_bronze(con, t, loaded[t], paths[t].name, todo[t], run_id, now)
            con.commit()
        except Exception:
            con.rollback(); raise
        counts["input"] = sum(len(loaded[t]) for t in todo)
        counts["bronze"] = sum(bronze_counts.values())

        # 4. Silver + Gold + reconciliation in ONE atomic transaction (with retry on transient errors).
        def atomic():
            con.begin()
            try:
                results, checks = [], []
                for t in PROCESS_ORDER:
                    if t not in todo:
                        continue
                    hook(f"silver:{t}")
                    bronze_df = ingestion.read_bronze(con, t, todo[t])  # Silver is built FROM Bronze
                    res = medallion.process_table(con, t, bronze_df, run_id, now, todo[t])
                    res.bronze_rows = bronze_counts[t]
                    results.append(res)
                    checks += reconciliation.check_batch(t, len(loaded[t]), bronze_counts[t],
                                                         res.valid_rows, res.rejected_rows)
                hook("gold")
                gold_rows = medallion.build_gold(con)
                hook("reconciliation")
                checks += reconciliation.check_layers(con)
                recon = reconciliation.record(con, run_id, checks)
                if recon == "FAIL":
                    failed = [c[0] for c in checks if str(c[1]) != str(c[2])]
                    raise reconciliation.ReconciliationError(f"Reconciliation failed: {failed}")
                reporting.persist_run_metrics(con, run_id, results, schema_rows_for_report, now)
                for t in todo:
                    con.execute("INSERT INTO audit.processed_files VALUES (?,?,?,?,?,?) "
                                "ON CONFLICT (file_hash) DO UPDATE SET run_id=excluded.run_id, processed_at=excluded.processed_at",
                                [todo[t], t, paths[t].name, run_id, len(loaded[t]), now])
                con.commit()
                return results, gold_rows, recon
            except Exception:
                con.rollback(); raise

        results, gold_rows, recon = monitoring.retry(atomic)
        counts.update(silver=sum(r.valid_rows for r in results), gold=gold_rows,
                      rejected=sum(r.rejected_rows for r in results),
                      duplicates=sum(r.duplicate_rows for r in results))
        monitoring.finish_run(con, run_id, "SUCCESS", t0, counts, recon_status=recon)
        reporting.write_report(con, run_id, report_dir)
        log("run_finished", run_id=run_id, status="SUCCESS", **counts)
        return RunSummary(run_id, "SUCCESS", counts, recon)
    except Exception as e:
        status = "FAILED"
        monitoring.finish_run(con, run_id, status, t0, counts, failure_reason=f"{type(e).__name__}: {e}")
        log("run_failed", level=logging.ERROR, run_id=run_id, error=str(e))
        raise
    finally:
        con.close()
