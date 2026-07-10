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
