# AuditEase Requirements Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade AuditEase requirements from a two-state document request into a reviewed submission lifecycle (`pending → submitted → clarification_needed → accepted`) with rich optional metadata, progressive-disclosure create UI, linked queries, company ETA, animated progress overview, and Excel bulk import.

**Architecture:** Extend `requirement_requests` with metadata columns plus per-engagement `seq_number` (display ID `REQ-001`). Append-only `requirement_responses` table records every company submission. Queries gain a nullable `requirement_id` link. One Alembic migration performs the status enum swap, backfills sequence numbers, and converts legacy fulfilled documents into response rows. Frontend rebuilds both Requirements tabs around a shared animated progress strip.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic + openpyxl; React 18 + TanStack Query + framer-motion 12 + Tailwind; pytest (backend), vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-08-26-auditease-requirements-lifecycle-design.md`

## Global Constraints

- Statuses exactly: `pending`, `submitted`, `clarification_needed`, `accepted` (`str` Enum members where `.name == .value`).
- Mandatory fields: requirement text (`description`), auto `seq_number`/display ID, `status`.
- Priority: integer 1–5, default 1. Due date: optional, no default.
- Expected format is a HINT (`text|file|any`, default `any`) — company may always submit text and/or a DocVault document.
- Reject = `clarification_needed`; loop until `accepted` (terminal; locks edits/responses).
- Review actions open to ANY auditor with `requirements` area access; edit/delete stay owner-only and only while `pending`; delete blocked when child requirements exist.
- Bulk import: all-or-nothing, per-row error report, no attachment columns.
- Activity events: `requirement.submitted`, `requirement.clarification`, `requirement.accepted`, `requirement.bulk_imported`, `requirement.eta_set` (+ existing raised/deleted).
- Tests provision schema via `Base.metadata.create_all` (`tests/conftest.py`) — model changes reach tests without Alembic; the migration is verified separately.
- Frontend lint runs with `--max-warnings 0`.
- Commits follow repo convention: `feat(auditease): ...`, `feat(auditease-web): ...`.

## File Structure

**Backend**
- Modify: `app/models/auditease.py` — `ExpectedFormat`, `RequirementRequest` columns, new `RequirementResponse`, `Query.requirement_id`
- Modify: `app/schemas/auditease.py` — extended create/response, review/respond/eta schemas
- Modify: `app/routers/auditor_engagements.py` — create/update/delete/review/list/import endpoints, query linkage, `enrich_requirements`
- Modify: `app/routers/auditease.py` — respond/eta replace fulfill
- Create: `app/services/requirement_import.py`
- Create: `alembic/versions/9f2c1a7d4e55_requirements_lifecycle.py`
- Create: `unit_tests/test_requirement_models.py`, `unit_tests/test_requirement_import.py`
- Modify: `tests/test_auditease.py`, `tests/test_auditease_multi_auditor.py`

**Frontend**
- Regenerate: `frontend/src/api/schema.d.ts` (`npm run gen:api`)
- Modify: `frontend/src/api/enums.ts`, `endpoints/auditorEngagements.ts`, `endpoints/auditease.ts`, `hooks/auditorEngagements.ts`, `hooks/auditease.ts`
- Create: `frontend/src/components/auditease/requirements/RequirementsProgress.tsx` (+ test), `PriorityChip.tsx`, `NewRequirementModal.tsx` (+ test), `BulkImportModal.tsx`
- Rewrite: `frontend/src/pages/auditor/RequirementsTab.tsx`, `frontend/src/pages/company/auditease/RequirementsTab.tsx`
- Modify: `frontend/src/pages/auditor/AuditorEngagementWorkspace.tsx`

---

### Task 1: Data layer — new columns, `RequirementResponse`, query link (additive only)

**Files:**
- Create: `unit_tests/test_requirement_models.py`
- Modify: `app/models/auditease.py`
- Modify: `app/schemas/auditease.py`

**Interfaces (produces):**
- `ExpectedFormat(str, Enum)` members `text|file|any`
- `RequirementResponse` model: `id, requirement_id (FK CASCADE), responded_by (nullable FK company_users.id SET NULL), text_answer (Text nullable), document_id (FK documents.id SET NULL nullable), created_at`
- `RequirementRequest` new attrs: `seq_number (Integer nullable until backfill), priority (int default 1), due_date, company_eta, additional_details, period_from, period_to, entity (String(255)), responsible_person_id (FK company_users.id SET NULL), expected_format (SAEnum default any), auditor_notes, parent_requirement_id (self-FK RESTRICT), clarification_note` + property `requirement_id -> str`
- `Query.requirement_id: uuid.UUID | None` (SET NULL)

Purely additive — `RequestStatus` keeps `open`/`fulfilled`; every existing endpoint keeps working; suite stays green.

- [ ] **Step 1: Write failing model test**

Create `unit_tests/test_requirement_models.py`:

```python
import uuid


def test_requirement_request_has_lifecycle_columns():
    from app.models.auditease import RequirementRequest, ExpectedFormat
    r = RequirementRequest(engagement_id=uuid.uuid4(), raised_by=uuid.uuid4(),
                           title="t", description="d")
    assert r.priority == 1
    assert r.expected_format == ExpectedFormat.any
    r.seq_number = 7
    assert r.requirement_id == "REQ-007"


def test_requirement_response_model_exists():
    from app.models.auditease import RequirementResponse
    resp = RequirementResponse(requirement_id=uuid.uuid4())
    assert resp.text_answer is None and resp.document_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest unit_tests/test_requirement_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'ExpectedFormat'`

- [ ] **Step 3: Implement models**

In `app/models/auditease.py`:

Update imports (lines 1–9):

```python
import uuid
import enum
from decimal import Decimal
from datetime import date, datetime, timezone
from sqlalchemy import String, ForeignKey, Boolean, Enum as SAEnum, Integer, Numeric, Text, DateTime, Date, UniqueConstraint, text
```

Add next to `RequestStatus` (after line 58):

```python
class ExpectedFormat(str, enum.Enum):
    """Hint for how the company should answer. Never enforced."""
    text = "text"
    file = "file"
    any = "any"
```

Replace the `RequirementRequest` class body (lines 246–255):

```python
class RequirementRequest(Base, TimestampMixin):
    __tablename__ = "requirement_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    raised_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auditors.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, server_default="Requirement")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(SAEnum(RequestStatus, name="request_status"), default=RequestStatus.open, nullable=False)
    fulfilled_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # --- lifecycle metadata (Task 3 swaps the enum + drops fulfilled_document_id) ---
    seq_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default="1")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    company_eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    additional_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    entity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsible_person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True)
    expected_format: Mapped[ExpectedFormat] = mapped_column(SAEnum(ExpectedFormat, name="expected_format"), default=ExpectedFormat.any, nullable=False, server_default="any")
    auditor_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_requirement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("requirement_requests.id", ondelete="RESTRICT"), nullable=True)
    clarification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def requirement_id(self) -> str:
        return f"REQ-{self.seq_number or 0:03d}"
```

Add below it:

```python
class RequirementResponse(Base):
    """One company submission against a requirement. Append-only: a
    clarification loop produces multiple rows, preserving the audit trail."""
    __tablename__ = "requirement_responses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("requirement_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    # Nullable only for legacy rows backfilled from old `fulfilled` requirements,
    # where the original respondent was never recorded.
    responded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True)
    text_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
```

Inside `class Query` add one column after `opened_by`:

```python
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("requirement_requests.id", ondelete="SET NULL"), nullable=True)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest unit_tests/test_requirement_models.py tests/test_auditease.py -v`
Expected: all PASS

- [ ] **Step 5: Extend response schema additively**

In `app/schemas/auditease.py`: add `Field` to the pydantic import, `date` to the datetime import, `ExpectedFormat` to the models import. Replace lines 423–438:

```python
class RequirementRequestCreate(BaseModel):
    description: str
    title: Optional[str] = None
    priority: int = Field(default=1, ge=1, le=5)
    due_date: Optional[date] = None
    additional_details: Optional[str] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    entity: Optional[str] = None
    responsible_person_id: Optional[uuid.UUID] = None
    expected_format: ExpectedFormat = ExpectedFormat.any
    auditor_notes: Optional[str] = None
    parent_requirement_id: Optional[uuid.UUID] = None


