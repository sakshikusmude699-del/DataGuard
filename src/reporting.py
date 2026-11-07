"""Persist per-run quality metrics and write JSON/Markdown quality reports."""
import json
from pathlib import Path
from .config import REPORTS_DIR
from .data_quality import quality_scores


def persist_run_metrics(con, run_id, results, schema_rows, now):
    for r in results:
        s = r  # TableResult
        con.execute("INSERT INTO audit.table_run_stats VALUES (?,?,?,?,?,?,?)",
                    [run_id, s.table, s.source_rows, s.bronze_rows, s.valid_rows, s.rejected_rows, s.duplicate_rows])
        for rr in s.rule_results:
            con.execute("INSERT INTO audit.rule_results VALUES (?,?,?,?,?,?)",
                        [run_id, s.table, rr.rule_name, rr.dimension, rr.rows_evaluated, rr.rows_failed])
        for col, nulls, total in s.null_profile:
            con.execute("INSERT INTO audit.null_profile VALUES (?,?,?,?,?)", [run_id, s.table, col, nulls, total])
    for sr in schema_rows:
        con.execute("INSERT INTO audit.schema_checks VALUES (?,?,?,?,?,?)",
                    [run_id, sr.table, sr.status, ",".join(sr.missing), ",".join(sr.unexpected), now])
    rows = [(rr.dimension, rr.rows_evaluated, rr.rows_failed) for s in results for rr in s.rule_results]
    scores = quality_scores(rows)
    for dim, (score, ev, fl) in scores.items():
        con.execute("INSERT INTO audit.quality_scores VALUES (?,?,?,?,?)", [run_id, dim, score, ev, fl])
    return scores


def write_report(con, run_id, out_dir=REPORTS_DIR):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    q = lambda sql: con.execute(sql, [run_id]).df().to_dict(orient="records")
    report = {
        "run": q("SELECT * FROM audit.pipeline_runs WHERE run_id=?"),
        "table_stats": q("SELECT * FROM audit.table_run_stats WHERE run_id=?"),
        "quality_scores": q("SELECT * FROM audit.quality_scores WHERE run_id=?"),
        "rule_results": q("SELECT * FROM audit.rule_results WHERE run_id=? AND rows_failed > 0 ORDER BY rows_failed DESC"),
        "schema_checks": q("SELECT * FROM audit.schema_checks WHERE run_id=?"),
        "reconciliation": q("SELECT * FROM audit.reconciliation WHERE run_id=?"),
    }
    (out_dir / f"quality_report_{run_id}.json").write_text(json.dumps(report, indent=2, default=str))
    md = [f"# Data Quality Report - {run_id}", "", "## Scores", "| Dimension | Score | Evaluated | Failed |", "|---|---|---|---|"]
    md += [f"| {s['dimension']} | {s['score']:.4f} | {s['rows_evaluated']} | {s['rows_failed']} |" for s in report["quality_scores"]]
    md += ["", "## Table statistics", "| Table | Source | Valid | Rejected | Duplicates |", "|---|---|---|---|---|"]
    md += [f"| {t['table_name']} | {t['source_rows']} | {t['valid_rows']} | {t['rejected_rows']} | {t['duplicate_rows']} |" for t in report["table_stats"]]
    md += ["", "## Failing rules", "| Table | Rule | Failed / Evaluated |", "|---|---|---|"]
    md += [f"| {r['table_name']} | {r['rule_name']} | {r['rows_failed']} / {r['rows_evaluated']} |" for r in report["rule_results"]]
    md += ["", "## Reconciliation", "| Check | Expected | Actual | Status |", "|---|---|---|---|"]
    md += [f"| {r['check_name']} | {r['expected']} | {r['actual']} | {r['status']} |" for r in report["reconciliation"]]
    (out_dir / f"quality_report_{run_id}.md").write_text("\n".join(md))
    return report
