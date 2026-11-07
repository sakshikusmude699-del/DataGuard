"""Export Gold tables to Parquet (analytics hand-off format).  python scripts/export_parquet.py [--db PATH] [--out DIR]"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import DB_PATH, ROOT
from src.database import connect

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--db", default=str(DB_PATH)); ap.add_argument("--out", default=str(ROOT / "reports" / "parquet"))
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    con = connect(a.db, read_only=True)
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='gold'").fetchall():
        con.execute(f"COPY gold.{t} TO '{out / (t + '.parquet')}' (FORMAT PARQUET)")
        print(f"gold.{t} -> {out / (t + '.parquet')}")