class RequirementResponseOut(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    responded_by: Optional[uuid.UUID] = None
    responded_by_name: Optional[str] = None
    text_answer: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class RequirementRequestResponse(BaseModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    raised_by: uuid.UUID
    raised_by_name: Optional[str] = None
    title: str
    description: str
    status: RequestStatus
    fulfilled_document_id: Optional[uuid.UUID]
    seq_number: Optional[int] = None
    requirement_id_str: Optional[str] = None   # display id e.g. REQ-001; routers set this
    priority: int = 1
    due_date: Optional[date] = None
    company_eta: Optional[date] = None
    additional_details: Optional[str] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    entity: Optional[str] = None
    responsible_person_id: Optional[uuid.UUID] = None
    responsible_person_name: Optional[str] = None
    expected_format: ExpectedFormat = ExpectedFormat.any
    auditor_notes: Optional[str] = None
    parent_requirement_id: Optional[uuid.UUID] = None
    clarification_note: Optional[str] = None
    latest_response: Optional[RequirementResponseOut] = None
    responses: List[RequirementResponseOut] = []
    linked_query_count: int = 0
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
```

(`requirement_id_str` stays null until Task 3 wires `enrich_requirements` — acceptable interim.)

- [ ] **Step 6: Run full backend suite**

Run: `uv run pytest tests/ unit_tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/models/auditease.py app/schemas/auditease.py unit_tests/test_requirement_models.py
git commit -m "feat(auditease): requirement lifecycle data layer (responses, metadata cols)"
```

---

### Task 2: Bulk-import service (pure module)

**Files:**
- Create: `app/services/requirement_import.py`
- Create: `unit_tests/test_requirement_import.py`

**Interfaces (produces):**
- `IMPORT_HEADERS: list[str]`
- `build_template_xlsx() -> bytes`
- `parse_rows(rows: List[list]) -> List[dict]` — raises `RowError(row, message)`
- `import_requirements(db, company_id, engagement_id, raised_by, rows) -> List[RequirementRequest]` — raises `ImportRejected([{"row","message"}])`; rolls back on failure; does NOT commit (caller owns the transaction, mirroring `asset_import.import_assets`)
- Payload dict keys from `parse_rows`: `row, description, additional_details, period_from, period_to, entity, priority, due_date, responsible_email, expected_format ("text"|"file"|"any"), auditor_notes, parent_seq (int|None)`
- Parent rule: `parent_seq` must reference an earlier row (`parent_seq < current excel row - 1`) or an existing requirement — enforced structurally in `parse_rows` and referentially in `import_requirements`

- [ ] **Step 1: Write failing tests**

Create `unit_tests/test_requirement_import.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest unit_tests/test_requirement_import.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

Create `app/services/requirement_import.py`:

```python
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
                seq = int(parts[1])
                if seq >= n - 1:
                    raise ValueError(
                        f"Parent '{ref}' must already exist or appear in an earlier row")
                p["parent_seq"] = seq
            else:
                p["parent_seq"] = None
        except ValueError as e:
            raise RowError(n, str(e))
        payloads.append(p)
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest unit_tests/test_requirement_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/requirement_import.py unit_tests/test_requirement_import.py
git commit -m "feat(auditease): requirement bulk-import service"
```

---

### Task 3: Lifecycle cutover — routers, status enum, migration

Atomic by nature: the `RequestStatus` member swap touches both routers at once. Steps are sequenced so the suite is green at the END of the task (intermediate steps will be red — that is expected and called out).

**Files:**
- Modify: `app/models/auditease.py` (only `RequestStatus` + `RequirementRequest.status` default; drop `fulfilled_document_id`)
- Modify: `app/routers/auditor_engagements.py`
- Modify: `app/routers/auditease.py`
- Modify: `app/schemas/auditease.py` (`QueryResponse.requirement_id`, drop `fulfilled_document_id`)
- Modify: `tests/test_auditease.py` (rewrite `test_requirements_and_queries`; add import roundtrip test)
- Create: `alembic/versions/9f2c1a7d4e55_requirements_lifecycle.py`

**Interfaces (produces):**
- Auditor routes (all gated `area="requirements"`): `POST .../requirement-requests/{req_id}/review` body `{action:"accept"|"clarify", note?}` · `GET .../requirement-requests/import-template` · `POST .../requirement-requests/import` (multipart `file`) · extended create/update/delete/list · `create_query` accepts optional Form `requirement_id`
- Company routes: `POST .../requirement-requests/{req_id}/respond` JSON `{text_answer?, document_id?}` (at least one) · `PATCH .../requirement-requests/{req_id}/eta` `{company_eta}` · fulfill endpoint REMOVED
- Shared helper in auditor router: `enrich_requirements(db, engagement_id, req_list) -> list[dict]` — imported by the company router too

- [ ] **Step 1: Swap the enum + default**

In `app/models/auditease.py`:

```python
class RequestStatus(str, enum.Enum):
    pending = "pending"
    submitted = "submitted"
    clarification_needed = "clarification_needed"
    accepted = "accepted"
```

In `RequirementRequest`: change `default=RequestStatus.open` to `default=RequestStatus.pending`, and DELETE the `fulfilled_document_id` line.

- [ ] **Step 2: Rewrite lifecycle tests**

Replace `test_requirements_and_queries` in `tests/test_auditease.py` (line ~802):

```python
@pytest.mark.asyncio
async def test_requirements_and_queries(client: AsyncClient):
    await create_test_company(client, email="co3@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co3@a.com', password='pass1234')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "aud3@a.com", "password": "pass1234", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud3@a.com", "password": "pass1234"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    eng_id = await make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "aud3@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    # create with defaults -> REQ-001 pending P1
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
                             json={"description": "Provide bank statements"}, headers=aud_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["requirement_id_str"] == "REQ-001"
    assert body["priority"] == 1
    req_id = body["id"]

    # second requirement gets REQ-002; priority honored
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
                             json={"description": "Ledger dump", "priority": 3}, headers=aud_headers)
    assert resp.json()["requirement_id_str"] == "REQ-002"
    child_id = resp.json()["id"]

    # invalid transition: accept before anything submitted
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{req_id}/review",
                             json={"action": "accept"}, headers=aud_headers)
    assert resp.status_code == 400

    # respond with text only
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
                             json={"text_answer": "Will upload Monday"}, headers=co_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "submitted"

    # clarify loop
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{req_id}/review",
                             json={"action": "clarify", "note": "Statements missing for acct 3"}, headers=aud_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "clarification_needed"
    assert resp.json()["clarification_note"] == "Statements missing for acct 3"

    # resubmit appends history, clears note
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
                             json={"text_answer": "Here is acct 3"}, headers=co_headers)
    assert resp.json()["status"] == "submitted"
    assert resp.json()["clarification_note"] is None

    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests", headers=co_headers)
    reqs = {r["id"]: r for r in resp.json()}
    assert len(reqs[req_id]["responses"]) == 2

    # accept is terminal
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{req_id}/review",
                             json={"action": "accept"}, headers=aud_headers)
    assert resp.json()["status"] == "accepted"
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
                             json={"text_answer": "late"}, headers=co_headers)
    assert resp.status_code == 400
    # accepted requirements cannot be edited or deleted
    resp = await client.put(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{req_id}",
                            json={"description": "edited"}, headers=aud_headers)
    assert resp.status_code == 400
    resp = await client.delete(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{req_id}", headers=aud_headers)
    assert resp.status_code == 400

    # respond with a DocVault document
    files = {'file': ('ledgers.xlsx', b'data', 'application/octet-stream')}
    resp = await client.post("/api/v1/docvault/documents", data={'title': 'Ledgers'}, files=files, headers=co_headers)
    doc_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{child_id}/respond",
                             json={"document_id": doc_id}, headers=co_headers)
    assert resp.status_code == 200
    assert resp.json()["latest_response"]["document_id"] == doc_id

    # company ETA
    resp = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{child_id}/eta",
                              json={"company_eta": "2026-09-30"}, headers=co_headers)
    assert resp.status_code == 200
    assert resp.json()["company_eta"] == "2026-09-30"

    # respond requires at least one field
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{child_id}/respond",
                             json={}, headers=co_headers)
    assert resp.status_code == 422

    # queries link to requirements
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries",
                             data={"initial_message": "What is this?", "requirement_id": child_id}, headers=aud_headers)
    assert resp.status_code == 200
    assert resp.json()["requirement_id"] == child_id
```

Also update requirement-related assertions elsewhere that reference old statuses:
- `tests/test_auditease_multi_auditor.py`: replace `'open'` with `'pending'` in requirement visibility/count contexts (lines ~175–176, ~230, ~346–351) and any `'fulfilled'` with `'accepted'`. Read each occurrence first to confirm it is requirement-related.
- `frontend` counts come later (Task 8).

Add a parent/cycle guard test after the rewritten test:

```python
@pytest.mark.asyncio
async def test_requirement_parenting_guards(client: AsyncClient):
    await create_test_company(client, email="cop@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='cop@a.com', password='pass1234')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "audp@a.com", "password": "pass1234", "name": "Aud"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "audp@a.com", "password": "pass1234"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    eng_id = await make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "audp@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    mk = lambda desc, **kw: client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": desc, **kw}, headers=aud_headers)

    r_parent = (await mk("Parent")).json()
    r_child = (await mk("Child", parent_requirement_id=r_parent["id"])).json()

    # cross-engagement parent rejected
    eng2 = await make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng2}/auditors/invite", json={"email": "audp@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng2}/accept", headers=aud_headers)
    resp = await mk("Orphan", parent_requirement_id=r_parent["id"])
    resp = await client.post(f"/api/v1/auditor/engagements/{eng2}/requirement-requests",
                             json={"description": "Orphan", "parent_requirement_id": r_parent["id"]}, headers=aud_headers)
    assert resp.status_code == 400

    # cycle rejected: making the parent a child of its own child
    resp = await client.put(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{r_parent['id']}",
        json={"description": "Parent", "parent_requirement_id": r_child["id"]}, headers=aud_headers)
    assert resp.status_code == 400

    # delete blocked while children exist
    resp = await client.delete(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{r_parent['id']}", headers=aud_headers)
    assert resp.status_code == 400
    # child deletes fine
    resp = await client.delete(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{r_child['id']}", headers=aud_headers)
    assert resp.status_code == 200
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_auditease.py::test_requirements_and_queries -v`
Expected: FAIL — no `/review`, `/respond`, `/eta` routes yet (404s), plus possible import errors from removed enum members in routers. That is expected.

- [ ] **Step 4: Rework the auditor router**

In `app/routers/auditor_engagements.py`:

Imports — extend:

```python
from typing import Annotated, List, Literal, Optional
from datetime import date, datetime, timezone
from sqlalchemy import select, and_, func
from app.models.company import CompanyUser
from app.models.auditease import RequirementResponse
from fastapi import Response
```

(`Response` may already be imported — dedupe.)

Add helpers after `check_auditor_access` (line ~65):

```python
async def _next_seq(db: AsyncSession, engagement_id: uuid.UUID) -> int:
    res = await db.execute(
        select(func.max(RequirementRequest.seq_number)).where(RequirementRequest.engagement_id == engagement_id))
    return (res.scalar() or 0) + 1


async def enrich_requirements(db: AsyncSession, engagement_id: uuid.UUID, req_list) -> list[dict]:
    """Build API dicts for requirements: response history, linked-query counts,
    responsible-person names, computed display id."""
    from app.schemas.auditease import RequirementRequestResponse, RequirementResponseOut
    if not req_list:
        return []
    ids = [r.id for r in req_list]
    res_rows = (await db.execute(
        select(RequirementResponse).where(RequirementResponse.requirement_id.in_(ids))
        .order_by(RequirementResponse.created_at))).scalars().all()
    q_counts = (await db.execute(
        select(Query.requirement_id, func.count(Query.id))
        .where(Query.requirement_id.in_(ids)).group_by(Query.requirement_id))).all()
    count_map = {rid: c for rid, c in q_counts}

    user_ids = {r.responsible_person_id for r in req_list if r.responsible_person_id}
    names: dict = {}
    if user_ids:
        rows_ = (await db.execute(
            select(CompanyUser.id, CompanyUser.name).where(CompanyUser.id.in_(user_ids)))).all()
        names = {uid: uname for uid, uname in rows_}

    by_req: dict = {}
    for resp in res_rows:
        by_req.setdefault(resp.requirement_id, []).append(resp)

    out = []
    for r in req_list:
        d = RequirementRequestResponse.model_validate(r).model_dump(mode="json")
        hist = [RequirementResponseOut.model_validate(h).model_dump(mode="json")
                for h in by_req.get(r.id, [])]
        d["responses"] = hist
        d["latest_response"] = hist[-1] if hist else None
        d["linked_query_count"] = count_map.get(r.id, 0)
        d["responsible_person_name"] = names.get(r.responsible_person_id)
        d["requirement_id_str"] = r.requirement_id
        out.append(d)
    return out


async def _validate_refs(db: AsyncSession, eng, payload) -> None:
    if payload.parent_requirement_id:
        parent = (await db.execute(select(RequirementRequest).where(and_(
            RequirementRequest.id == payload.parent_requirement_id,
            RequirementRequest.engagement_id == eng.id)))).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent requirement not found in this engagement")
    if payload.responsible_person_id:
        user = (await db.execute(select(CompanyUser).where(and_(
            CompanyUser.id == payload.responsible_person_id,
            CompanyUser.company_id == eng.company_id)))).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=400, detail="Responsible person must belong to the client company")


def _would_cycle(new_parent_id: uuid.UUID, node_id: uuid.UUID, all_reqs) -> bool:
    children_map: dict = {}
    for r in all_reqs:
        children_map.setdefault(r.parent_requirement_id, []).append(r.id)

    def is_descendant(candidate: uuid.UUID, of: uuid.UUID, seen=frozenset()) -> bool:
        if candidate == of:
            return True
        if candidate in seen:
            return False
        return any(is_descendant(c, of, seen | {candidate})
                   for c in children_map.get(candidate, []))
    return is_descendant(new_parent_id, node_id)


def _apply_metadata(db_req: RequirementRequest, req: RequirementRequestCreate) -> None:
    db_req.title = (req.title.strip() if req.title and req.title.strip() else req.description.strip()[:255]) or "Requirement"
    db_req.description = req.description
    db_req.priority = req.priority
    db_req.due_date = req.due_date
    db_req.additional_details = req.additional_details
    db_req.period_from = req.period_from
    db_req.period_to = req.period_to
    db_req.entity = req.entity
    db_req.responsible_person_id = req.responsible_person_id
    db_req.expected_format = req.expected_format
    db_req.auditor_notes = req.auditor_notes
    db_req.parent_requirement_id = req.parent_requirement_id
```

Replace `create_requirement` (lines 277–303):

```python
@router.post("/engagements/{engagement_id}/requirement-requests", response_model=RequirementRequestResponse)
async def create_requirement(
    engagement_id: uuid.UUID,
    req: RequirementRequestCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")
    await _validate_refs(db, eng, req)

    db_req = RequirementRequest(
        engagement_id=engagement_id,
        raised_by=current_auditor.id,
        seq_number=await _next_seq(db, engagement_id),
    )
    _apply_metadata(db_req, req)
    db.add(db_req)
    await db.flush()

    await log_activity(db, eng.company_id, current_auditor.id,
                 "requirement.raised", "requirement_request", db_req.id,
                 metadata_={"title": db_req.title},
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
    await db.commit()
    await db.refresh(db_req)
    return (await enrich_requirements(db, engagement_id, [db_req]))[0]
```

Replace `update_requirement` (lines 306–328):

```python
@router.put("/engagements/{engagement_id}/requirement-requests/{req_id}", response_model=RequirementRequestResponse)
async def update_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    req: RequirementRequestCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")

    db_req = (await db.execute(select(RequirementRequest).where(and_(
        RequirementRequest.id == req_id, RequirementRequest.engagement_id == engagement_id,
        RequirementRequest.raised_by == current_auditor.id)))).scalar_one_or_none()
    if not db_req:
        raise HTTPException(status_code=404, detail="Requirement request not found")
    if db_req.status == RequestStatus.accepted:
        raise HTTPException(status_code=400, detail="Cannot edit an accepted requirement request")

    new_title = (req.title.strip() if req.title and req.title.strip()
                 else req.description.strip()[:255]) or "Requirement"
    text_changed = (req.description.strip() != db_req.description.strip()) or (new_title != db_req.title)
    if text_changed and db_req.status != RequestStatus.pending:
        raise HTTPException(status_code=400, detail="The requirement text can only be edited while pending")

    if req.parent_requirement_id != db_req.parent_requirement_id:
        if req.parent_requirement_id == db_req.id:
            raise HTTPException(status_code=400, detail="A requirement cannot be its own parent")
        if req.parent_requirement_id is not None:
            parent = (await db.execute(select(RequirementRequest).where(and_(
                RequirementRequest.id == req.parent_requirement_id,
                RequirementRequest.engagement_id == engagement_id)))).scalar_one_or_none()
            if not parent:
                raise HTTPException(status_code=400, detail="Parent requirement not found in this engagement")
            all_reqs = (await db.execute(select(RequirementRequest).where(
                RequirementRequest.engagement_id == engagement_id))).scalars().all()
            if _would_cycle(req.parent_requirement_id, db_req.id, all_reqs):
                raise HTTPException(status_code=400, detail="Cannot move a requirement under its own descendant")
    if req.responsible_person_id:
        await _validate_refs(db, eng, req)

    _apply_metadata(db_req, req)
    await db.commit()
    await db.refresh(db_req)
    return (await enrich_requirements(db, engagement_id, [db_req]))[0]
```

Replace `delete_requirement` (lines 331–353): keep structure but change the status guard and add child check between the 404 and activity log:

```python
    if db_req.status != RequestStatus.pending:
        raise HTTPException(status_code=400, detail="Only pending requirements can be deleted")
    child = (await db.execute(select(RequirementRequest.id).where(
        RequirementRequest.parent_requirement_id == req_id).limit(1))).scalar_one_or_none()
    if child:
        raise HTTPException(status_code=400, detail="Delete or re-parent child requirements first")
```

Replace `list_requirements` (lines 484–494):

```python
@router.get("/engagements/{engagement_id}/requirement-requests", response_model=List[RequirementRequestResponse])
async def list_requirements(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")
    req_list = (await db.execute(
        select(RequirementRequest).where(RequirementRequest.engagement_id == engagement_id)
        .order_by(RequirementRequest.seq_number.nulls_first(), RequirementRequest.created_at)
    )).scalars().all()
    await attach_actor_names(db, req_list, "raised_by", "raised_by_name")
    return await enrich_requirements(db, engagement_id, req_list)
```

Add the review endpoint after `delete_requirement`:

```python
class RequirementReviewCreate(BaseModel):
    action: Literal["accept", "clarify"]
    note: Optional[str] = None


@router.post("/engagements/{engagement_id}/requirement-requests/{req_id}/review",
             response_model=RequirementRequestResponse)
async def review_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    payload: RequirementReviewCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")
    db_req = (await db.execute(select(RequirementRequest).where(and_(
        RequirementRequest.id == req_id,
        RequirementRequest.engagement_id == engagement_id)))).scalar_one_or_none()
    if not db_req:
        raise HTTPException(status_code=404, detail="Requirement request not found")

    if payload.action == "accept":
        if db_req.status != RequestStatus.submitted:
            raise HTTPException(status_code=400, detail="Only submitted requirements can be accepted")
        db_req.status = RequestStatus.accepted
        event = "requirement.accepted"
    else:
        if db_req.status in (RequestStatus.clarification_needed, RequestStatus.accepted):
            raise HTTPException(status_code=400, detail="Requirement already needs clarification or is accepted")
        db_req.status = RequestStatus.clarification_needed
        db_req.clarification_note = payload.note
        event = "requirement.clarification"

    await log_activity(db, eng.company_id, current_auditor.id,
                 event, "requirement_request", db_req.id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
    await db.commit()
    await db.refresh(db_req)
    return (await enrich_requirements(db, engagement_id, [db_req]))[0]
```

Wire the query link into `create_query` (line ~398): add parameter

```python
    requirement_id: Annotated[Optional[uuid.UUID], Form()] = None,
```

and after `await db.flush()` insert:

```python
    if requirement_id is not None:
        target = (await db.execute(select(RequirementRequest.id).where(and_(
            RequirementRequest.id == requirement_id,
            RequirementRequest.engagement_id == engagement_id)))).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=400, detail="Requirement not found in this engagement")
        db_query.requirement_id = requirement_id
```

In `app/schemas/auditease.py`, add to `QueryResponse`: `requirement_id: Optional[uuid.UUID] = None`, and DELETE `fulfilled_document_id` from `RequirementRequestResponse`.

- [ ] **Step 5: Rework the company router**

In `app/routers/auditease.py`:

Extend imports: `date` on the datetime line; `model_validator` on the pydantic line; `RequirementResponse` on the models line; `GrantStatus`, `AuditorEngagementGrant` if not already present; `func` unused here. Add near the top:

```python
from app.routers.auditor_engagements import enrich_requirements
```

Replace the whole fulfill block (lines 1288–1329) — including deleting `RequirementFulfill` and `fulfill_requirement` — with:

```python
class RequirementRespond(BaseModel):
    text_answer: Optional[str] = None
    document_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def _needs_something(self):
        if not self.text_answer and not self.document_id:
            raise ValueError("Provide a text answer and/or a document")
        return self


class CompanyEtaUpdate(BaseModel):
    company_eta: Optional[date] = None


async def grant_document_access_to_auditors(db, engagement_id, document_id) -> None:
    """Give every accepted auditor with the requirements area read access to a
    submitted document (shared-workspace rule)."""
    from app.models.docvault import DocumentAccessOverride, PrincipalType
    rows = (await db.execute(
        select(AuditorEngagementGrant.auditor_id, AuditorEngagementGrant.area_permissions)
        .where(and_(
            AuditorEngagementGrant.engagement_id == engagement_id,
            AuditorEngagementGrant.status == GrantStatus.accepted,
        )))).all()
    existing = set((await db.execute(
        select(DocumentAccessOverride.principal_id).where(
            DocumentAccessOverride.document_id == document_id,
            DocumentAccessOverride.principal_type == PrincipalType.auditor,
        ))).scalars().all())
    for auditor_id, perms in rows:
        if not area_enabled(perms, "requirements") or auditor_id in existing:
            continue
        db.add(DocumentAccessOverride(
            document_id=document_id,
            principal_type=PrincipalType.auditor,
            principal_id=auditor_id,
            permission_level="read",
        ))


async def _owned_requirement(db, current_user, engagement_id, req_id) -> RequirementRequest:
    result = await db.execute(select(AuditEngagement).where(and_(
        AuditEngagement.id == engagement_id,
        AuditEngagement.company_id == current_user.company_id)))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
    req = (await db.execute(select(RequirementRequest).where(and_(
        RequirementRequest.id == req_id,
        RequirementRequest.engagement_id == engagement_id)))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement request not found")
    return req


@router.post("/engagements/{engagement_id}/requirement-requests/{req_id}/respond",
             response_model=RequirementRequestResponse)
async def respond_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    payload: RequirementRespond,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    from app.models.docvault import Document
    req = await _owned_requirement(db, current_user, engagement_id, req_id)
    if req.status not in (RequestStatus.pending, RequestStatus.clarification_needed):
        raise HTTPException(status_code=400, detail=f"Cannot respond to a {req.status.value} requirement")

    if payload.document_id is not None:
        doc_ok = (await db.execute(select(Document.id).where(and_(
            Document.id == payload.document_id,
            Document.company_id == current_user.company_id)))).scalar_one_or_none()
        if not doc_ok:
            raise HTTPException(status_code=404, detail="Document not found")

    db.add(RequirementResponse(
        requirement_id=req.id,
        responded_by=current_user.id,
        text_answer=payload.text_answer,
        document_id=payload.document_id,
    ))
    req.status = RequestStatus.submitted
    req.clarification_note = None
    if payload.document_id is not None:
        await grant_document_access_to_auditors(db, engagement_id, payload.document_id)

    await log_activity(db, current_user.company_id, current_user.id,
                 "requirement.submitted", "requirement_request", req.id,
                 actor_type=ActorType.company_user, engagement_id=engagement_id)
    await db.commit()
    await db.refresh(req)
    return (await enrich_requirements(db, engagement_id, [req]))[0]


@router.patch("/engagements/{engagement_id}/requirement-requests/{req_id}/eta",
              response_model=RequirementRequestResponse)
async def set_requirement_eta(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    payload: CompanyEtaUpdate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    req = await _owned_requirement(db, current_user, engagement_id, req_id)
    if req.status == RequestStatus.accepted:
        raise HTTPException(status_code=400, detail="Cannot change ETA on an accepted requirement")

    req.company_eta = payload.company_eta
    await log_activity(db, current_user.company_id, current_user.id,
                 "requirement.eta_set", "requirement_request", req.id,
                 metadata_={"company_eta": str(payload.company_eta) if payload.company_eta else None},
                 actor_type=ActorType.company_user, engagement_id=engagement_id)
    await db.commit()
    await db.refresh(req)
    return (await enrich_requirements(db, engagement_id, [req]))[0]
```

Update the company `list_requirements` (lines 1271–1285): keep ownership check as-is, then replace the last three lines with:

```python
    req_list = (await db.execute(
        select(RequirementRequest).where(RequirementRequest.engagement_id == engagement_id)
        .order_by(RequirementRequest.seq_number.nulls_first(), RequirementRequest.created_at)
    )).scalars().all()
    await attach_actor_names(db, req_list, "raised_by", "raised_by_name")
    return await enrich_requirements(db, engagement_id, req_list)
```

Check imports available in this file: `area_enabled` (from `app.services.auditor_access`) — add if missing.

- [ ] **Step 6: Run lifecycle tests**

Run: `grep -rn "RequestStatus.open\|RequestStatus.fulfilled" app/ tests/` — must return nothing (fix any stragglers).
Run: `uv run pytest tests/test_auditease.py tests/test_auditease_multi_auditor.py -v`
Expected: PASS (iterate on fallout)

- [ ] **Step 6b: Extend area-gating tests**

Open `tests/test_auditease_multi_auditor.py` and find the existing test asserting 403 for a requirements-revoked auditor (around lines 175–176). Using the SAME revocation mechanism that test already uses, add assertions for every new endpoint so none of them leak past `check_auditor_access(..., area="requirements")`:

```python
    # all new lifecycle endpoints must honor the revoked requirements area
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{req_id}/review",
                             json={"action": "clarify"}, headers=revoked_headers)
    assert resp.status_code == 403
    resp = await client.get(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/import-template",
        headers=revoked_headers)
    assert resp.status_code == 403
    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/import",
        files={"file": ("x.xlsx", b"x", "application/octet-stream")},
        headers=revoked_headers)
    assert resp.status_code == 403
```

(`req_id` comes from a requirement created by the fully-permitted auditor earlier in that test; reuse whatever variables the existing test establishes. If the file instead gates via a helper fixture, mirror it.)

Company-side cross-tenant protection for `/respond` and `/eta` is already enforced by `_owned_requirement`'s 404-on-wrong-company behavior; add one assertion to the existing cross-tenant test in `tests/test_auditease.py::test_auditease_cross_tenant_leak`:

```python
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{uuid.uuid4()}/respond",
                             json={"text_answer": "hi"}, headers=headers_b)
    assert resp.status_code == 404
```

(add `import uuid` at top of the file if missing).

Run: `uv run pytest tests/test_auditease_multi_auditor.py tests/test_auditease.py -q`
Expected: PASS

- [ ] **Step 7: Write the Alembic migration**

Create `alembic/versions/9f2c1a7d4e55_requirements_lifecycle.py`:

```python
"""requirements lifecycle

Revision ID: 9f2c1a7d4e55
Revises: ff50c2eb5b28
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "9f2c1a7d4e55"
down_revision = "ff50c2eb5b28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Status enum swap. PG cannot USE a newly added enum value in the same
    #    transaction that adds it, so flip the column to varchar first.
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN status TYPE varchar USING status::text")
    op.execute("UPDATE requirement_requests SET status = 'pending' WHERE status = 'open'")
    op.execute("UPDATE requirement_requests SET status = 'accepted' WHERE status = 'fulfilled'")
    op.execute("DROP TYPE IF EXISTS request_status")
    op.execute("CREATE TYPE request_status AS ENUM "
               "('pending', 'submitted', 'clarification_needed', 'accepted')")
    op.execute("ALTER TABLE requirement_requests "
               "ALTER COLUMN status TYPE request_status USING status::request_status")

    # 2. Metadata columns.
    op.add_column("requirement_requests", sa.Column("seq_number", sa.Integer(), nullable=True))
    op.add_column("requirement_requests", sa.Column("priority", sa.Integer(), server_default="1", nullable=False))
    op.add_column("requirement_requests", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("company_eta", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("additional_details", sa.Text(), nullable=True))
    op.add_column("requirement_requests", sa.Column("period_from", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("period_to", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("entity", sa.String(255), nullable=True))
    op.add_column("requirement_requests", sa.Column(
        "responsible_person_id", UUID(as_uuid=True),
        sa.ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("requirement_requests", sa.Column(
        "expected_format", sa.Enum("text", "file", "any", name="expected_format"),
        server_default="any", nullable=False))
    op.add_column("requirement_requests", sa.Column("auditor_notes", sa.Text(), nullable=True))
    op.add_column("requirement_requests", sa.Column(
        "parent_requirement_id", UUID(as_uuid=True),
        sa.ForeignKey("requirement_requests.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("requirement_requests", sa.Column("clarification_note", sa.Text(), nullable=True))

    # 3. Backfill per-engagement sequence numbers (stable created-order), then lock it down.
    op.execute("""
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY engagement_id ORDER BY created_at, id) AS rn
            FROM requirement_requests
        )
        UPDATE requirement_requests r SET seq_number = n.rn FROM numbered n WHERE n.id = r.id
    """)
    op.create_unique_constraint(
        "uq_requirement_seq", "requirement_requests", ["engagement_id", "seq_number"])

    # 4. Legacy fulfilled documents become the first response row; then drop the column.
    op.execute("""
        INSERT INTO requirement_responses
            (id, requirement_id, responded_by, text_answer, document_id, created_at)
        SELECT gen_random_uuid(), id, NULL, NULL, fulfilled_document_id, updated_at
        FROM requirement_requests
        WHERE fulfilled_document_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM requirement_responses rr
              WHERE rr.requirement_id = requirement_requests.id)
    """)
    op.drop_column("requirement_requests", "fulfilled_document_id")

    # 5. Responses table (created AFTER the legacy insert above references it).
    op.create_table(
        "requirement_responses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("requirement_id", UUID(as_uuid=True),
                  sa.ForeignKey("requirement_requests.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("responded_by", UUID(as_uuid=True),
                  sa.ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("text_answer", sa.Text(), nullable=True),
        sa.Column("document_id", UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 6. Query linkage.
    op.add_column("queries", sa.Column(
        "requirement_id", UUID(as_uuid=True),
        sa.ForeignKey("requirement_requests.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("queries", "requirement_id")
    op.add_column("requirement_requests", sa.Column(
        "fulfilled_document_id", UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True))
    op.execute("""
        UPDATE requirement_requests r SET fulfilled_document_id = sub.document_id
        FROM (
            SELECT DISTINCT ON (requirement_id) requirement_id, document_id
            FROM requirement_responses WHERE document_id IS NOT NULL
            ORDER BY requirement_id, created_at DESC
        ) sub WHERE sub.requirement_id = r.id
    """)
    op.drop_table("requirement_responses")
    op.drop_constraint("uq_requirement_seq", "requirement_requests", type_="unique")
    for col in ("seq_number", "priority", "due_date", "company_eta", "additional_details",
                "period_from", "period_to", "entity", "responsible_person_id",
                "expected_format", "auditor_notes", "parent_requirement_id",
                "clarification_note"):
        op.drop_column("requirement_requests", col)
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN status TYPE varchar USING status::text")
    op.execute("UPDATE requirement_requests SET status = 'open' WHERE status = 'pending'")
    op.execute("UPDATE requirement_requests SET status = 'fulfilled' "
               "WHERE status IN ('submitted', 'clarification_needed', 'accepted')")
    op.execute("DROP TYPE request_status")
    op.execute("CREATE TYPE request_status AS ENUM ('open', 'fulfilled')")
    op.execute("ALTER TABLE requirement_requests "
               "ALTER COLUMN status TYPE request_status USING status::request_status")
```

IMPORTANT ordering note baked into the migration above: step 4's `INSERT INTO requirement_responses` runs BEFORE step 5 creates the table — flip steps 4 and 5 if your Postgres complains: create the table first, then run the legacy insert. Verify by running the upgrade; if it errors with "relation does not exist", reorder and re-run.

- [ ] **Step 8: Verify the migration round-trip**

Start the dev DB (`docker-compose up -d postgres` if needed), then:
Run: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
Expected: all three succeed.

- [ ] **Step 9: Add import-template/import endpoints + roundtrip test**

In `app/routers/auditor_engagements.py`, append after the review endpoint:

```python
@router.get("/engagements/{engagement_id}/requirement-requests/import-template")
async def download_requirement_import_template(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")
    from app.services.requirement_import import build_template_xlsx
    content = build_template_xlsx()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="requirements_import_template.xlsx"'},
    )


@router.post("/engagements/{engagement_id}/requirement-requests/import", response_model=dict)
async def import_requirements_endpoint(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")
    from app.services.import_service import load_sheet
    from app.services.requirement_import import ImportRejected, RowError, import_requirements

    content = await file.read()
    try:
        _, rows = load_sheet(file.filename or "", content, sheet_name=None)
        created = await import_requirements(
            db, eng.company_id, engagement_id, current_auditor.id, rows)
    except ImportRejected as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors)
    except RowError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=[{"row": e.row, "message": e.message}])

    for unit in created:
        await log_activity(db, eng.company_id, current_auditor.id,
                           "requirement.bulk_imported", "requirement_request", unit.id,
                           metadata_={"source": "import"},
                           actor_type=ActorType.auditor, engagement_id=engagement_id)
    await db.commit()
    return {"created_count": len(created)}
```

Append to `tests/test_auditease.py`:

```python
@pytest.mark.asyncio
async def test_requirement_bulk_import_roundtrip(client: AsyncClient):
    import io
    import openpyxl
    from app.services.requirement_import import build_template_xlsx

    await create_test_company(client, email="coi@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='coi@a.com', password='pass1234')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "audi@a.com", "password": "pass1234", "name": "Aud"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "audi@a.com", "password": "pass1234"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    eng_id = await make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "audi@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    # template downloads
    resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/import-template",
                            headers=aud_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # build a filled sheet: two parents + one child referencing row order REQ-001
    wb = openpyxl.load_workbook(io.BytesIO(build_template_xlsx()))
    ws = wb["Requirements"]
    ws.delete_rows(2)  # drop example row
    ws.append(["Bulk req A"])
    ws.append(["Bulk req B", None, None, None, None, 4])
    ws.append(["Child of A", None, None, None, None, None, None, None, None, None, "REQ-001"])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)

    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/import",
        files={"file": ("reqs.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=aud_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["created_count"] == 3

    resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", headers=aud_headers)
    by_desc = {r["description"]: r for r in resp.json()}
    assert by_desc["Bulk req A"]["requirement_id_str"] == "REQ-001"
    assert by_desc["Bulk req B"]["priority"] == 4
    assert by_desc["Child of A"]["parent_requirement_id"] == by_desc["Bulk req A"]["id"]

    # all-or-nothing: one bad row aborts everything
    wb2 = openpyxl.load_workbook(io.BytesIO(build_template_xlsx()))
    ws2 = wb2["Requirements"]
    ws2.delete_rows(2)
    ws2.append(["Good row"])
    ws2.append(["Bad row", None, "not-a-date"])
    buf2 = io.BytesIO(); wb2.save(buf2); buf2.seek(0)
    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/import",
        files={"file": ("bad.xlsx", buf2.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=aud_headers)
    assert resp.status_code == 422
    assert any(e["row"] == 3 for e in resp.json()["detail"])

    resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", headers=aud_headers)
    assert len(resp.json()) == 3  # nothing extra persisted
```

- [ ] **Step 10: Full backend suite**

Run: `uv run pytest tests/ unit_tests/ -q`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat(auditease): reviewed requirement lifecycle (statuses, review, respond, eta, bulk import)"
```

---

### Task 4: Frontend API layer — types, enums, endpoints, hooks

**Files:**
- Regenerate: `frontend/src/api/schema.d.ts`
- Modify: `frontend/src/api/enums.ts`
- Modify: `frontend/src/api/endpoints/auditorEngagements.ts`
- Modify: `frontend/src/api/endpoints/auditease.ts`
- Modify: `frontend/src/api/hooks/auditorEngagements.ts`
- Modify: `frontend/src/api/hooks/auditease.ts`

**Interfaces (produces):**
- `REQUEST_STATUS = ['pending', 'submitted', 'clarification_needed', 'accepted']`
- `auditorEngagementsApi.updateRequirement / deleteRequirement / reviewRequirement / downloadImportTemplate / bulkImportRequirements`
- `auditeaseCompanyApi.respondRequirement / setRequirementEta`
- Hooks: `useAuditorUpdateRequirement, useAuditorDeleteRequirement, useAuditorReviewRequirement, useAuditorDownloadImportTemplate, useAuditorBulkImportRequirements, useRespondToRequirement, useSetRequirementEta`

- [ ] **Step 1: Regenerate schema types**

Start backend (`uv run uvicorn app.main:app --port 8000`), then:
Run: `cd frontend && npm run gen:api`
Expected: `schema.d.ts` contains `"pending" | "submitted" | "clarification_needed" | "accepted"`, `RequirementResponseOut`, `requirement_id_str`.

- [ ] **Step 2: Enums**

`frontend/src/api/enums.ts` line 60 — replace:

```ts
export const REQUEST_STATUS = ['pending', 'submitted', 'clarification_needed', 'accepted'] as const
```

If the compile-time guard (`satisfies readonly S['RequestStatus'][]`) fails because `open/fulfilled` remain in the generated union, re-run gen (Step 1) until the generated type matches; do not weaken the guard.

In `STATUS_TONE` (~line 144) replace the `fulfilled: 'success',` entry with:

```ts
  // RequestStatus
  pending: 'neutral',
  submitted: 'info',
  clarification_needed: 'warning',
  accepted: 'success',
```

- [ ] **Step 3: Endpoints**

Append inside the api object in `frontend/src/api/endpoints/auditorEngagements.ts`:

```ts
  updateRequirement: (id: string, reqId: string, body: RequirementRequestCreate) =>
    auditorClient.put<RequirementRequestResponse>(
      `/api/v1/auditor/engagements/${id}/requirement-requests/${reqId}`, { body }),
  deleteRequirement: (id: string, reqId: string) =>
    auditorClient.delete<void>(`/api/v1/auditor/engagements/${id}/requirement-requests/${reqId}`),
  reviewRequirement: (id: string, reqId: string, body: { action: 'accept' | 'clarify'; note?: string }) =>
    auditorClient.post<RequirementRequestResponse>(
      `/api/v1/auditor/engagements/${id}/requirement-requests/${reqId}/review`, { body }),
  downloadImportTemplate: (id: string) =>
    auditorClient.get<Blob>(
      `/api/v1/auditor/engagements/${id}/requirement-requests/import-template`,
      { responseType: 'blob' },
    ),
  bulkImportRequirements: (id: string, formData: FormData) =>
    auditorClient.post<{ created_count: number }>(
      `/api/v1/auditor/engagements/${id}/requirement-requests/import`, { formData }),
```

Check `frontend/src/api/http.ts`: if the client wrapper lacks `put`, add it following the existing `post` pattern.

Append inside the api object in `frontend/src/api/endpoints/auditease.ts`:

```ts
  respondRequirement: (engagementId: string, reqId: string,
                       body: { text_answer?: string; document_id?: string }) =>
    companyClient.post<RequirementRequestResponse>(
      `/api/v1/auditease/engagements/${engagementId}/requirement-requests/${reqId}/respond`,
      { body }),
  setRequirementEta: (engagementId: string, reqId: string,
                      body: { company_eta: string | null }) =>
    companyClient.patch<RequirementRequestResponse>(
      `/api/v1/auditease/engagements/${engagementId}/requirement-requests/${reqId}/eta`,
      { body }),
```

(Backend verbs: respond = POST, eta = PATCH. Match exactly.)

- [ ] **Step 4: Hooks**

Append to `frontend/src/api/hooks/auditorEngagements.ts`:

```ts
export function useAuditorUpdateRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, reqId, body }: { engagementId: string; reqId: string; body: import('@/api/types').RequirementRequestCreate }) =>
      auditorEngagementsApi.updateRequirement(engagementId, reqId, body),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditor', 'requirements', engagementId] }),
  })
}

