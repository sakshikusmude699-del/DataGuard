# Data dictionary

Grain: Orders = one row per order; Customers = one row per `customer_id` (an id per order, **not** per person);
Order items = one row per item within an order. `customer_unique_id` identifies the person and may repeat across `customer_id`s.

## Source and Bronze (all columns VARCHAR in Bronze)
**orders** (key: `order_id`): order_id, customer_id (FK customers), order_status, order_purchase_timestamp, order_approved_at,
order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date.
**customers** (key: `customer_id`): customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state.
**order_items** (key: `order_id` + `order_item_id`): order_id (FK orders), order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value.

Bronze adds: `_extra_json` (unexpected columns), `source_file`, `source_file_hash`, `source_row_number`, `ingestion_timestamp`, `run_id`. PK `(source_file_hash, source_row_number)`.

## Silver
### silver.orders_clean (PK order_id)
| Column | Type | Null | Rule |
|---|---|---|---|
| order_id | VARCHAR | no | present, unique |
| customer_id | VARCHAR | no | exists in silver.customers_clean |
| order_status | VARCHAR | no | lower-cased; in the valid set |
| status_rank | INTEGER | yes | 1 created ... 6 delivered/canceled/unavailable; blocks regressions on MERGE |
| order_purchase_timestamp | TIMESTAMP | no | valid `%Y-%m-%d %H:%M:%S` |
| order_approved_at, order_delivered_carrier_date, order_estimated_delivery_date | TIMESTAMP | yes | valid when present |
| order_delivered_customer_date | TIMESTAMP | yes | required when status = delivered; not before purchase |
| source_file, source_row_number, run_id, processed_at | | | lineage |
### silver.customers_clean (PK customer_id)
customer_id (not null, unique), customer_unique_id (not null), customer_zip_code_prefix VARCHAR (kept as text; leading zeros), customer_city (lower-cased, contains letters),
customer_state (upper-cased, exactly 2 letters), lineage columns.
### silver.order_items_clean (PK order_id, order_item_id)
order_id (exists in silver orders), order_item_id INTEGER, product_id and seller_id (not null), shipping_limit_date TIMESTAMP (valid when present),
price DECIMAL(12,2) >= 0, freight_value DECIMAL(12,2) >= 0, lineage columns.

## Gold
| Table | Grain | Key columns / measures |
|---|---|---|
| fact_orders | one row per order | order_id, customer_id, customer_unique_id, customer_state, order_status, purchase_month, item_count, items_revenue, freight_total, order_value (= items + freight), delivery_days, is_late |
| dim_customers | one row per customer_unique_id | customer_id_count, state/city of latest order, order_count, total_spent, first/last purchase, is_repeat_customer |
| sales_summary | purchase_month x order_status x customer_state | total_orders, total_revenue (items), total_freight, total_order_value, avg_order_value (over orders with items) |
| delivery_performance | purchase_month x customer_state, delivered orders only | delivered_orders, avg_delivery_days, late_orders, late_delivery_pct |

`is_late` = delivered after the estimated date; NULL when either date is missing. Revenue excludes freight; `order_value` includes it.

## Audit
`rejected_orders|customers|order_items`: record_id, original source columns, source_file, source_file_hash, source_row_number, run_id, rejection_reason (rule names joined by `;`), rejection_timestamp.
`pipeline_runs`, `processed_files`, `schema_checks`, `table_run_stats`, `rule_results`, `null_profile`, `quality_scores`, `reconciliation`: see `src/database.py`.
