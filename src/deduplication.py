"""Deterministic duplicate policy.

Policy: within one batch rows are ordered by source_row_number; the FIRST occurrence of a business
key is kept and every later occurrence is rejected (reason DUPLICATE_<KEY>) and quarantined.
Across batches, a re-delivered key is handled by the Silver MERGE (upsert), not by rejection.
"""
import pandas as pd


def duplicate_mask(df: pd.DataFrame, keys) -> pd.Series:
    """True for rows that are a repeat of an earlier row with the same non-blank business key."""
    has_key = ~df[keys].apply(lambda s: s.str.strip().eq("")).any(axis=1)
    ordered = df.sort_values("source_row_number")
    dup = ordered.duplicated(subset=keys, keep="first") & has_key.loc[ordered.index]
    return dup.reindex(df.index)
