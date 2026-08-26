import io
import openpyxl
import pytest

from app.services.requirement_import import (
    IMPORT_HEADERS, build_template_xlsx, parse_rows,
    RowError,
)


def _load(content: bytes) -> list[list]:
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb["Requirements"]
    return [[c for c in row] for row in ws.iter_rows(values_only=True)]


def test_template_has_headers_and_example():
    rows = _load(build_template_xlsx())
    assert list(rows[0])[:3] == ["Requirement", "Additional Details", "Period From"]
    assert len(rows[0]) == len(IMPORT_HEADERS)
    assert any(any(c for c in row) for row in rows[1:])  # example row present


def test_parse_minimal_row_defaults():
    p = parse_rows([["Bank statements FY24"]])[0]
    assert p["description"] == "Bank statements FY24"
    assert p["priority"] == 1
    assert p["expected_format"] == "any"
    assert p["due_date"] is None
    assert p["parent_seq"] is None


def test_parse_full_row():
    p = parse_rows([[
        "Ledger dump", "Include opening balances", "2025-04-01", "2026-03-31",
        "ETHDC Main", 3, "2026-04-15", "finance@ethdc.com", "FILE",
        "Chase weekly", "REQ-002",
    ]])[0]
    assert str(p["period_from"]) == "2025-04-01"
    assert p["priority"] == 3
    assert p["expected_format"] == "file"
    assert p["parent_seq"] == 2


def test_missing_requirement_is_row_error():
    with pytest.raises(RowError) as e:
        parse_rows([[None]])
    assert e.value.row == 2


def test_bad_priority_rejected():
    with pytest.raises(RowError):
        parse_rows([["X", None, None, None, None, 9]])


def test_bad_date_rejected():
    with pytest.raises(RowError):
        parse_rows([["X", None, "31/04/2025"]])


def test_bad_expected_format_rejected():
    with pytest.raises(RowError):
        parse_rows([["X", None, None, None, None, None, None, None, "smoke signal"]])


def test_forward_parent_reference_rejected():
    with pytest.raises(RowError):
        parse_rows([
            ["Child", None, None, None, None, None, None, None, None, None, "REQ-999"],
            ["Parent"],
        ])


def test_blank_spacer_rows_tolerated():
    payloads = parse_rows([[None, None], ["Real"], [None]])
    assert len(payloads) == 1 and payloads[0]["row"] == 3
