"""Central configuration: paths, source schemas, business-rule constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SYNTHETIC_DIR = ROOT / "data" / "synthetic"
DB_PATH = ROOT / "database" / "dataguard.duckdb"
REPORTS_DIR = ROOT / "reports"
LOG_DIR = ROOT / "logs"

TS_FORMAT = "%Y-%m-%d %H:%M:%S"  # format used by every Olist timestamp column

# Source table definitions (Olist). `keys` is the business key (see docs/data_dictionary.md).
TABLES = {
    "orders": {
        "filename": "olist_orders_dataset.csv",
        "columns": ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
                    "order_approved_at", "order_delivered_carrier_date",
                    "order_delivered_customer_date", "order_estimated_delivery_date"],
        "keys": ["order_id"],
        "bronze": "bronze.orders_raw", "silver": "silver.orders_clean",
        "rejected": "audit.rejected_orders",
    },
    "customers": {
        "filename": "olist_customers_dataset.csv",
        "columns": ["customer_id", "customer_unique_id", "customer_zip_code_prefix",
                    "customer_city", "customer_state"],
        "keys": ["customer_id"],
        "bronze": "bronze.customers_raw", "silver": "silver.customers_clean",
        "rejected": "audit.rejected_customers",
    },
    "order_items": {
        "filename": "olist_order_items_dataset.csv",
        "columns": ["order_id", "order_item_id", "product_id", "seller_id",
                    "shipping_limit_date", "price", "freight_value"],
        "keys": ["order_id", "order_item_id"],
        "bronze": "bronze.order_items_raw", "silver": "silver.order_items_clean",
        "rejected": "audit.rejected_order_items",
    },
}
# Processing order matters: customers -> orders -> order_items (FK dependencies).
PROCESS_ORDER = ["customers", "orders", "order_items"]

VALID_STATUSES = {"created", "approved", "invoiced", "processing", "shipped",
                  "delivered", "unavailable", "canceled"}
# Used to stop out-of-order (late/replayed) records from regressing an order's lifecycle.
STATUS_RANK = {"created": 1, "approved": 2, "invoiced": 3, "processing": 4,
               "shipped": 5, "delivered": 6, "unavailable": 6, "canceled": 6}
ORDER_TS_COLS = ["order_purchase_timestamp", "order_approved_at",
                 "order_delivered_carrier_date", "order_delivered_customer_date",
                 "order_estimated_delivery_date"]
DELIVERED_REQUIRES_TS = {"delivered"}

RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
