"""Reconciliation checks. A FAIL aborts the run (transaction rolled back) so Gold is never inconsistent."""


class ReconciliationError(Exception):
    pass


def _q(con, sql):
    return con.execute(sql).fetchall()[0][0]


def check_batch(table, source_rows, bronze_rows, valid_rows, rejected_rows):
    return [
        (f"{table}: source rows == bronze rows", source_rows, bronze_rows),
        (f"{table}: bronze rows == silver-valid + rejected", bronze_rows, valid_rows + rejected_rows),
    ]


def check_layers(con):
    """Cross-layer invariants over the whole database state."""
    r = []
    r.append(("silver.orders == gold.fact_orders (rows)", _q(con, "SELECT count(*) FROM silver.orders_clean"),
              _q(con, "SELECT count(*) FROM gold.fact_orders")))
    r.append(("silver items price == gold items_revenue",
              _q(con, "SELECT COALESCE(SUM(price),0) FROM silver.order_items_clean"),
              _q(con, "SELECT COALESCE(SUM(items_revenue),0) FROM gold.fact_orders")))
    r.append(("silver items freight == gold freight_total",
              _q(con, "SELECT COALESCE(SUM(freight_value),0) FROM silver.order_items_clean"),
              _q(con, "SELECT COALESCE(SUM(freight_total),0) FROM gold.fact_orders")))
    r.append(("gold.sales_summary orders == fact_orders rows",
              _q(con, "SELECT count(*) FROM gold.fact_orders"),
              _q(con, "SELECT COALESCE(SUM(total_orders),0) FROM gold.sales_summary")))
    r.append(("gold.dim_customers order_count == fact_orders rows",
              _q(con, "SELECT count(*) FROM gold.fact_orders"),
              _q(con, "SELECT COALESCE(SUM(order_count),0) FROM gold.dim_customers")))
    r.append(("silver order items with no silver order (orphans)", 0,
              _q(con, "SELECT count(*) FROM silver.order_items_clean i "
                      "WHERE NOT EXISTS (SELECT 1 FROM silver.orders_clean o WHERE o.order_id=i.order_id)")))
    return r


def record(con, run_id, checks):
    """Persist checks; return overall status 'PASS' or 'FAIL'."""
    status = "PASS"
    for name, expected, actual in checks:
        ok = str(expected) == str(actual)
        status = status if ok else "FAIL"
        con.execute("INSERT INTO audit.reconciliation VALUES (?,?,?,?,?)",
                    [run_id, name, str(expected), str(actual), "PASS" if ok else "FAIL"])
    return status
