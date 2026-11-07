import pytest
from src.schema_validation import SchemaValidationError, assert_schema, validate_columns

EXP = ["a", "b"]

def test_exact_schema_passes():
    assert validate_columns("t", ["a", "b"], EXP).status == "PASS"

def test_column_order_is_irrelevant():
    assert validate_columns("t", ["b", "a"], EXP).status == "PASS"

def test_missing_column_fails():
    r = validate_columns("t", ["a"], EXP)
    assert r.status == "FAIL" and r.missing == ["b"]
    with pytest.raises(SchemaValidationError):
        assert_schema(r)

def test_unexpected_column_is_warning_not_failure():
    r = validate_columns("t", ["a", "b", "zzz"], EXP)
    assert r.status == "WARN" and r.unexpected == ["zzz"]
    assert_schema(r)  # does not raise

def test_header_whitespace_is_tolerated():
    assert validate_columns("t", [" a", "b "], EXP).status == "PASS"