export function useAuditorDeleteRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, reqId }: { engagementId: string; reqId: string }) =>
      auditorEngagementsApi.deleteRequirement(engagementId, reqId),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditor', 'requirements', engagementId] }),
  })
}

export function useAuditorReviewRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, reqId, body }: { engagementId: string; reqId: string; body: { action: 'accept' | 'clarify'; note?: string } }) =>
      auditorEngagementsApi.reviewRequirement(engagementId, reqId, body),
    onSuccess: (_r, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ['auditor', 'requirements', engagementId] })
      qc.invalidateQueries({ queryKey: ['company', 'activity'] })
    },
  })
}

export function useAuditorDownloadImportTemplate() {
  return useMutation({
    mutationFn: (engagementId: string) => auditorEngagementsApi.downloadImportTemplate(engagementId),
  })
}

export function useAuditorBulkImportRequirements() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, formData }: { engagementId: string; formData: FormData }) =>
      auditorEngagementsApi.bulkImportRequirements(engagementId, formData),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditor', 'requirements', engagementId] }),
  })
}
```

Append to `frontend/src/api/hooks/auditease.ts`:

```ts
export function useRespondToRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, reqId, body }: { engagementId: string; reqId: string; body: { text_answer?: string; document_id?: string } }) =>
      auditeaseCompanyApi.respondRequirement(engagementId, reqId, body),
    onSuccess: (_r, { engagementId }) => {
      qc.invalidateQueries({ queryKey: ['auditease', 'requirements', engagementId] })
      qc.invalidateQueries({ queryKey: ['company', 'activity'] })
    },
  })
}

