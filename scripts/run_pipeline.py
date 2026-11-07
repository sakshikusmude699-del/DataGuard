"""CLI: python scripts/run_pipeline.py [--raw-dir DIR] [--db PATH] [--force]"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import DB_PATH, RAW_DIR
from src.pipeline import run_pipeline

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=str(RAW_DIR)); p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--force", action="store_true", help="re-process files already processed (backfill)")
    p.add_argument("--data-source", default="kaggle")
    a = p.parse_args()
    s = run_pipeline(a.db, a.raw_dir, force=a.force, data_source=a.data_source)
    print(s)
