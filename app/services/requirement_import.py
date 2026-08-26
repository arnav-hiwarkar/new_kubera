"""Bulk import of auditor requirements from Excel.

All-or-nothing: every row is parsed and referentially validated before anything
is written; one bad row aborts the whole file with a per-row report.
Attachments are deliberately out of scope — they are added later through the
normal respond/edit flows.
"""
import io
import uuid
from datetime import date, datetime
from typing import List, Optional

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditease import RequirementRequest
from app.models.company import CompanyUser

IMPORT_HEADERS = [
    "Requirement", "Additional Details", "Period From", "Period To",
    "Entity", "Priority", "Due Date", "Responsible Person Email",
    "Expected Format", "Auditor Notes", "Parent Requirement ID",
]

_INSTRUCTIONS = [
    "AuditEase — bulk requirement import.",
    "Fill the Requirements sheet. One row per requirement. Do not rename columns.",
    "Requirement is mandatory; every other column is optional.",
    "Dates: YYYY-MM-DD. Priority: 1-5 (blank = 1). Expected Format: text/file/any (blank = any).",
    "Responsible Person Email must belong to the client company.",
    "Parent Requirement ID must be an existing REQ-xxx in this engagement or an EARLIER row of this file.",
    "Documents cannot be attached here — attach them later from the requirement.",
    "Any row with an error aborts the whole file — fix it and re-upload.",
]


class ImportRejected(Exception):
    def __init__(self, errors: List[dict]):
        self.errors = errors
        super().__init__("Import rejected")


class RowError(Exception):
    def __init__(self, row: int, message: str):
        self.row, self.message = row, message
        super().__init__(message)