export function useSetRequirementEta() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, reqId, body }: { engagementId: string; reqId: string; body: { company_eta: string | null } }) =>
      auditeaseCompanyApi.setRequirementEta(engagementId, reqId, body),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditease', 'requirements', engagementId] }),
  })
}
```

Keep `useFulfillRequirement` for now (Task 8 removes it with its last consumer).

- [ ] **Step 5: Typecheck + commit**

Run: `cd frontend && npx tsc -b --noEmit && npm run lint`
Expected: PASS

```bash
git add frontend/src
git commit -m "feat(auditease-web): requirements lifecycle api layer"
```

---

### Task 5: Shared UI — progress strip + priority chip

**Files:**
- Create: `frontend/src/components/auditease/requirements/RequirementsProgress.tsx`
- Create: `frontend/src/components/auditease/requirements/RequirementsProgress.test.tsx`
- Create: `frontend/src/components/auditease/requirements/PriorityChip.tsx`

**Interfaces (produces):**
- `computeCounts(requirements: RequirementLite[]): Record<RequestStatusFilter, number>` (pure)
- `percentComplete(requirements: RequirementLite[]): number` (pure)
- `RequirementsProgress({ requirements, activeFilter, onFilterChange })` where `type RequestStatusFilter = 'pending' | 'submitted' | 'clarification_needed' | 'accepted'`, `interface RequirementLite { status: string }`
- `PriorityChip({ priority }: { priority: number })`

Before writing, read `frontend/src/components/ui/StatusBadge.tsx` and the Tailwind config to confirm design tokens (`status-success`, `status-warning`, `rounded-pill`, `ease-spring`). Substitute whatever tokens actually exist — the classes below are the intent.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/auditease/requirements/RequirementsProgress.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { computeCounts, percentComplete } from './RequirementsProgress'

const req = (status: string) => ({ status })

describe('computeCounts', () => {
  it('counts each bucket', () => {
    expect(computeCounts([
      req('accepted'), req('accepted'), req('submitted'),
      req('clarification_needed'), req('pending'),
    ])).toEqual({ accepted: 2, submitted: 1, clarification_needed: 1, pending: 1 })
  })

  it('handles empty list', () => {
    expect(computeCounts([]).accepted).toBe(0)
  })

  it('ignores unknown statuses', () => {
    expect(computeCounts([req('weird')])).toEqual({
      accepted: 0, submitted: 0, clarification_needed: 0, pending: 0,
    })
  })
})

describe('percentComplete', () => {
  it('is accepted share rounded', () => {
    expect(percentComplete([req('accepted'), req('pending')])).toBe(50)
    expect(percentComplete([])).toBe(0)
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/components/auditease/requirements/RequirementsProgress.test.tsx`
Expected: FAIL — module missing

