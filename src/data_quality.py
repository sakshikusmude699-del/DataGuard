"""Modular validation rules. Each rule returns (name, dimension, failed_mask, evaluated_mask).

Dimensions: completeness | validity | uniqueness | referential
"""
from dataclasses import dataclass
import pandas as pd
from .config import (DELIVERED_REQUIRES_TS, ORDER_TS_COLS, TS_FORMAT, VALID_STATUSES)
from .deduplication import duplicate_mask


@dataclass
class RuleResult:
    rule_name: str
    dimension: str
    rows_evaluated: int
    rows_failed: int


def _blank(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().eq("")


def parse_ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format=TS_FORMAT, errors="coerce")


# ---- generic rule builders -------------------------------------------------
def required(df, col):
    return (f"MISSING_{col.upper()}", "completeness", _blank(df[col]), None)


def invalid_timestamp(df, col):
    nonblank = ~_blank(df[col])
    return (f"INVALID_TIMESTAMP_{col.upper()}", "validity", nonblank & parse_ts(df[col]).isna(), nonblank)


def invalid_number(df, col):
    nonblank = ~_blank(df[col])
    return (f"INVALID_NUMBER_{col.upper()}", "validity", nonblank & pd.to_numeric(df[col], errors="coerce").isna(), nonblank)


def negative_number(df, col):
    num = pd.to_numeric(df[col], errors="coerce")
    return (f"NEGATIVE_{col.upper()}", "validity", num < 0, num.notna())


def not_in_set(df, col, allowed, name):
    nonblank = ~_blank(df[col])
    return (name, "validity", nonblank & ~df[col].isin(allowed), nonblank)


def duplicate_key(df, keys, name):
    evaluated = ~df[keys].apply(_blank).any(axis=1)
    return (name, "uniqueness", duplicate_mask(df, keys).fillna(False), evaluated)


def foreign_key(df, col, valid_values, name):
    nonblank = ~_blank(df[col])
    return (name, "referential", nonblank & ~df[col].isin(valid_values), nonblank)


# ---- per-table rule sets ---------------------------------------------------
def customers_rules(df):
    state_bad = ~df["customer_state"].str.fullmatch(r"[A-Za-z]{2}", na=False)
    city_bad = ~df["customer_city"].str.contains(r"[A-Za-zÀ-ÿ]", na=False)
    st_nb, city_nb = ~_blank(df["customer_state"]), ~_blank(df["customer_city"])
    return [
        required(df, "customer_id"), required(df, "customer_unique_id"),
        required(df, "customer_city"), required(df, "customer_state"),
        ("MALFORMED_CUSTOMER_STATE", "validity", st_nb & state_bad, st_nb),
        ("MALFORMED_CUSTOMER_CITY", "validity", city_nb & city_bad, city_nb),
        duplicate_key(df, ["customer_id"], "DUPLICATE_CUSTOMER_ID"),
    ]


def orders_rules(df, valid_customer_ids):
    purchase = parse_ts(df["order_purchase_timestamp"])
    delivered = parse_ts(df["order_delivered_customer_date"])
    both = purchase.notna() & delivered.notna()
    needs_delivery = df["order_status"].isin(DELIVERED_REQUIRES_TS)
    rules = [required(df, c) for c in ("order_id", "customer_id", "order_status", "order_purchase_timestamp")]
    rules += [not_in_set(df, "order_status", VALID_STATUSES, "INVALID_ORDER_STATUS")]
    rules += [invalid_timestamp(df, c) for c in ORDER_TS_COLS]
    rules += [
        ("DELIVERED_BEFORE_PURCHASE", "validity", both & (delivered < purchase), both),
        # Missing delivery date is only an error when the status says the order WAS delivered.
        ("DELIVERED_STATUS_MISSING_DELIVERY_DATE", "validity",
         needs_delivery & _blank(df["order_delivered_customer_date"]), needs_delivery),
        duplicate_key(df, ["order_id"], "DUPLICATE_ORDER_ID"),
        foreign_key(df, "customer_id", valid_customer_ids, "ORPHAN_CUSTOMER_ID"),
    ]
    return rules


def order_items_rules(df, valid_order_ids):
    rules = [required(df, c) for c in ("order_id", "order_item_id", "product_id", "seller_id")]
    rules += [invalid_number(df, "price"), invalid_number(df, "freight_value"),
              negative_number(df, "price"), negative_number(df, "freight_value"),
              invalid_number(df, "order_item_id"), invalid_timestamp(df, "shipping_limit_date"),
              duplicate_key(df, ["order_id", "order_item_id"], "DUPLICATE_ORDER_ITEM_KEY"),
              foreign_key(df, "order_id", valid_order_ids, "ORPHAN_ORDER_ID")]
    return rules


def evaluate(df: pd.DataFrame, rules):
    """Apply rules. Returns (reasons Series ('' = valid), list[RuleResult])."""
    reasons = pd.Series([""] * len(df), index=df.index, dtype=object)
    results = []
    for name, dim, failed, evaluated in rules:
        failed = failed.fillna(False).astype(bool)
        evaluated = pd.Series(True, index=df.index) if evaluated is None else evaluated.fillna(False)
        reasons = reasons.where(~failed, reasons + failed.map({True: name + ";"}).fillna(""))
        results.append(RuleResult(name, dim, int(evaluated.sum()), int(failed.sum())))
    return reasons.str.rstrip(";"), results


def null_profile(df: pd.DataFrame, columns):
    return [(c, int(_blank(df[c]).sum()), len(df)) for c in columns]


def quality_scores(rule_rows):
    """rule_rows: iterable of (dimension, evaluated, failed).
    score(dimension) = 1 - sum(failed)/sum(evaluated); overall = unweighted mean of the 4 dimensions."""
    agg = {}
    for dim, ev, fl in rule_rows:
        a = agg.setdefault(dim, [0, 0]); a[0] += ev; a[1] += fl
    scores = {d: (1.0 if ev == 0 else 1 - fl / ev, ev, fl) for d, (ev, fl) in agg.items()}
    if scores:
        scores["overall"] = (sum(v[0] for v in scores.values()) / len(scores),
                             sum(v[1] for v in scores.values()), sum(v[2] for v in scores.values()))
    return scores
