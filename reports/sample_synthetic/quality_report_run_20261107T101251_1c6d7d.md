# Data Quality Report - run_20261107T101251_1c6d7d

## Scores
| Dimension | Score | Evaluated | Failed |
|---|---|---|---|
| completeness | 0.9950 | 143460 | 718 |
| validity | 0.9936 | 195443 | 1260 |
| uniqueness | 0.9714 | 35663 | 1021 |
| referential | 0.9028 | 26685 | 2594 |
| overall | 0.9657 | 401251 | 5593 |

## Table statistics
| Table | Source | Valid | Rejected | Duplicates |
|---|---|---|---|---|
| customers | 9180 | 8820 | 360 | 180 |
| orders | 10200 | 8859 | 1341 | 198 |
| order_items | 16485 | 13207 | 3278 | 643 |

## Failing rules
| Table | Rule | Failed / Evaluated |
|---|---|---|
| order_items | ORPHAN_ORDER_ID | 2175 / 16485 |
| order_items | DUPLICATE_ORDER_ITEM_KEY | 643 / 16485 |
| orders | ORPHAN_CUSTOMER_ID | 419 / 10200 |
| order_items | NEGATIVE_PRICE | 332 / 16485 |
| order_items | MISSING_SELLER_ID | 331 / 16485 |
| order_items | NEGATIVE_FREIGHT_VALUE | 328 / 16485 |
| orders | INVALID_TIMESTAMP_ORDER_PURCHASE_TIMESTAMP | 205 / 10200 |
| orders | MISSING_ORDER_ID | 202 / 10200 |
| orders | INVALID_ORDER_STATUS | 198 / 10200 |
| orders | DUPLICATE_ORDER_ID | 198 / 9998 |
| orders | DELIVERED_BEFORE_PURCHASE | 197 / 9299 |
| customers | MISSING_CUSTOMER_STATE | 185 / 9180 |
| customers | DUPLICATE_CUSTOMER_ID | 180 / 9180 |

## Reconciliation
| Check | Expected | Actual | Status |
|---|---|---|---|
| customers: source rows == bronze rows | 9180 | 9180 | PASS |
| customers: bronze rows == silver-valid + rejected | 9180 | 9180 | PASS |
| orders: source rows == bronze rows | 10200 | 10200 | PASS |
| orders: bronze rows == silver-valid + rejected | 10200 | 10200 | PASS |
| order_items: source rows == bronze rows | 16485 | 16485 | PASS |
| order_items: bronze rows == silver-valid + rejected | 16485 | 16485 | PASS |
| silver.orders == gold.fact_orders (rows) | 8859 | 8859 | PASS |
| silver items price == gold items_revenue | 1185670.56 | 1185670.56 | PASS |
| silver items freight == gold freight_total | 209557.40 | 209557.40 | PASS |
| gold.sales_summary orders == fact_orders rows | 8859 | 8859 | PASS |
| gold.dim_customers order_count == fact_orders rows | 8859 | 8859 | PASS |
| silver order items with no silver order (orphans) | 0 | 0 | PASS |