- [ ] **Step 3: Implement**

`frontend/src/components/auditease/requirements/RequirementsProgress.tsx`:

```tsx
import { motion } from 'framer-motion'
import { CountUp } from '@/components/ui'

export type RequestStatusFilter = 'pending' | 'submitted' | 'clarification_needed' | 'accepted'

export interface RequirementLite {
  status: string
}

const BUCKETS: { key: RequestStatusFilter; label: string; bar: string; dot: string }[] = [
  { key: 'accepted', label: 'Accepted', bar: 'bg-status-success', dot: 'bg-status-success' },
  { key: 'submitted', label: 'Submitted', bar: 'bg-accent', dot: 'bg-accent' },
  { key: 'clarification_needed', label: 'Clarification', bar: 'bg-status-warning', dot: 'bg-status-warning' },
  { key: 'pending', label: 'Pending', bar: 'bg-border-strong', dot: 'bg-text-muted' },
]

export function computeCounts(requirements: RequirementLite[]): Record<RequestStatusFilter, number> {
  const counts = { accepted: 0, submitted: 0, clarification_needed: 0, pending: 0 }
  for (const r of requirements) {
    if (r.status in counts) counts[r.status as RequestStatusFilter] += 1
  }
  return counts
}

export function percentComplete(requirements: RequirementLite[]): number {
  if (!requirements.length) return 0
  const accepted = requirements.filter((r) => r.status === 'accepted').length
  return Math.round((accepted / requirements.length) * 100)
}

export function RequirementsProgress({
  requirements,
  activeFilter,
  onFilterChange,
}: {
  requirements: RequirementLite[]
  activeFilter: RequestStatusFilter | null
  onFilterChange: (f: RequestStatusFilter | null) => void
}) {
  const counts = computeCounts(requirements)
  const total = requirements.length || 1
  return (
    <div className="rounded-card border border-border bg-bg-surface p-4 shadow-card">
      <p className="text-sm font-medium text-text-secondary">
        <CountUp value={percentComplete(requirements)} suffix="%"
                 className="font-semibold text-text-primary" />{' '}
        complete · {requirements.length} requirement{requirements.length === 1 ? '' : 's'}
      </p>
      <div className="mt-3 flex h-2.5 w-full gap-0.5 overflow-hidden rounded-full bg-bg-raised">
        {BUCKETS.map((b) =>
          counts[b.key] > 0 ? (
            <motion.div
              key={b.key}
              className={`${b.bar} h-full rounded-full`}
              initial={{ width: 0 }}
              animate={{ width: `${(counts[b.key] / total) * 100}%` }}
              transition={{ type: 'spring', stiffness: 120, damping: 20 }}
            />
          ) : null,
        )}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {BUCKETS.map((b) => (
          <button
            key={b.key}
            onClick={() => onFilterChange(activeFilter === b.key ? null : b.key)}
            className={`flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-xs font-medium transition-all duration-150 ease-spring ${
              activeFilter === b.key
                ? 'border-border-strong bg-bg-raised text-text-primary'
                : 'border-transparent text-text-secondary hover:bg-bg-raised'
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${b.dot}`} />
            {b.label}
            <span className="tabular-nums"><CountUp value={counts[b.key]} duration={500} /></span>
          </button>
        ))}
      </div>
    </div>
  )
}
```

`frontend/src/components/auditease/requirements/PriorityChip.tsx`:

```tsx
const TONES: Record<number, string> = {
  1: 'border-border bg-bg-surface text-text-muted',
  2: 'border-border-strong bg-bg-surface text-text-secondary',
  3: 'border-sky-300/60 bg-sky-50 text-sky-700 dark:border-sky-700 dark:bg-sky-950 dark:text-sky-300',
  4: 'border-orange-300/60 bg-orange-50 text-orange-700 dark:border-orange-700 dark:bg-orange-950 dark:text-orange-300',
  5: 'border-red-300/60 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-300',
}

/** P1 is quiet by design — default priority should not shout. */
export function PriorityChip({ priority }: { priority: number }) {
  const p = Math.min(5, Math.max(1, Math.round(priority)))
  return (
    <span className={`inline-flex items-center rounded-pill border px-2 py-0.5 text-xs font-semibold ${TONES[p]}`}>
      P{p}
    </span>
  )
}
```

- [ ] **Step 4: Run tests + typecheck**

Run: `cd frontend && npx vitest run src/components/auditease/requirements/ && npx tsc -b --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/auditease/requirements/
git commit -m "feat(auditease-web): requirements progress strip + priority chip"
```

---

### Task 6: Create modal (advanced options) + bulk import modal

**Files:**
- Create: `frontend/src/components/auditease/requirements/NewRequirementModal.tsx`
- Create: `frontend/src/components/auditease/requirements/NewRequirementModal.test.tsx`
- Create: `frontend/src/components/auditease/requirements/BulkImportModal.tsx`

**Interfaces (produces):**
- `validateRequirementForm(f): string | null` and `buildRequirementPayload(f): Record<string, unknown>` (pure, exported, tested)
- `NewRequirementModal({ engagementId, nextReqId, companyUsers, onClose })` — `companyUsers: { id: string; name: string }[]`
- `BulkImportModal({ engagementId, onClose })`

**Responsible-person source:** search for an existing company-users listing hook (`rg "company_users|listUsers|useCompany" frontend/src/api/endpoints frontend/src/api/hooks`). If one exists exposing `{id, name}`, pass it via `companyUsers`. If none exists, the auditor cannot resolve user IDs client-side: render the select only when `companyUsers.length > 0`, otherwise hide the field and show muted copy "Assign responsible person after import or edit — needs company user directory". Record the outcome in the PR description; the Excel path still supports it server-side by email.

- [ ] **Step 1: Write the failing validation test**

`frontend/src/components/auditease/requirements/NewRequirementModal.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { buildRequirementPayload, validateRequirementForm } from './NewRequirementModal'

describe('validateRequirementForm', () => {
  const base = { description: '', priority: 1 } as Parameters<typeof validateRequirementForm>[0]

  it('rejects empty requirement text', () => {
    expect(validateRequirementForm({ ...base, description: '   ' }))
      .toBe('Requirement text is required')
  })

  it('rejects period_to before period_from', () => {
    expect(validateRequirementForm({
      ...base, description: 'X',
      period_from: '2026-01-01', period_to: '2025-01-01',
    })).toBe('"Period to" must be on or after "Period from"')
  })

  it('rejects past due dates', () => {
    expect(validateRequirementForm({ ...base, description: 'X', due_date: '2000-01-01' }))
      .toBe('Due date cannot be in the past')
  })

  it('accepts a minimal valid form', () => {
    expect(validateRequirementForm({ ...base, description: 'Bank stmts' })).toBeNull()
  })
})

describe('buildRequirementPayload', () => {
  it('trims, drops empties, keeps defaults', () => {
    expect(buildRequirementPayload({ description: '  Bank stmts ', priority: 1, entity: '  ' }))
      .toEqual({ description: 'Bank stmts', priority: 1 })
  })

  it('keeps explicit non-defaults', () => {
    expect(buildRequirementPayload({
      description: 'X', priority: 4, due_date: '2030-01-01', expected_format: 'file',
    })).toEqual({ description: 'X', priority: 4, due_date: '2030-01-01', expected_format: 'file' })
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/components/auditease/requirements/NewRequirementModal.test.tsx`
Expected: FAIL — exports missing

- [ ] **Step 3: Implement the create modal**

`frontend/src/components/auditease/requirements/NewRequirementModal.tsx`:

```tsx
import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Button, Field, Input, Modal, Select, Textarea, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useAuditorCreateRequirement } from '@/api/hooks/auditorEngagements'

type FormState = {
  description: string
  title: string
  priority: number
  due_date: string
  additional_details: string
  period_from: string
  period_to: string
  entity: string
  responsible_person_id: string
  expected_format: 'text' | 'file' | 'any'
  auditor_notes: string
  parent_requirement_id: string
}

const EMPTY: FormState = {
  description: '', title: '', priority: 1, due_date: '', additional_details: '',
  period_from: '', period_to: '', entity: '', responsible_person_id: '',
  expected_format: 'any', auditor_notes: '', parent_requirement_id: '',
}

export function validateRequirementForm(
  f: Pick<FormState, 'description' | 'period_from' | 'period_to' | 'due_date'>,
): string | null {
  if (!f.description.trim()) return 'Requirement text is required'
  if (f.period_from && f.period_to && f.period_to < f.period_from)
    return '"Period to" must be on or after "Period from"'
  if (f.due_date) {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    if (new Date(`${f.due_date}T00:00:00`) < today) return 'Due date cannot be in the past'
  }
  return null
}

function clean(v: string | undefined): string | undefined {
  const t = (v ?? '').trim()
  return t ? t : undefined
}

export function buildRequirementPayload(f: Partial<FormState>): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    description: (f.description ?? '').trim(),
    priority: f.priority ?? 1,
  }
  const optional = [
    ['title', clean(f.title)],
    ['due_date', clean(f.due_date)],
    ['additional_details', clean(f.additional_details)],
    ['period_from', clean(f.period_from)],
    ['period_to', clean(f.period_to)],
    ['entity', clean(f.entity)],
    ['responsible_person_id', clean(f.responsible_person_id)],
    ['auditor_notes', clean(f.auditor_notes)],
    ['parent_requirement_id', clean(f.parent_requirement_id)],
  ] as const
  for (const [key, value] of optional) if (value !== undefined) payload[key] = value
  if (f.expected_format && f.expected_format !== 'any') payload.expected_format = f.expected_format
  return payload
}

export function NewRequirementModal({
  engagementId, nextReqId, companyUsers, onClose,
}: {
  engagementId: string
  nextReqId: string
  companyUsers: { id: string; name: string }[]
  onClose: () => void
}) {
  const toast = useToast()
  const createReq = useAuditorCreateRequirement()
  const [form, setForm] = useState<FormState>(EMPTY)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const handleSubmit = async () => {
    const problem = validateRequirementForm(form)
    if (problem) { setError(problem); return }
    try {
      await createReq.mutateAsync({ engagementId, body: buildRequirementPayload(form) })
      toast.success(`Requirement ${nextReqId} requested`)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    }
  }

  return (
    <Modal open onClose={onClose} title="New requirement" description={`Will be filed as ${nextReqId}`}>
      <div className="flex flex-col gap-4">
        <Field label="Requirement *" hint="What you are asking the company to provide.">
          <Textarea
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="e.g. FY24 bank statements for all current accounts"
            rows={3}
            autoFocus
          />
        </Field>

        {/* Visible by default per spec: priority preset to 1, due date optional & unset */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Priority" hint="1 = routine · 5 = critical">
            <Select value={String(form.priority)} onChange={(e) => set('priority', Number(e.target.value))}>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>P{n}</option>)}
            </Select>
          </Field>
          <Field label="Due date" hint="Optional">
            <Input type="date" value={form.due_date} onChange={(e) => set('due_date', e.target.value)} />
          </Field>
        </div>

        {error && <p className="text-sm font-medium text-status-action">{error}</p>}

        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setAdvancedOpen((o) => !o)}
            aria-expanded={advancedOpen}
            className="flex items-center gap-2 rounded-btn px-1 py-1 text-sm font-medium text-text-secondary transition-colors hover:text-text-primary"
          >
            <ChevronDown
              className={`h-4 w-4 transition-transform duration-200 ease-spring ${advancedOpen ? 'rotate-180' : ''}`}
            />
            Advanced options
          </button>
          <Button onClick={handleSubmit} disabled={createReq.isPending || !form.description.trim()}>
            {createReq.isPending ? 'Requesting…' : 'Request'}
          </Button>
        </div>

        {/* Progressive disclosure: grid-rows trick animates open without measuring height */}
        <div
          className="grid transition-[grid-template-rows] duration-300 ease-nav"
          style={{ gridTemplateRows: advancedOpen ? '1fr' : '0fr' }}
        >
          <div className="overflow-hidden">
            <div className="flex flex-col gap-4 border-t border-border pt-4">
              <Field label="Title" hint="Short label — defaults to the first line of the requirement.">
                <Input value={form.title} onChange={(e) => set('title', e.target.value)} />
              </Field>
              <Field label="Additional details">
                <Textarea rows={2} value={form.additional_details}
                          onChange={(e) => set('additional_details', e.target.value)} />
              </Field>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Period from">
                  <Input type="date" value={form.period_from} onChange={(e) => set('period_from', e.target.value)} />
                </Field>
                <Field label="Period to">
                  <Input type="date" value={form.period_to} onChange={(e) => set('period_to', e.target.value)} />
                </Field>
              </div>
              <Field label="Entity" hint="Group company / branch this applies to.">
                <Input value={form.entity} onChange={(e) => set('entity', e.target.value)}
                       placeholder="e.g. ETHDC Main" />
              </Field>
              {companyUsers.length > 0 && (
                <Field label="Responsible person (company)">
                  <Select value={form.responsible_person_id}
                          onChange={(e) => set('responsible_person_id', e.target.value)}>
                    <option value="">Unassigned</option>
                    {companyUsers.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                  </Select>
                </Field>
              )}
              <Field label="Expected format" hint="A hint for the company — they can always answer either way.">
                <Select value={form.expected_format}
                        onChange={(e) => set('expected_format', e.target.value as FormState['expected_format'])}>
                  <option value="any">Any</option>
                  <option value="text">Typed answer</option>
                  <option value="file">Document</option>
                </Select>
              </Field>
              <Field label="Parent requirement" hint="Files this as a child request under an existing REQ.">
                <Input value={form.parent_requirement_id} onChange={(e) => set('parent_requirement_id', e.target.value)}
                       placeholder="Paste a requirement id…" />
              </Field>
              <Field label="Auditor notes" hint="Visible to auditors only.">
                <Textarea rows={2} value={form.auditor_notes} onChange={(e) => set('auditor_notes', e.target.value)} />
              </Field>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}
```

Check the actual `Modal` props in `frontend/src/components/ui/Modal.tsx` first (`open/onClose/title/description` vs children-only) and adapt the header usage accordingly. Same for `Textarea` existence in `components/ui/index.ts`; fall back to `<textarea>` styled like `Field` inputs if absent.

- [ ] **Step 4: Implement the bulk import modal**

`frontend/src/components/auditease/requirements/BulkImportModal.tsx`:

```tsx
import { useState } from 'react'
import { Button, Modal, Spinner, useToast } from '@/components/ui'
import { FileUploadDropzone } from '@/components/ui'
import { saveBlob } from '@/lib/download'
import { ApiError } from '@/api/http'
import {
  useAuditorBulkImportRequirements,
  useAuditorDownloadImportTemplate,
} from '@/api/hooks/auditorEngagements'

type RowError = { row: number; message: string }

function extractErrors(err: unknown): RowError[] {
  if (!(err instanceof ApiError)) return [{ row: 0, message: String(err) }]
  const detail = err.payload?.detail ?? err.message
  if (Array.isArray(detail)) return detail as RowError[]
  return [{ row: 0, message: String(detail) }]
}

export function BulkImportModal({ engagementId, onClose }: { engagementId: string; onClose: () => void }) {
  const toast = useToast()
  const downloadTemplate = useAuditorDownloadImportTemplate()
  const importReqs = useAuditorBulkImportRequirements()
  const [errors, setErrors] = useState<RowError[] | null>(null)

  const handleTemplate = async () => {
    try {
      const blob = await downloadTemplate.mutateAsync(engagementId)
      saveBlob(blob, 'requirements_import_template.xlsx')
    } catch {
      toast.error('Could not download template')
    }
  }

  const handleFile = async (file: File) => {
    setErrors(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await importReqs.mutateAsync({ engagementId, formData: fd })
      toast.success(`Imported ${res.created_count} requirement${res.created_count === 1 ? '' : 's'}`)
      onClose()
    } catch (err) {
      setErrors(extractErrors(err))
    }
  }

  return (
    <Modal open onClose={onClose} title="Bulk import requirements"
           description="Upload a filled template. All rows are validated first — one bad row aborts the file.">
      <div className="flex flex-col gap-4">
        <Button variant="secondary" onClick={handleTemplate} disabled={downloadTemplate.isPending}>
          {downloadTemplate.isPending ? 'Preparing…' : 'Download template (.xlsx)'}
        </Button>

        {importReqs.isPending ? (
          <Spinner className="mx-auto h-6 w-6" />
        ) : (
          <FileUploadDropzone
            accept=".xlsx,.xls,.csv"
            onFile={(f) => void handleFile(f)}
            label="Drop the filled sheet here"
          />
        )}

        {errors && errors.length > 0 && (
          <div className="animate-fade-in rounded-card border border-status-warning/40 bg-status-warning/10 p-3">
            <p className="mb-2 text-sm font-semibold text-text-primary">
              Nothing was imported — fix these rows and re-upload:
            </p>
            <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto text-sm text-text-secondary">
              {errors.map((e, i) => (
                <li key={i}>
                  <span className="font-semibold">Row {e.row}:</span> {e.message}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>
  )
}
```

Verify `FileUploadDropzone`'s real prop names in `frontend/src/components/ui/FileUploadDropzone.tsx` and adapt (`label`/`accept`/`onFile` may differ). Verify how `ApiError` exposes response payloads (`err.payload` vs `err.body`) in `frontend/src/api/http.ts` and adjust `extractErrors`.

- [ ] **Step 5: Run tests + lint**

Run: `cd frontend && npx vitest run src/components/auditease/requirements/ && npx tsc -b --noEmit && npm run lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/auditease/requirements/
git commit -m "feat(auditease-web): new-requirement modal with advanced options + bulk import modal"
```

---

### Task 7: Auditor Requirements tab rebuild

**Files:**
- Rewrite: `frontend/src/pages/auditor/RequirementsTab.tsx`
- Modify: `frontend/src/pages/auditor/AuditorEngagementWorkspace.tsx`

**Interfaces (consumes):** `RequirementsProgress`, `PriorityChip`, `NewRequirementModal`, `BulkImportModal` from Tasks 5–6; hooks `useAuditorReviewRequirement`, `useAuditorDeleteRequirement` from Task 4.

New prop from workspace: `canQuery: boolean` (auditor needs `queries` area to initiate a query).

- [ ] **Step 1: Rebuild the tab**

Full replacement of `frontend/src/pages/auditor/RequirementsTab.tsx`:

```tsx
import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ChevronRight, Download, History, MessageSquarePlus, Plus, Trash2, Upload,
} from 'lucide-react'
import {
  Button, Card, ConfirmDialog, EmptyState, Input, Spinner, StatusBadge, useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import {
  useAuditorListRequirements, useAuditorCreateQuery,
  useAuditorReviewRequirement, useAuditorDeleteRequirement,
} from '@/api/hooks/auditorEngagements'
import { auditorEngagementsApi } from '@/api/endpoints/auditorEngagements'
import { saveBlob } from '@/lib/download'
import { RequirementsProgress, type RequestStatusFilter } from '@/components/auditease/requirements/RequirementsProgress'
import { PriorityChip } from '@/components/auditease/requirements/PriorityChip'
import { NewRequirementModal } from '@/components/auditease/requirements/NewRequirementModal'
import { BulkImportModal } from '@/components/auditease/requirements/BulkImportModal'

type Req = Awaited<ReturnType<typeof auditorEngagementsApi.listRequirements>>[number]

function isOverdue(iso: string | null | undefined): boolean {
  if (!iso) return false
  const today = new Date(); today.setHours(0, 0, 0, 0)
  return new Date(`${iso.slice(0, 10)}T00:00:00`) < today
}

function fmtDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined,
    { day: 'numeric', month: 'short', year: 'numeric' })
}

export function RequirementsTab({ engagementId, canQuery }: { engagementId: string; canQuery: boolean }) {
  const toast = useToast()
  const { data: reqs = [], isLoading } = useAuditorListRequirements(engagementId)
  const review = useAuditorReviewRequirement()
  const del = useAuditorDeleteRequirement()
  const createQuery = useAuditorCreateQuery()

  const [filter, setFilter] = useState<RequestStatusFilter | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [expandedChildren, setExpandedChildren] = useState<Record<string, boolean>>({})
  const [historyFor, setHistoryFor] = useState<string | null>(null)
  const [clarifyFor, setClarifyFor] = useState<string | null>(null)
  const [clarifyNote, setClarifyNote] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Req | null>(null)

  const roots = useMemo(() => reqs.filter((r) => !r.parent_requirement_id), [reqs])
  const childrenOf = (id: string) =>
    reqs.filter((r) => r.parent_requirement_id === id).sort((a, b) => a.seq_number - b.seq_number)

  const visible = filter ? reqs.filter((r) => r.status === filter) : reqs
  const visibleRoots = visible.filter((r) => !r.parent_requirement_id)
  const visibleChildrenOf = (id: string) =>
    visible.filter((r) => r.parent_requirement_id === id).sort((a, b) => a.seq_number - b.seq_number)

  const nextReqId = `REQ-${String(
    Math.max(0, ...reqs.map((r) => r.seq_number ?? 0)) + 1).padStart(3, '0')}`

  const handleDownload = async (docId: string) => {
    try {
      const doc = await auditorEngagementsApi.getDocument(docId)
      const blob = await auditorEngagementsApi.downloadDocument(docId)
      const version = doc.versions.find((v) => v.id === doc.current_version_id)
      saveBlob(blob, version?.original_filename || 'document')
    } catch {
      toast.error('Failed to download document')
    }
  }

  const handleReview = async (req: Req, action: 'accept' | 'clarify', note?: string) => {
    try {
      await review.mutateAsync({ engagementId, reqId: req.id, body: { action, note } })
      toast.success(action === 'accept'
        ? `${req.requirement_id_str} accepted`
        : `${req.requirement_id_str} marked for clarification`)
      setClarifyFor(null); setClarifyNote('')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Error')
    }
  }

  const handleInitiateQuery = async (req: Req) => {
    try {
      const fd = new FormData()
      fd.append('initial_message',
        `Clarification on ${req.requirement_id_str}: ${req.description}\n\n`)
      fd.append('requirement_id', req.id)
      await createQuery.mutateAsync({ engagementId, formData: fd })
      toast.success(`Query opened for ${req.requirement_id_str}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not open query')
    }
  }

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  return (
    <div className="flex flex-col gap-6">
      <RequirementsProgress requirements={reqs} activeFilter={filter} onFilterChange={setFilter} />

      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-medium text-text-primary">Requested documents</h3>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => setShowImport(true)}>
            <Upload className="h-4 w-4" /> Bulk import
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" /> New requirement
          </Button>
        </div>
      </div>

      {visibleRoots.length === 0 && roots.length === 0 ? (
        <EmptyState title="No requirements"
                    description="Request documents or import your requirement list." />
      ) : visibleRoots.length === 0 ? (
        <EmptyState title={`No ${filter?.replace('_', ' ')} requirements`}
                    description="Try another status filter." />
      ) : (
        <AnimatePresence initial={false}>
          {visibleRoots.map((req) => {
            const kids = visibleChildrenOf(req.id)
            const allKids = childrenOf(req.id)
            const open = expandedChildren[req.id] ?? false
            return (
              <motion.div key={req.id} layout
                          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0 }} transition={{ duration: 0.18 }}
                          className="flex flex-col gap-2">
                <Card className="flex flex-col gap-3 p-4">
                  {/* row 1: id · badges · meta pills · actions */}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-bg-raised px-1.5 py-0.5 font-mono text-xs text-text-secondary">
                      {req.requirement_id_str}
                    </span>
                    <StatusBadge status={req.status} />
                    {req.priority > 1 && <PriorityChip priority={req.priority} />}
                    {req.due_date && (
                      <span className={`inline-flex items-center rounded-pill border px-2 py-0.5 text-xs ${
                        isOverdue(req.due_date)
                          ? 'border-red-300/60 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-300'
                          : 'border-border text-text-secondary'}`}>
                        Due {fmtDate(req.due_date)}
                      </span>
                    )}
                    {req.company_eta && (
                      <span className="rounded-pill border border-border px-2 py-0.5 text-xs text-text-muted">
                        ETA {fmtDate(req.company_eta)}
                      </span>
                    )}
                    {(req.entity || req.period_from || req.period_to) && (
                      <span className="text-xs text-text-muted">
                        {[req.entity,
                          req.period_from && req.period_to
                            ? `${fmtDate(req.period_from)} – ${fmtDate(req.period_to)}`
                            : null].filter(Boolean).join(' · ')}
                      </span>
                    )}
                    {req.responsible_person_name && (
                      <span className="rounded-pill border border-border px-2 py-0.5 text-xs text-text-secondary">
                        {req.responsible_person_name}
                      </span>
                    )}

                    <div className="ml-auto flex items-center gap-1.5">
                      {allKids.length > 0 && (
                        <button
                          onClick={() => setExpandedChildren((m) => ({ ...m, [req.id]: !open }))}
                          className="flex items-center gap-1 rounded-btn px-2 py-1 text-xs text-text-secondary transition-colors hover:bg-bg-raised hover:text-text-primary"
                        >
                          <ChevronRight className={`h-3.5 w-3.5 transition-transform duration-200 ease-spring ${open ? 'rotate-90' : ''}`} />
                          {allKids.length} child{allKids.length === 1 ? '' : 'ren'}
                        </button>
                      )}
                      {req.latest_response?.document_id && (
                        <Button variant="ghost" size="sm"
                                onClick={() => handleDownload(req.latest_response!.document_id!)}>
                          <Download className="h-4 w-4" />
                        </Button>
                      )}
                      {req.responses.length > 0 && (
                        <Button variant="ghost" size="sm"
                                onClick={() => setHistoryFor(historyFor === req.id ? null : req.id)}>
                          <History className="h-4 w-4" /> {req.responses.length}
                        </Button>
                      )}
                      {canQuery && (
                        <button
                          title={req.linked_query_count
                            ? `View ${req.linked_query_count} linked quer${req.linked_query_count === 1 ? 'y' : 'ies'} in the Queries tab`
                            : 'Initiate query'}
                          onClick={() => void handleInitiateQuery(req)}
                          disabled={createQuery.isPending}
                          className="group flex h-7 w-7 items-center justify-center rounded-full border border-border text-text-muted
                                     transition-transform duration-150 ease-spring hover:scale-[1.15] hover:border-accent hover:text-accent
                                     active:scale-95 disabled:opacity-40"
                        >
                          <MessageSquarePlus className="h-3.5 w-3.5" />
                          {req.linked_query_count > 0 && (
                            <span className="absolute -mt-5 ml-5 rounded-full bg-accent px-1.5 text-[10px] font-semibold text-white">
                              {req.linked_query_count}
                            </span>
                          )}
                        </button>
                      )}
                      {req.status === 'submitted' && (
                        <>
                          <Button size="sm" onClick={() => void handleReview(req, 'accept')}>
                            Accept
                          </Button>
                          <Button size="sm" variant="secondary"
                                  onClick={() => setClarifyFor(clarifyFor === req.id ? null : req.id)}>
                            Need clarification
                          </Button>
                        </>
                      )}
                      {req.status === 'pending' && (
                        <Button variant="ghost" size="sm" onClick={() => setDeleteTarget(req)}>
                          <Trash2 className="h-4 w-4 text-status-action" />
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* row 2: the ask */}
                  <p className="font-medium text-text-primary">{req.description}</p>

                  {/* clarification banner (auditor sees what they asked) */}
                  {req.status === 'clarification_needed' && req.clarification_note && (
                    <p className="animate-fade-in rounded-card border border-status-warning/40 bg-status-warning/10 px-3 py-2 text-sm">
                      Clarification requested: {req.clarification_note}
                    </p>
                  )}

                  {/* inline clarify note field */}
                  <AnimatePresence>
                    {clarifyFor === req.id && (
                      <motion.div initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: 'auto', opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  className="overflow-hidden">
                        <div className="flex items-end gap-2 pt-1">
                          <Input value={clarifyNote} onChange={(e) => setClarifyNote(e.target.value)}
                                 placeholder="What needs clarifying? (optional)" />
                          <Button size="sm"
                                  disabled={review.isPending}
                                  onClick={() => void handleReview(req, 'clarify', clarifyNote.trim() || undefined)}>
                            Send
                          </Button>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {/* response history */}
                  <AnimatePresence>
                    {historyFor === req.id && req.responses.length > 0 && (
                      <motion.ul initial={{ height: 0, opacity: 0 }}
                                 animate={{ height: 'auto', opacity: 1 }}
                                 exit={{ height: 0, opacity: 0 }}
                                 className="overflow-hidden rounded-card border border-border bg-bg-raised/50 p-3 text-sm">
                        {req.responses.map((resp) => (
                          <li key={resp.id} className="flex items-start justify-between gap-3 py-1">
                            <div>
                              <p className="text-text-primary">{resp.text_answer}</p>
                              <p className="text-xs text-text-muted">
                                {new Date(resp.created_at).toLocaleString()}
                                {resp.responded_by_name ? ` · ${resp.responded_by_name}` : ''}
                              </p>
                            </div>
                            {resp.document_id && (
                              <Button variant="ghost" size="sm"
                                      onClick={() => handleDownload(resp.document_id!)}>
                                <Download className="h-4 w-4" />
                              </Button>
                            )}
                          </li>
                        ))}
                      </motion.ul>
                    )}
                  </AnimatePresence>
                </Card>

                {/* indented children */}
                <AnimatePresence initial={false}>
                  {open && kids.map((kid) => (
                    <motion.div key={kid.id} layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0 }} className="ml-8">
                      <ChildRow req={kid} onDownload={handleDownload} />
                    </motion.div>
                  ))}
                </AnimatePresence>
              </motion.div>
            )
          })}
        </AnimatePresence>
      )}

      {showCreate && (
        <NewRequirementModal engagementId={engagementId} nextReqId={nextReqId} companyUsers={[]}
                             onClose={() => setShowCreate(false)} />
      )}
      {showImport && <BulkImportModal engagementId={engagementId} onClose={() => setShowImport(false)} />}
      {deleteTarget && (
        <ConfirmDialog
          open
          title={`Delete ${deleteTarget.requirement_id_str}?`}
          description="Only pending requirements without children can be deleted."
          confirmLabel="Delete"
          onConfirm={async () => {
            try {
              await del.mutateAsync({ engagementId, reqId: deleteTarget.id })
              toast.success('Requirement deleted')
            } catch (err) {
              toast.error(err instanceof ApiError ? err.message : 'Error deleting')
            } finally {
              setDeleteTarget(null)
            }
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}

function ChildRow({ req, onDownload }: { req: Req; onDownload: (docId: string) => Promise<void> }) {
  return (
    <Card className="flex items-center justify-between gap-3 p-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="rounded-md bg-bg-raised px-1.5 py-0.5 font-mono text-xs text-text-muted">
          {req.requirement_id_str}
        </span>
        <StatusBadge status={req.status} />
        {req.priority > 1 && <PriorityChip priority={req.priority} />}
        <span className="truncate text-sm font-medium text-text-primary">{req.description}</span>
      </div>
      {req.latest_response?.document_id && (
        <Button variant="ghost" size="sm" onClick={() => void onDownload(req.latest_response!.document_id!)}>
          <Download className="h-4 w-4" />
        </Button>
      )}
    </Card>
  )
}
```

Adapt prop names to actual UI kit (`ConfirmDialog`, `Input`, `Button` variants/sizes — read each component's props first; adjust `variant="secondary"/"ghost"` and `size="sm"` to whatever exists).

Note on the child picker in `NewRequirementModal`: this task passes `companyUsers={[]}` — wiring the real directory is part of Task 6 Step 1's resolution; parent linking via paste-id input works regardless (server validates).

- [ ] **Step 2: Wire the workspace**

In `frontend/src/pages/auditor/AuditorEngagementWorkspace.tsx`:

1. Line 57 — change the requirements tab count from open to not-yet-accepted:
   ```ts
   count: reqs.filter((r) => r.status !== 'accepted').length,
   ```
2. Line ~117 — overview StatCard "Open requirements": same predicate (`r.status !== 'accepted'`).
3. Line 137 — pass the new prop:
   ```tsx
   {tab === 'requirements' && <RequirementsTab engagementId={eng.id} canQuery={perms.queries !== false} />}
   ```

- [ ] **Step 3: Typecheck, lint, tests**

Run: `cd frontend && npx tsc -b --noEmit && npm run lint && npx vitest run`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "feat(auditease-web): auditor requirements lifecycle UI (progress, review, queries, grouping)"
```

---

### Task 8: Company Requirements tab rebuild + legacy cleanup

**Files:**
- Rewrite: `frontend/src/pages/company/auditease/RequirementsTab.tsx`
- Modify: `frontend/src/api/hooks/auditease.ts` (delete `useFulfillRequirement`)
- Modify: `frontend/src/api/endpoints/auditease.ts` (delete `fulfillRequirement` + its type import if unused)

- [ ] **Step 1: Rebuild the tab**

Full replacement of `frontend/src/pages/company/auditease/RequirementsTab.tsx`:

```tsx
import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CalendarClock, ChevronDown, Download, Paperclip } from 'lucide-react'
import {
  Button, Card, EmptyState, Input, Select, Spinner, StatusBadge, Textarea, useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import { useListRequirements, useRespondToRequirement, useSetRequirementEta } from '@/api/hooks/auditease'
import { useDocuments, useDownloadDocument } from '@/api/hooks/docvault'
import { RequirementsProgress, type RequestStatusFilter } from '@/components/auditease/requirements/RequirementsProgress'
import { PriorityChip } from '@/components/auditease/requirements/PriorityChip'

type Req = { id: string; description: string; status: string; requirement_id_str: string | null;
             priority: number; due_date: string | null; company_eta: string | null;
             entity: string | null; period_from: string | null; period_to: string | null;
             responsible_person_name: string | null; responsible_person_id: string | null;
             expected_format: string; clarification_note: string | null;
             latest_response: { document_id: string | null; text_answer: string | null } | null }
// Prefer importing the generated type instead of redeclaring it:
// type Req = RequirementRequestResponse  (from '@/api/types')

function fmtDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined,
    { day: 'numeric', month: 'short', year: 'numeric' })
}

export function RequirementsTab({
  engagementId, currentUserId,
}: { engagementId: string; currentUserId?: string }) {
  const toast = useToast()
  const { data: reqs = [], isLoading } = useListRequirements(engagementId)
  const { data: docs = [] } = useDocuments()
  const downloadDoc = useDownloadDocument()
  const respond = useRespondToRequirement()
  const setEta = useSetRequirementEta()

  const [filter, setFilter] = useState<RequestStatusFilter | null>(null)
  const [respondFor, setRespondFor] = useState<string | null>(null)
  const [textAnswer, setTextAnswer] = useState('')
  const [selectedDoc, setSelectedDoc] = useState('')

  const visible = filter ? reqs.filter((r) => r.status === filter) : reqs

  const handleRespond = async (req: Req) => {
    if (!textAnswer.trim() && !selectedDoc) {
      toast.error('Type an answer or attach a document')
      return
    }
    try {
      await respond.mutateAsync({
        engagementId, reqId: req.id,
        body: {
          text_answer: textAnswer.trim() || undefined,
          document_id: selectedDoc || undefined,
        },
      })
      toast.success(`Response submitted for ${req.requirement_id_str}`)
      setRespondFor(null); setTextAnswer(''); setSelectedDoc('')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Error submitting response')
    }
  }

  const handleEta = async (req: Req, value: string) => {
    try {
      await setEta.mutateAsync({ engagementId, reqId: req.id, body: { company_eta: value || null } })
      toast.success(value ? `ETA set for ${req.requirement_id_str}` : 'ETA cleared')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not set ETA')
    }
  }

  const handleDownload = async (docId: string) => {
    const doc = docs.find((d) => d.id === docId)
    const version = doc?.versions.find((v) => v.id === doc.current_version_id)
    if (!doc || !version) { toast.error('Document not found'); return }
    try {
      await downloadDoc.mutateAsync({ id: doc.id, versionId: version.id, filename: version.original_filename })
    } catch {
      toast.error('Failed to download document')
    }
  }

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  const canRespondTo = (r: Req) => r.status === 'pending' || r.status === 'clarification_needed'

  return (
    <div className="flex flex-col gap-4">
      <RequirementsProgress requirements={reqs} activeFilter={filter} onFilterChange={setFilter} />

      {visible.length === 0 ? (
        <EmptyState title="No requirements here"
                   description={filter ? 'Try another status.' : "The auditor hasn't requested anything yet."} />
      ) : (
        visible.map((req) => {
          const open = respondFor === req.id
          const mine = currentUserId && req.responsible_person_id === currentUserId
          return (
            <Card key={req.id} className="flex animate-fade-in-up flex-col gap-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-bg-raised px-1.5 py-0.5 font-mono text-xs text-text-secondary">
                  {req.requirement_id_str}
                </span>
                <StatusBadge status={req.status} />
                {req.priority > 1 && <PriorityChip priority={req.priority} />}
                {mine && (
                  <span className="rounded-pill border border-accent/50 bg-accent-subtle px-2 py-0.5 text-xs font-medium text-accent">
                    You're responsible
                  </span>
                )}
                {req.due_date && (
                  <span className="text-xs font-medium text-text-secondary">Due {fmtDate(req.due_date)}</span>
                )}
                {(req.entity || (req.period_from && req.period_to)) && (
                  <span className="text-xs text-text-muted">
                    {[req.entity,
                      req.period_from && req.period_to
                        ? `${fmtDate(req.period_from)} – ${fmtDate(req.period_to)}`
                        : null].filter(Boolean).join(' · ')}
                  </span>
                )}
              </div>

              <p className="font-medium text-text-primary">{req.description}</p>

              {req.expected_format !== 'any' && (
                <p className="text-xs text-text-muted">
                  Auditor expects: {req.expected_format === 'text' ? 'a typed answer' : 'a document'}
                  {' '}— you can always provide either or both.
                </p>
              )}

              {req.status === 'clarification_needed' && req.clarification_note && (
                <p className="animate-fade-in rounded-card border border-status-warning/40 bg-status-warning/10 px-3 py-2 text-sm">
                  <strong>Clarification needed:</strong> {req.clarification_note}
                </p>
              )}

              <div className="flex flex-wrap items-center gap-2">
                {req.company_eta ? (
                  <span className="inline-flex items-center gap-1 rounded-pill border border-border px-2 py-0.5 text-xs text-text-secondary">
                    <CalendarClock className="h-3.5 w-3.5" /> ETA {fmtDate(req.company_eta)}
                  </span>
                ) : canRespondTo(req) ? (
                  <label className="inline-flex cursor-pointer items-center gap-1 rounded-pill border border-dashed border-border-strong px-2 py-0.5 text-xs text-text-muted transition-colors hover:border-accent hover:text-accent">
                    <CalendarClock className="h-3.5 w-3.5" /> Set expected by
                    <input type="date" className="sr-only"
                           onChange={(e) => void handleEta(req, e.target.value)} />
                  </label>
                ) : null}

                {req.latest_response?.document_id && (
                  <Button variant="ghost" size="sm"
                          onClick={() => void handleDownload(req.latest_response!.document_id!)}>
                    <Download className="h-4 w-4" /> Document
                  </Button>
                )}

                {canRespondTo(req) && !open && (
                  <Button size="sm" className="ml-auto"
                          onClick={() => { setRespondFor(req.id); setTextAnswer(''); setSelectedDoc('') }}>
                    Respond
                  </Button>
                )}
              </div>

              <AnimatePresence>
                {open && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                    <div className="animate-scale-in flex flex-col gap-3 rounded-card border border-border bg-bg-raised/40 p-3">
                      <Textarea rows={3} autoFocus value={textAnswer}
                                onChange={(e) => setTextAnswer(e.target.value)}
                                placeholder="Type your answer…" />
                      <div className="flex items-end gap-2">
                        <Select value={selectedDoc} onChange={(e) => setSelectedDoc(e.target.value)}
                                className="flex-1">
                          <option value="">Attach from docVault…</option>
                          {docs.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
                        </Select>
                        <Paperclip className="mb-2.5 h-4 w-4 shrink-0 text-text-muted" />
                      </div>
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="secondary" size="sm" onClick={() => setRespondFor(null)}>Cancel</Button>
                        <Button size="sm" disabled={respond.isPending} onClick={() => void handleRespond(req)}>
                          {respond.isPending ? 'Submitting…' : 'Submit'}
                        </Button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </Card>
          )
        })
      )}
    </div>
  )
}
```

Check whether `EngagementWorkspace` (company side, line ~245) passes any user identity already; if `currentUserId` is unavailable without new plumbing, drop the "You're responsible" chip by omitting the prop — do NOT add new auth plumbing in this task. Adapt `Textarea`/`Select`/`FileUploadDropzone` usage to the real kit exports as in Task 7.

- [ ] **Step 2: Remove legacy fulfill plumbing**

In `frontend/src/api/hooks/auditease.ts`: delete `useFulfillRequirement` (lines ~297–305).
In `frontend/src/api/endpoints/auditease.ts`: delete `fulfillRequirement` and remove now-unused imports/types.
Run `rg -n "fulfill|fulfilled|status === 'open'" frontend/src` and fix every remaining reference in auditease/requirement contexts (e.g. company EngagementWorkspace stat cards using `'open'` → switch to `!== 'accepted'`; `schema.d.ts` regenerates only from backend so stale union members there are fine to leave if types still compile).

- [ ] **Step 3: Full frontend verification**

Run: `cd frontend && npx tsc -b --noEmit && npm run lint --max-warnings 0 && npx vitest run`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "feat(auditease-web): company respond flow with ETA + progress strip; drop fulfill"
```

---

### Task 9: End-to-end verification

- [ ] **Step 1: Backend suite**

Run: `uv run pytest tests/ unit_tests/ -q`
Expected: PASS

- [ ] **Step 2: Frontend build + tests**

Run: `cd frontend && npm run build && npx vitest run`
Expected: PASS

- [ ] **Step 3: Manual smoke checklist (dev servers up)**

As auditor: create requirement (verify REQ id preview, P1 default preset, due date empty, advanced options expand animation) → bulk-import template roundtrip → mark submitted item accepted / send clarification → initiate query from a card (spring-enlarging button) → verify progress strip segments animate and filters work.
As company: see same strip → set ETA on an open card → respond with typed answer only, then with DocVault doc → see amber clarification banner after auditor marks one → resubmit → watch badge crossfade to Accepted.
Both sides respect reduced-motion (system setting on).

- [ ] **Step 4: Final commit if smoke fixes were needed**

```bash
git add -A && git commit -m "fix(auditease): requirements lifecycle smoke fixes"
```

## Plan self-review notes

- Spec coverage: statuses/lifecycle (Task 3), REQ ids (Tasks 1–3), advanced fields + defaults (Task 6 modal), query-from-requirement (Task 3 backend + Task 7 button), bulk Excel incl. template/errors/all-or-nothing/parent refs/email matching (Tasks 2–3), company ETA (Tasks 3+8), progress strip both tabs (Tasks 5, 7, 8), activity events (Task 3 endpoints), migration remap incl. legacy responses (Task 3 migration).
- Type consistency checked: `enrich_requirements(db, engagement_id, req_list) -> list[dict]` used identically in both routers; `requirement_id_str` naming consistent across schemas/tests/frontend; hook names match endpoint names.

