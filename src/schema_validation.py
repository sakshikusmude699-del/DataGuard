"""Schema validation: required columns (hard fail) and unexpected columns (warning, preserved)."""
from dataclasses import dataclass, field


class SchemaValidationError(Exception):
    """Raised when a source file is missing required columns."""


@dataclass
class SchemaResult:
    table: str
    status: str  # PASS | WARN | FAIL
    missing: list = field(default_factory=list)
    unexpected: list = field(default_factory=list)


def validate_columns(table: str, actual_columns, expected_columns) -> SchemaResult:
    actual = [c.strip() for c in actual_columns]
    missing = [c for c in expected_columns if c not in actual]
    unexpected = [c for c in actual if c not in expected_columns]
    if missing:
        return SchemaResult(table, "FAIL", missing, unexpected)
    return SchemaResult(table, "WARN" if unexpected else "PASS", [], unexpected)


def assert_schema(result: SchemaResult) -> None:
    if result.status == "FAIL":
        raise SchemaValidationError(f"{result.table}: missing required columns {result.missing}")
