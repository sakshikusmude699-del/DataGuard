"""Read-only DuckDB access for the dashboard. Short-lived connections so the pipeline can write concurrently."""
import os
import sys
from pathlib import Path
import duckdb
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import DB_PATH  # noqa: E402


def db_path() -> str:
    return os.environ.get("DATAGUARD_DB", str(DB_PATH))


class DatabaseUnavailable(Exception):
    pass


@st.cache_data(ttl=60, show_spinner=False)
def q(sql: str, params: tuple = (), _path: str | None = None) -> pd.DataFrame:
    path = _path or db_path()
    if not Path(path).exists():
        raise DatabaseUnavailable(f"Database not found at {path}. Run: python scripts/run_pipeline.py")
    con = duckdb.connect(path, read_only=True)     # dashboard never writes
    try:
        return con.execute(sql, list(params)).df()
    except duckdb.CatalogException as e:
        raise DatabaseUnavailable(f"Expected table is missing ({e}). Run the pipeline first.") from e
    finally:
        con.close()


def runs() -> pd.DataFrame:
    return q("SELECT * FROM audit.pipeline_runs ORDER BY start_time DESC")
