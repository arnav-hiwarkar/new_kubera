import io
import csv
from uuid import UUID
from typing import List, Dict, Callable, Any
from dataclasses import dataclass
from fastapi import UploadFile
import openpyxl

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ValidationError

from app.models.custom_fields import CustomFieldDefinition
from app.services.custom_field_validator import validate_custom_fields

@dataclass
class ColumnMapping:
    source_column: str
    target_field: str

@dataclass
class ImportResult:
    imported: int
    skipped: int
    errors: List[dict]

async def parse_and_import(
    file: UploadFile,
    column_mappings: List[ColumnMapping],
    base_field_validators: Dict[str, Callable],
    custom_field_definitions: List[CustomFieldDefinition],
    row_factory: Callable[[dict, dict], Any], # takes base_data, custom_data
    db: AsyncSession,
    company_id: UUID,
    module: Any
) -> ImportResult:
    content = await file.read()
    
    rows = []
    if file.filename.endswith('.csv'):
        text = content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    elif file.filename.endswith('.xlsx'):
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        sheet = wb.active
        headers = [cell.value for cell in sheet[1]]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            rows.append(dict(zip(headers, row)))
    else:
        raise ValueError("Unsupported file format")

    result = ImportResult(imported=0, skipped=0, errors=[])
    
    def_map = {d.field_key: d for d in custom_field_definitions}

    for idx, row in enumerate(rows, start=1): # 1-indexed for user visibility
        row_errors = []
        base_data = {}
        custom_data = {}

        for mapping in column_mappings:
            source = mapping.source_column
            target = mapping.target_field
            value = row.get(source)

            if target in base_field_validators:
                try:
                    if value is not None and value != "":
                        base_data[target] = base_field_validators[target](value)
                except Exception as e:
                    row_errors.append(f"Invalid value for {target}: {value}")
            else:
                custom_data[target] = value

        # Validate custom fields
        custom_errors = await validate_custom_fields(custom_data, company_id, module, db)
        for err in custom_errors:
            row_errors.append(err)

        if row_errors:
            result.skipped += 1
            result.errors.append({"row": idx, "errors": row_errors})
        else:
            try:
                db_row = row_factory(base_data, custom_data)
                db.add(db_row)
                result.imported += 1
            except Exception as e:
                result.skipped += 1
                result.errors.append({"row": idx, "errors": [str(e)]})

    return result


# ---------------------------------------------------------------------------
# Trial-balance import (server-side, two-call: inspect -> map -> import)
# ---------------------------------------------------------------------------

TB_NUMERIC_FIELDS = ["opening_balance", "debit", "credit", "closing_balance"]


def _to_number(raw: Any) -> float:
    """Parse a spreadsheet cell into a float. Handles blanks (error), commas,
    currency symbols, and accounting-style parentheses for negatives."""
    if raw is None:
        raise ValueError("empty")
    s = str(raw).strip()
    if s == "":
        raise ValueError("empty")
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    for ch in (",", "₹", "$", "€", "£", " "):
        s = s.replace(ch, "")
    val = float(s)
    return -val if neg else val


def _read_csv(content: bytes) -> tuple[List[str], List[list]]:
    text = content.decode("utf-8-sig")
    all_rows = list(csv.reader(io.StringIO(text)))
    if not all_rows:
        return [], []
    headers = [("" if h is None else str(h).strip()) for h in all_rows[0]]
    return headers, [list(r) for r in all_rows[1:]]


def load_sheet(filename: str, content: bytes, sheet_name: str | None) -> tuple[List[str], List[list]]:
    """Return (headers, data_rows) for one sheet. CSV has a single virtual sheet."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return _read_csv(content)
    if name.endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        try:
            if sheet_name and sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
            elif sheet_name:
                raise ValueError(f"Sheet '{sheet_name}' not found")
            else:
                ws = wb.worksheets[0]
            rows = list(ws.iter_rows(values_only=True))
        finally:
            wb.close()
        if not rows:
            return [], []
        headers = [("" if h is None else str(h).strip()) for h in rows[0]]
        return headers, [list(r) for r in rows[1:]]
    raise ValueError("Unsupported file format. Use .csv or .xlsx")


def inspect_spreadsheet(filename: str, content: bytes, preview: int = 5) -> List[dict]:
    """List every sheet with its column headers and the first `preview` data rows."""
    name = (filename or "").lower()
    sheets: List[dict] = []
    if name.endswith(".csv"):
        headers, data = _read_csv(content)
        sheets.append({
            "name": "Sheet1",
            "headers": headers,
            "preview_rows": [[("" if c is None else str(c)) for c in row] for row in data[:preview]],
        })
    elif name.endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        try:
            for ws in wb.worksheets:
                rows_iter = ws.iter_rows(values_only=True)
                try:
                    header_row = next(rows_iter)
                except StopIteration:
                    header_row = ()
                headers = [("" if h is None else str(h).strip()) for h in header_row]
                preview_rows = []
                for row in rows_iter:
                    if len(preview_rows) >= preview:
                        break
                    preview_rows.append([("" if c is None else str(c)) for c in row])
                sheets.append({"name": ws.title, "headers": headers, "preview_rows": preview_rows})
        finally:
            wb.close()
    else:
        raise ValueError("Unsupported file format. Use .csv or .xlsx")
    return sheets


def parse_trial_balance(
    filename: str,
    content: bytes,
    sheet_name: str | None,
    column_map: Dict[str, str | None],
) -> tuple[List[dict], List[dict]]:
    """Parse the chosen sheet using column_map (field -> source header).
    Returns (valid_rows, errors). ledger_name + all four numerics are required;
    ledger_code is optional. Rows failing validation are collected, not raised."""
    headers, data_rows = load_sheet(filename, content, sheet_name)

    idx: Dict[str, int] = {}
    missing: List[str] = []
    for field, src in column_map.items():
        if not src:
            continue
        if src in headers:
            idx[field] = headers.index(src)
        else:
            missing.append(src)
    if missing:
        raise ValueError(f"Mapped columns not found in sheet: {missing}")
    if "ledger_name" not in idx:
        raise ValueError("ledger_name must be mapped")
    for f in TB_NUMERIC_FIELDS:
        if f not in idx:
            raise ValueError(f"{f} must be mapped")

    def cell(row: list, field: str):
        i = idx.get(field)
        if i is None or i >= len(row):
            return None
        return row[i]

    valid: List[dict] = []
    errors: List[dict] = []
    for i, row in enumerate(data_rows, start=1):
        if not any(c not in (None, "") for c in row):
            continue  # skip fully blank rows
        row_errors: List[str] = []
        rec: Dict[str, Any] = {}

        name = cell(row, "ledger_name")
        if name is None or str(name).strip() == "":
            row_errors.append("ledger_name is required")
        else:
            rec["ledger_name"] = str(name).strip()

        if "ledger_code" in idx:
            code = cell(row, "ledger_code")
            rec["ledger_code"] = None if code in (None, "") else str(code).strip()

        for f in TB_NUMERIC_FIELDS:
            try:
                rec[f] = _to_number(cell(row, f))
            except (ValueError, TypeError):
                row_errors.append(f"{f} must be a number (got {cell(row, f)!r})")

        if row_errors:
            errors.append({"row": i, "errors": row_errors})
        else:
            valid.append(rec)

    return valid, errors
