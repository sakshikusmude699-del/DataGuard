import csv
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import TABLES  # noqa: E402

EXPECTED_DIR = Path(__file__).resolve().parent.parent / "data" / "expected"
OC = TABLES["orders"]["columns"]; CC = TABLES["customers"]["columns"]; IC = TABLES["order_items"]["columns"]


def write_csv(directory: Path, table: str, rows, columns=None):
    directory.mkdir(parents=True, exist_ok=True)
    columns = columns or TABLES[table]["columns"]
    with open(directory / TABLES[table]["filename"], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(columns); w.writerows(rows)


def order(oid, cid, status="delivered", purchase="2018-01-01 10:00:00", approved="2018-01-01 11:00:00",
          carrier="2018-01-02 10:00:00", delivered="2018-01-05 10:00:00", est="2018-01-10 10:00:00"):
    return [oid, cid, status, purchase, approved, carrier, delivered, est]


def item(oid, n, price="10.00", freight="1.00", seller="s1", product="p1"):
    return [oid, str(n), product, seller, "2018-01-03 10:00:00", price, freight]


def cust(cid, uid, state="SP", city="sao paulo", zip_="01000"):
    return [cid, uid, zip_, city, state]


def build_small_dataset(directory: Path):
    """Known-answer fixture. Expected results live in data/expected/small_fixture_expected.json."""
    customers = [cust("c1", "u1"), cust("c2", "u1"), cust("c3", "u2", "RJ", "rio"),
                 cust("c4", "u3", state="S"),           # malformed state
                 cust("c3", "u2", "RJ", "rio")]         # duplicate customer_id
    orders = [order("o1", "c1"),
              order("o2", "c2", purchase="2018-01-02 10:00:00", delivered="2018-02-01 10:00:00", est="2018-01-20 10:00:00"),
              order("o3", "c3", status="shipped", delivered=""),   # legitimately no delivery date
              order("o4", "cX"),                                    # orphan customer
              order("o5", "c1", status="bogus"),
              order("o6", "c1", delivered="2017-12-01 10:00:00"),   # delivered before purchase
              order("o1", "c1"),                                    # duplicate order_id
              order("o7", "c1", delivered="")]                      # 'delivered' without a date
    items = [item("o1", 1, "100.00", "10.00"), item("o1", 2, "50.00", "5.00"), item("o2", 1, "200.00", "20.00"),
             item("o3", 1, "30.00", "3.00"), item("o3", 1, "30.00", "3.00"),   # duplicate composite key
             item("o9", 1),                                                     # orphan order
             item("o1", 3, price="-5.00"), item("o2", 2, seller="")]
    write_csv(directory, "customers", customers)
    write_csv(directory, "orders", orders)
    write_csv(directory, "order_items", items)
    return directory


@pytest.fixture
def expected():
    return json.loads((EXPECTED_DIR / "small_fixture_expected.json").read_text())


@pytest.fixture
def raw_dir(tmp_path):
    return build_small_dataset(tmp_path / "raw")


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.duckdb"   # isolated temporary DB, never the project DB


@pytest.fixture
def report_dir(tmp_path):
    return tmp_path / "reports"


@pytest.fixture
def run(db_path, report_dir):
    from src.pipeline import run_pipeline
    def _run(raw, **kw):
        return run_pipeline(db_path, raw, report_dir=report_dir, data_source="test", **kw)
    return _run


@pytest.fixture
def query(db_path):
    import duckdb
    def _q(sql, params=None):
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            return con.execute(sql, params or []).fetchall()
        finally:
            con.close()
    return _q