def build_template_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    info = wb.active
    info.title = "Instructions"
    info.column_dimensions["A"].width = 95
    for i, line in enumerate(_INSTRUCTIONS, start=1):
        cell = info.cell(row=i, column=1, value=line)
        if i == 1:
            cell.font = Font(bold=True)
    sheet = wb.create_sheet("Requirements")
    for col, name in enumerate(IMPORT_HEADERS, start=1):
        sheet.cell(row=1, column=col, value=name).font = Font(bold=True)
        sheet.column_dimensions[get_column_letter(col)].width = 28
    sheet.append([
        "FY24 bank statements for all current accounts", "Include closing balance certificates",
        "2025-04-01", "2026-03-31", "ETHDC Main", 2, "2026-09-15", "finance@example.com",
        "file", "Example row — delete before use", None,
    ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _email_key(email: str) -> str:
    return email.strip().lower()


def _to_date(value) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"'{value}' is not a YYYY-MM-DD date")


def _to_priority(value) -> int:
    if value in (None, ""):
        return 1
    try:
        p = int(float(str(value)))
    except (TypeError, ValueError):
        raise ValueError(f"'{value}' is not a whole number")
    if not 1 <= p <= 5:
        raise ValueError(f"Priority {p} out of range 1-5")
    return p


def _to_format(value) -> str:
    v = (str(value).strip().lower() if value not in (None, "") else "") or "any"
    if v not in ("text", "file", "any"):
        raise ValueError(f"'{value}' is not text/file/any")
    return v


def _cell(row: list, idx: int):
    return row[idx] if idx < len(row) else None


def _opt_str(row: list, idx: int) -> Optional[str]:
    v = _cell(row, idx)
    return str(v).strip() if v not in (None, "") else None


def parse_rows(rows: List[list]) -> List[dict]:
    """Structural parsing only. Referential checks (emails, parents) happen in
    import_requirements against the DB + earlier file rows."""
    payloads: List[dict] = []
    for n, row in enumerate(rows, start=2):  # Excel numbering: header is row 1
        if not any(v not in (None, "") for v in row):
            continue  # tolerate blank spacer rows
        p: dict = {"row": n}
        try:
            desc = _cell(row, 0)
            if not desc or not str(desc).strip():
                raise ValueError("Requirement is required")
            p["description"] = str(desc).strip()
            p["additional_details"] = _opt_str(row, 1)
            p["period_from"] = _to_date(_cell(row, 2))
            p["period_to"] = _to_date(_cell(row, 3))
            p["entity"] = _opt_str(row, 4)
            p["priority"] = _to_priority(_cell(row, 5))
            p["due_date"] = _to_date(_cell(row, 6))
            p["responsible_email"] = _opt_str(row, 7)
            p["expected_format"] = _to_format(_cell(row, 8))
            p["auditor_notes"] = _opt_str(row, 9)
            ref = _opt_str(row, 10)
            if ref is not None:
                parts = ref.upper().split("-")
                if len(parts) != 2 or parts[0] != "REQ" or not parts[1].isdigit():
                    raise ValueError(f"Parent '{ref}' is not a REQ-xxx id")
                # Format-only here: whether the parent exists / precedes this row
                # is referential knowledge — import_requirements enforces it.
                p["parent_seq"] = int(parts[1])
            else:
                p["parent_seq"] = None
        except ValueError as e:
            raise RowError(n, str(e))
        payloads.append(p)
    if not payloads and rows:
        raise RowError(2, "Requirement is required")
    return payloads


async def import_requirements(
    db: AsyncSession, company_id: uuid.UUID, engagement_id: uuid.UUID,
    raised_by: uuid.UUID, rows: List[list],
) -> List[RequirementRequest]:
    """Validate everything, then stage creations on the caller's session.
    Rolls back and raises ImportRejected on any failure. Does NOT commit."""
    from app.models.auditease import ExpectedFormat

    payloads = parse_rows(rows)
    if not payloads:
        raise RowError(0, "No data rows found")

    users = (await db.execute(
        select(CompanyUser.id, CompanyUser.email).where(CompanyUser.company_id == company_id)
    )).all()
    emails = {_email_key(email): uid for uid, email in users}

    seq_rows = (await db.execute(
        select(RequirementRequest.seq_number).where(RequirementRequest.engagement_id == engagement_id)
    )).scalars().all()
    next_seq = max((s for s in seq_rows if s is not None), default=0) + 1

    errors: List[RowError] = []
    created: List[RequirementRequest] = []

    for p in payloads:
        try:
            responsible_id = None
            if p["responsible_email"]:
                responsible_id = emails.get(_email_key(p["responsible_email"]))
                if responsible_id is None:
                    raise ValueError(f"No company user with email '{p['responsible_email']}'")

            parent_id = None
            if p["parent_seq"] is not None:
                prior = next((r for r in created if r.seq_number == p["parent_seq"]), None)
                if prior is not None:
                    parent_id = prior.id
                else:
                    existing = (await db.execute(
                        select(RequirementRequest.id).where(
                            RequirementRequest.engagement_id == engagement_id,
                            RequirementRequest.seq_number == p["parent_seq"],
                        )
                    )).scalar_one_or_none()
                    if existing is None:
                        raise ValueError(f"Parent REQ-{p['parent_seq']:03d} not found")
                    parent_id = existing

            req = RequirementRequest(
                engagement_id=engagement_id,
                raised_by=raised_by,
                title=p["description"][:255],
                description=p["description"],
                seq_number=next_seq,
                priority=p["priority"],
                due_date=p["due_date"],
                additional_details=p["additional_details"],
                period_from=p["period_from"],
                period_to=p["period_to"],
                entity=p["entity"],
                responsible_person_id=responsible_id,
                expected_format=ExpectedFormat(p["expected_format"]),
                auditor_notes=p["auditor_notes"],
                parent_requirement_id=parent_id,
            )
            db.add(req)
            await db.flush()  # assign id + seq so later rows can parent to it
            created.append(req)
            next_seq += 1
        except ValueError as e:
            errors.append(RowError(p["row"], str(e)))

    if errors:
        await db.rollback()
        raise ImportRejected([{"row": e.row, "message": e.message} for e in errors])
    return created
