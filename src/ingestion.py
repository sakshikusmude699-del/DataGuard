"""CSV -> Bronze. Everything is read as text so malformed values can be diagnosed later."""
import csv
import hashlib
import json
from datetime import datetime
import pandas as pd
from .config import TABLES
from .schema_validation import validate_columns


class IngestionError(Exception):
    """Unreadable, empty or malformed source file."""


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_field_counts(path) -> None:
    """pandas silently turns over-long rows into an implicit index, so verify field counts explicitly."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            width = len(next(reader))
            for row in reader:
                if row and len(row) != width:
                    raise IngestionError(f"{path}: malformed CSV at line {reader.line_num}: "
                                         f"expected {width} fields, found {len(row)}")
    except (csv.Error, UnicodeDecodeError) as e:
        raise IngestionError(f"{path}: malformed CSV: {e}") from e


def read_source(path, table: str):
    """Return (dataframe_of_expected_columns | None, SchemaResult). Raises IngestionError on bad files."""
    spec = TABLES[table]
    try:
        header = pd.read_csv(path, nrows=0, dtype=str)
    except pd.errors.EmptyDataError as e:
        raise IngestionError(f"{path}: file is empty") from e
    except (pd.errors.ParserError, UnicodeDecodeError) as e:
        raise IngestionError(f"{path}: malformed CSV header: {e}") from e
    schema = validate_columns(table, list(header.columns), spec["columns"])
    if schema.status == "FAIL":
        return None, schema
    _check_field_counts(path)
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False,
                         on_bad_lines="error", encoding="utf-8", index_col=False)
    except (pd.errors.ParserError, UnicodeDecodeError) as e:
        raise IngestionError(f"{path}: malformed CSV: {e}") from e
    if df.empty:
        raise IngestionError(f"{path}: contains a header but no data rows")
    df.columns = [c.strip() for c in df.columns]
    df = df.fillna("")
    df["source_row_number"] = range(2, len(df) + 2)  # header is line 1
    if schema.unexpected:
        extras = df[schema.unexpected].to_dict(orient="records")
        df["_extra_json"] = [json.dumps(e, ensure_ascii=False) for e in extras]
    else:
        df["_extra_json"] = None
    return df[spec["columns"] + ["_extra_json", "source_row_number"]], schema


def load_bronze(con, table: str, df: pd.DataFrame, source_file: str, file_hash: str,
                run_id: str, now: datetime) -> int:
    """Append to Bronze. PK (file_hash, row) + ON CONFLICT DO NOTHING makes this idempotent."""
    spec = TABLES[table]
    batch = df.copy()
    batch["source_file"], batch["source_file_hash"] = source_file, file_hash
    batch["ingestion_timestamp"], batch["run_id"] = now, run_id
    cols = spec["columns"] + ["_extra_json", "source_file", "source_file_hash",
                              "source_row_number", "ingestion_timestamp", "run_id"]
    con.register("bronze_batch", batch[cols])
    try:
        con.execute(f"INSERT INTO {spec['bronze']} ({', '.join(cols)}) "
                    f"SELECT {', '.join(cols)} FROM bronze_batch ON CONFLICT DO NOTHING")
    finally:
        con.unregister("bronze_batch")
    return con.execute(f"SELECT count(*) FROM {spec['bronze']} WHERE source_file_hash=?",
                       [file_hash]).fetchall()[0][0]


def read_bronze(con, table: str, file_hash: str) -> pd.DataFrame:
    spec = TABLES[table]
    cols = spec["columns"] + ["source_file", "source_file_hash", "source_row_number"]
    return con.execute(f"SELECT {', '.join(cols)} FROM {spec['bronze']} "
                       "WHERE source_file_hash=? ORDER BY source_row_number", [file_hash]).df()
