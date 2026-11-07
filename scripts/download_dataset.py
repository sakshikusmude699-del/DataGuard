"""Download the Olist dataset from Kaggle (needs credentials) or verify files placed manually.

  python scripts/download_dataset.py            # try Kaggle CLI/API, else print manual steps
  python scripts/download_dataset.py --verify   # only profile files already in data/raw/
"""
import argparse, csv, json, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import PROCESS_ORDER, RAW_DIR, TABLES

SLUG = "olistbr/brazilian-ecommerce"
MANUAL = f"""
Kaggle credentials were not available, so the dataset was NOT downloaded (and nothing was fabricated).

Manual download:
  1. Sign in at https://www.kaggle.com/datasets/{SLUG} and click Download (zip).
  2. Unzip it and copy these three files into:  {RAW_DIR}
       olist_orders_dataset.csv
       olist_customers_dataset.csv
       olist_order_items_dataset.csv
  3. Re-run:  python scripts/download_dataset.py --verify

Or enable the API: create a token at https://www.kaggle.com/settings (Create New Token), save kaggle.json to
~/.kaggle/kaggle.json (chmod 600) or set KAGGLE_USERNAME / KAGGLE_KEY, `pip install kaggle`, and re-run this script.
"""


def profile(directory: Path):
    out, ok = {}, True
    for t in PROCESS_ORDER:
        p = directory / TABLES[t]["filename"]
        if not p.exists():
            print(f"MISSING  {p}"); ok = False; continue
        with open(p, newline="", encoding="utf-8") as f:
            r = csv.reader(f); header = next(r); rows = sum(1 for _ in r)
        missing = [c for c in TABLES[t]["columns"] if c not in header]
        out[TABLES[t]["filename"]] = {"rows": rows, "columns": header, "missing_required_columns": missing}
        print(f"{'OK     ' if not missing else 'BAD    '} {p.name}: {rows:,} rows, {len(header)} columns" + (f", missing {missing}" if missing else ""))
        ok &= not missing
    if ok:
        (directory / "dataset_profile.json").write_text(json.dumps(out, indent=2))
        print(f"Profile written to {directory / 'dataset_profile.json'}")
    return ok


def try_kaggle(dest: Path) -> bool:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, "-m", "kaggle", "datasets", "download", "-d", SLUG, "-p", tmp],
                               capture_output=True, text=True, timeout=600)
            if r.returncode:
                print(r.stderr.strip()[-300:]); return False
            z = next(Path(tmp).glob("*.zip"))
            dest.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(z) as zf:
                for t in PROCESS_ORDER:
                    zf.extract(TABLES[t]["filename"], dest)
        return True
    except (StopIteration, KeyError, subprocess.SubprocessError, OSError) as e:
        print(f"Kaggle download failed: {e}"); return False


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--verify", action="store_true"); ap.add_argument("--dir", default=str(RAW_DIR))
    a = ap.parse_args(); d = Path(a.dir)
    if a.verify:
        sys.exit(0 if profile(d) else 1)
    if try_kaggle(d):
        sys.exit(0 if profile(d) else 1)
    print(MANUAL); sys.exit(2)
