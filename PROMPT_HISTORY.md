# Prompt history and AI-assistance disclosure

The project was built with an AI assistant (Claude) from a single master prompt (project brief) provided by the candidate.
The brief required: Olist dataset, DuckDB Medallion architecture, quality framework, idempotency, monitoring, pytest suite,
synthetic data generator, benchmark, Streamlit dashboard, and honest reporting (no fabricated data or results).

Key points of the session
1. Kaggle access was attempted from the build sandbox and failed (no DNS route, no credentials); the dataset was not fabricated.
   The pipeline was verified on labelled synthetic data and a hand-computed fixture instead.
2. Implementation, tests, dashboard, benchmark and documentation were generated, executed, and defects found during testing were fixed (docs/design_decisions.md).
3. Candidate to-do before submission: run on the real data, refresh README sections 14-16, capture screenshots, review every module so it can be explained in interview.
