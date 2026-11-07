"""Smoke tests: every dashboard page renders against a real (temporary) DuckDB without exceptions."""
import os
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app" / "app.py")
PAGES = ["pages/overview.py", "pages/data_quality.py", "pages/rejected.py", "pages/monitoring.py", "pages/explorer.py"]


@pytest.fixture
def populated(run, raw_dir, db_path, monkeypatch):
    run(raw_dir)
    monkeypatch.setenv("DATAGUARD_DB", str(db_path))
    import streamlit as st
    st.cache_data.clear()
    return db_path


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_data(populated, page):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.switch_page(page).run()
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("page", PAGES)
def test_page_shows_clear_error_when_database_missing(tmp_path, monkeypatch, page):
    monkeypatch.setenv("DATAGUARD_DB", str(tmp_path / "missing.duckdb"))
    import streamlit as st
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.switch_page(page).run()
    assert not at.exception and any("not found" in e.value for e in at.error)


def test_overview_numbers_come_from_database(populated, query):
    at = AppTest.from_file(APP, default_timeout=60).run()
    html = " ".join(m.value for m in at.markdown)
    source = query("SELECT sum(source_rows) FROM audit.table_run_stats")[0][0]
    assert f"{source:,}" in html


def test_dashboard_connection_is_read_only(populated):
    import duckdb
    con = duckdb.connect(str(populated), read_only=True)
    with pytest.raises(duckdb.Error):
        con.execute("DELETE FROM silver.orders_clean")
