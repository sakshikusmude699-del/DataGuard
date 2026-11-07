# Architecture

```mermaid
flowchart TB
  subgraph Input
    A1[olist_orders_dataset.csv]; A2[olist_customers_dataset.csv]; A3[olist_order_items_dataset.csv]
  end
  A1 & A2 & A3 --> P0[1. validate input files + schema, SHA-256 hash]
  P0 --> P1{already processed? hash in audit.processed_files}
  P1 -->|yes, no --force| SK[skip: SKIPPED_NO_NEW_DATA]
  P1 -->|no / --force| BR[2. Bronze load, own transaction, ON CONFLICT DO NOTHING]
  BR --> TX
  subgraph TX[3. ONE atomic transaction]
    direction TB
    S1[customers: rules -> quarantine -> MERGE] --> S2[orders: rules -> quarantine -> MERGE]
    S2 --> S3[order_items: rules -> quarantine -> MERGE]
    S3 --> GD[Gold rebuild from Silver]
    GD --> RC[Reconciliation checks]
    RC --> MT[quality scores, rule results, null profile, processed_files]
  end
  RC -->|any FAIL| RB[ROLLBACK, run marked FAILED]
  MT --> CM[COMMIT, run marked SUCCESS, JSON + MD report]
  CM --> DASH[Streamlit, read-only]
```

## Module responsibilities
| Module | Responsibility |
|---|---|
| `config.py` | paths, source schemas, valid statuses, status ranks, retry settings |
| `database.py` | connections, DDL for four schemas |
| `ingestion.py` | read CSV as text, field-count check, hash, Bronze load/read |
| `schema_validation.py` | missing columns (fail) vs unexpected columns (warn) |
| `data_quality.py` | rule builders, per-table rule sets, `evaluate`, null profile, quality score |
| `deduplication.py` | deterministic first-occurrence duplicate mask |
| `transformations.py` | pure trimming/typing functions |
| `medallion.py` | quarantine, Silver MERGE, Gold SQL |
| `reconciliation.py` | batch and cross-layer checks |
| `monitoring.py` | JSON logging, run bookkeeping, retry |
| `reporting.py` | persist metrics, write reports |
| `pipeline.py` | orchestration and transaction boundaries |

Processing order is customers, orders, order_items so each foreign-key rule checks the parent **after** the parent batch was merged.
