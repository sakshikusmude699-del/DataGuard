"""Benchmark the pipeline on synthetic data. Every number printed is measured, none are hardcoded.

Stage timings are derived from the pipeline's own stage hooks (no pipeline changes needed):
  read+schema   : start -> 'bronze' hook
  bronze load   : 'bronze' -> first silver hook
  silver        : first silver hook -> 'gold' hook   (validation + quarantine + MERGE)
  gold          : 'gold' -> 'reconciliation' hook
  recon+metrics : 'reconciliation' hook -> end
Peak memory is ru_maxrss of a fresh subprocess per size.
"""
import argparse, json, resource, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run_one(n_orders: int, seed: int):
    from scripts.generate_data import generate
    from src.pipeline import run_pipeline
    with tempfile.TemporaryDirectory() as tmp:
        raw, _ = generate(n_orders, Path(tmp) / "raw", seed=seed)
        marks = {}
        def hook(stage):
            marks.setdefault(stage if not stage.startswith("silver") else "silver_first", time.perf_counter())
            if stage.startswith("silver"):
                marks["silver_last"] = time.perf_counter()
        t0 = time.perf_counter()
        s = run_pipeline(Path(tmp) / "b.duckdb", raw, report_dir=Path(tmp) / "rep", data_source="synthetic", fault_hook=hook)
        t1 = time.perf_counter()
        return {"orders": n_orders, "input_rows": s.counts["input"], "read_schema_s": marks["bronze"] - t0,
                "bronze_load_s": marks["silver_first"] - marks["bronze"], "silver_s": marks["gold"] - marks["silver_first"],
                "gold_s": marks["reconciliation"] - marks["gold"], "recon_metrics_s": t1 - marks["reconciliation"],
                "total_s": t1 - t0, "rows_per_s": s.counts["input"] / (t1 - t0),
                "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, "status": s.status}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--orders", type=int, nargs="+", default=[1000, 10000, 100000]); p.add_argument("--seed", type=int, default=42)
    p.add_argument("--child", type=int); p.add_argument("--out", default="reports/benchmark.json")
    a = p.parse_args()
    if a.child:
        print(json.dumps(run_one(a.child, a.seed))); sys.exit()
    results = []
    for n in a.orders:
        out = subprocess.run([sys.executable, __file__, "--child", str(n), "--seed", str(a.seed)], capture_output=True, text=True,
                             cwd=Path(__file__).resolve().parent.parent)
        if out.returncode: print(out.stderr[-800:]); sys.exit(1)
        results.append(json.loads(out.stdout.strip().splitlines()[-1]))
    Path(a.out).write_text(json.dumps(results, indent=2))
    hdr = f"{'orders':>8} {'rows':>9} {'read':>7} {'bronze':>7} {'silver':>7} {'gold':>6} {'recon':>6} {'total':>7} {'rows/s':>9} {'RSS MB':>7}"
    print(hdr)
    for r in results:
        print(f"{r['orders']:>8} {r['input_rows']:>9} {r['read_schema_s']:>7.2f} {r['bronze_load_s']:>7.2f} {r['silver_s']:>7.2f} "
              f"{r['gold_s']:>6.2f} {r['recon_metrics_s']:>6.2f} {r['total_s']:>7.2f} {r['rows_per_s']:>9.0f} {r['peak_rss_mb']:>7.0f}")
