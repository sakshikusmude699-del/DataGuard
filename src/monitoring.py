"""Structured (JSON) logging and audit.pipeline_runs bookkeeping."""
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .config import LOG_DIR, RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_run_id() -> str:
    return f"run_{utcnow():%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"


class _JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"ts": utcnow().isoformat(), "level": record.levelname, "event": record.getMessage()}
        payload.update(getattr(record, "ctx", {}))
        return json.dumps(payload, default=str)


def get_logger(log_dir=LOG_DIR) -> logging.Logger:
    logger = logging.getLogger("dataguard")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handlers = [logging.StreamHandler()]
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(Path(log_dir) / "pipeline.log"))
        except OSError:
            pass
        for h in handlers:
            h.setFormatter(_JsonFormatter())
            logger.addHandler(h)
        logger.propagate = False
    return logger


def log(event: str, level=logging.INFO, **ctx):
    get_logger().log(level, event, extra={"ctx": ctx})


def start_run(con, run_id, data_source):
    con.execute("INSERT INTO audit.pipeline_runs (run_id, start_time, execution_status, data_source) "
                "VALUES (?, ?, 'RUNNING', ?)", [run_id, utcnow(), data_source])


def finish_run(con, run_id, status, started_monotonic, counts=None, failure_reason=None, recon_status=None):
    counts = counts or {}
    con.execute("""UPDATE audit.pipeline_runs SET end_time=?, execution_status=?, input_count=?, bronze_count=?,
        silver_count=?, gold_count=?, rejected_count=?, duplicate_count=?, execution_duration=?,
        failure_reason=?, reconciliation_status=? WHERE run_id=?""",
                [utcnow(), status, counts.get("input"), counts.get("bronze"), counts.get("silver"),
                 counts.get("gold"), counts.get("rejected"), counts.get("duplicates"),
                 round(time.monotonic() - started_monotonic, 3), failure_reason, recon_status, run_id])


def retry(fn, attempts=RETRY_ATTEMPTS, backoff=RETRY_BACKOFF_SECONDS, transient=(OSError,)):
    """Retry only on transient exception types; logic errors (validation, reconciliation) fail fast."""
    for i in range(1, attempts + 1):
        try:
            return fn()
        except transient as e:
            if i == attempts:
                raise
            log("retrying_after_transient_error", level=logging.WARNING, attempt=i, error=str(e))
            time.sleep(backoff * i)
