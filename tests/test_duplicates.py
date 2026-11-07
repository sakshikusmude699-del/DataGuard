import pandas as pd
from src.deduplication import duplicate_mask


def f(rows, cols):
    d = pd.DataFrame(rows, columns=cols); d["source_row_number"] = range(2, len(d) + 2); return d


def test_first_occurrence_kept_later_rejected():
    assert list(duplicate_mask(f([["a"], ["b"], ["a"], ["a"]], ["k"]), ["k"])) == [False, False, True, True]


def test_blank_keys_are_not_duplicates_of_each_other():
    assert list(duplicate_mask(f([[""], [""], ["a"]], ["k"]), ["k"])) == [False, False, False]


def test_composite_key():
    d = f([["o1", "1"], ["o1", "2"], ["o1", "1"]], ["order_id", "order_item_id"])
    assert list(duplicate_mask(d, ["order_id", "order_item_id"])) == [False, False, True]


def test_policy_is_deterministic_regardless_of_row_order():
    d = f([["a"], ["a"]], ["k"]).iloc[::-1]       # shuffled physical order, source_row_number decides
    m = duplicate_mask(d, ["k"])
    assert m.loc[d["source_row_number"].idxmin()] == False and m.sum() == 1
