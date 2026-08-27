# AuditEase Requirements — Open/Closed Redesign

**Spec + change sheet — single source of truth for this work**

| | |
|---|---|
| **Date** | 2026-08-27 |
| **Branch baseline** | `graph` (verified; `main` holds a much older version of this module — do not build there) |
| **Alembic head to build on** | `a4b5c6d7e8f9` (`a4b5c6d7e8f9_add_leads_table.py`) |
| **Status** | Approved — ready to build |

---

## 1. What we are doing

The Requirements module (Prepared-by-Client lists) carries more metadata and more
lifecycle states than the way it is actually used. This change:

1. **Collapses the lifecycle to Open / Closed.** A requirement is `open` from creation and
   becomes `closed` only when an auditor presses Close. Reopening is allowed.
2. **Reduces a requirement to four fields** — serial number, requirement text, due date,
   priority. The requirement text is one free-form field holding everything.
3. **Reduces the Excel import to four columns** — `S. No. | Requirement | Due Date | Priority`,
   with only `Requirement` mandatory.
4. **Makes submissions multi-document.** The company answers with optional text plus any
   number of documents, uploaded directly or picked from DocVault, and every batch is one
   numbered submission round ("edition") in an append-only history.
5. **Rebuilds both portals' UI** — a completion donut with metric tiles replacing the
   segmented bar, and compact requirement rows that expand in place into a submission
   timeline showing every document.

Raising a query from a requirement is kept exactly as-is, and becomes the sole channel for
"this submission isn't good enough" now that `clarification_needed` is gone.

## 2. Locked decisions

| Decision | Choice |
|---|---|
| Status model | Two stored states (`open`/`closed`). Awaiting / Responded / Closed derived **client-side** |
| Clarification loop | Removed. Raising a query replaces it |
| The nine extra requirement fields | **All dropped** |
| DocVault layout | **Keep the single shared `"Audit Attachments"` bucket.** No new buckets, no nesting. Grouping lives in the Requirements tab, driven by DB metadata; documents are titled and tagged by convention so they remain findable |
| Submission model | One `RequirementResponse` per round, holding N documents via a join table |
| Upload path | Direct multi-file upload **and** pick from DocVault |
| Auditor controls | Reopen allowed; edit while open by **any** auditor with the `requirements` area; delete only when zero submissions exist |
| Migration | **Hard drop — no data preserved** |
| Upload limits | **None added.** Deliberately deferred to a separate team decision |
| Bulk zip download | Out of scope |

## 3. Before → after

| Concern | Before (`graph` today) | After |
|---|---|---|
| `RequestStatus` | `pending`, `submitted`, `clarification_needed`, `accepted` | `open`, `closed` |
| `ExpectedFormat` | enum + column | **deleted** |
| `RequirementRequest` columns | 20 | 10 |
| Hierarchy | `parent_requirement_id` + cycle prevention | **deleted** |
| Documents per submission | exactly 0 or 1 | 0..N |
| Company upload | must pre-upload to DocVault, then attach one | upload N files inline and/or pick N existing |
| Auditor review | `POST /review` → accept / clarify | `POST /close`, `POST /reopen` |
| Company ETA | `PATCH /eta` | **deleted** |
| Import columns | 11 | 4 |
| Overview UI | segmented bar + pills | donut + 4 stat tiles + pills |
| List UI | flat cards with nested children | compact rows expanding into a submission timeline |
| `enrich_requirements` | in `app/routers/auditor_engagements.py:75`, imported by `auditease.py:40` | `app/services/requirements.py` |

## 4. Global conventions and constraints

- **Python/backend:** FastAPI + async SQLAlchemy 2.0 (`Mapped` / `mapped_column`),
  Pydantic v2 (`model_config = {"from_attributes": True}`). Postgres only.
- **Never lazy-load in async paths.** Follow the existing `lazy="raise"` +
  explicit `selectinload()` convention (see `AuditEntryLine.ledger`).
- **Tests:** `uv run pytest`. Integration tests hit a real `kubera_test` Postgres DB via
  `tests/conftest.py`; pure-logic tests live in `unit_tests/` (no DB).
- **Migrations:** hand-edited. `uv run alembic revision -m "..."`, then
  `uv run alembic upgrade head`. The `api` container runs `alembic upgrade head` on deploy.
- **Frontend:** React + TypeScript, TanStack Query, framer-motion, Tailwind with CSS-var
  tokens from `frontend/src/index.css`. Company accent is emerald (`--accent`), auditor
  accent is blue (`--auditor-accent`).
- **Frontend checks:** `npm test` (vitest), `npm run build` (`tsc -b && vite build`),
  `npm run lint` (eslint, `--max-warnings 0`).
- **Never hand-edit `frontend/src/api/schema.d.ts`.** Regenerate with `npm run gen:api`,
  which needs the backend running on `:8000`.
- **Display id format** stays `REQ-{seq:03d}`.
- **Priority** is an integer 1–5, default 1. 1 = routine, 5 = critical.

## 5. Behaviour specification

### 5.1 State model

```
                    auditor presses Close
   [ open ] ─────────────────────────────────▶ [ closed ]
      ▲                                             │
      └───────────────── auditor presses Reopen ────┘

  Company may submit only while `open`. Submitting never changes `status`.
```

`status` is the only stored state. The UI derives a third label from data:

| Derived display state | Condition | Colour token |
|---|---|---|
| **Awaiting** | `status == 'open'` and `submission_count == 0` | `--border-strong` / muted |
| **Responded** | `status == 'open'` and `submission_count > 0` | `--status-uploaded` (blue) |
| **Closed** | `status == 'closed'` | `--status-verified` (green) |

`is_overdue` is a separate axis, derived as `due_date < today && status == 'open'`, and
must be visually distinct from high priority — they are different things and must not both
read as plain red.

`percentComplete` = `closed / total`.

### 5.2 Permission matrix

| Action | Who | Gate |
|---|---|---|
| List requirements | Auditor with `requirements` area | `check_auditor_access(..., area="requirements")` |
| List requirements | Any company user of the owning tenant | `engagement.company_id == user.company_id` |
| Create / edit / delete | **Any** auditor with `requirements` area (no longer creator-only) | as above |
| Edit | — | 400 when `closed` |
| Delete | — | 400 when any submission exists |
| Close / Reopen | Any auditor with `requirements` area | 400 when already in that state |
| Import / template | Any auditor with `requirements` area | as above |
| Respond | Any company user of the owning tenant | 400 when `closed` |
| Raise query from requirement | Auditor with `queries` area | unchanged |
| Download a submitted document | Auditor | `DocumentAccessOverride` **and** live grant **and** `documents` area |

### 5.3 Validation rules

**Create / edit requirement**
- `description` required, non-blank after strip.
- `priority` integer 1–5; absent → 1.
- `due_date` optional. Client-side rejects a past date on create; the server does not
  enforce it (an imported historic list must still load).

**Respond**
- At least one of `text_answer`, `files`, `document_ids` must be present, else 422.
- Every `document_ids` entry must resolve to a `Document` whose `company_id` matches the
  caller's company. **One failure rejects the whole request** — no partial submissions.
- No size or count limit (§13).

**Import** — see §8.6.

### 5.4 Activity events

| Event | When | Actor |
|---|---|---|
| `requirement.raised` | create (unchanged) | auditor |
| `requirement.updated` | **new** — successful `PUT` | auditor |
| `requirement.deleted` | delete (unchanged) | auditor |
| `requirement.closed` | **new** | auditor |
| `requirement.reopened` | **new** | auditor |
| `requirement.bulk_imported` | import (unchanged) | auditor |
| `requirement.submitted` | respond (unchanged; metadata gains `round_number`, `file_count`) | company user |
| ~~`requirement.accepted`~~ | **removed** | |
| ~~`requirement.clarification`~~ | **removed** | |
| ~~`requirement.eta_set`~~ | **removed** | |

`tests/test_auditease_multi_auditor.py:259` asserts a set of logged actions and must be
updated for the renames.

---

## 6. Master change inventory

### Backend

| File | Action |
|---|---|
| `app/models/auditease.py` | Modify — enum, `RequirementRequest`, `RequirementResponse`; add `RequirementResponseDocument`; delete `ExpectedFormat` |
| `alembic/versions/<rev>_requirements_open_closed.py` | **Create** |
| `app/schemas/auditease.py` | Modify — rewrite the three requirement schemas |
| `app/services/requirements.py` | **Create** |
| `app/services/document_access.py` | Modify — receive `grant_document_access_to_auditors` |
| `app/services/requirement_import.py` | Rewrite |
| `app/routers/auditor_engagements.py` | Modify — heavy deletions, 2 new endpoints |
| `app/routers/auditease.py` | Modify — multipart respond, deletions |
| `app/services/account_admin.py` | Modify — docstring only |

### Backend tests

| File | Action |
|---|---|
| `unit_tests/test_requirement_models.py` | Rewrite |
| `unit_tests/test_requirement_import.py` | Rewrite |
| `tests/test_auditease.py` | Modify — `test_requirements_and_queries`, `test_requirement_parenting_guards` (**delete**), `test_requirement_bulk_import_roundtrip` |
| `tests/test_requirement_submissions.py` | **Create** |
| `tests/test_auditease_multi_auditor.py` | Modify |
| `tests/test_account_admin.py` | Modify — join-table purge assertion |

### Frontend

| File | Action |
|---|---|
| `frontend/src/api/enums.ts` | Modify |
| `frontend/src/api/schema.d.ts` | Regenerate |
| `frontend/src/api/types.ts` | Modify — add submission aliases |
| `frontend/src/api/endpoints/auditorEngagements.ts` | Modify |
| `frontend/src/api/endpoints/auditease.ts` | Modify |
| `frontend/src/api/hooks/auditorEngagements.ts` | Modify |
| `frontend/src/api/hooks/auditease.ts` | Modify |
| `.../requirements/progress.ts` | Rewrite |
| `.../requirements/RequirementsProgress.tsx` | **Delete** |
| `.../requirements/RequirementsProgress.test.tsx` | **Delete** |
| `.../requirements/RequirementsOverview.tsx` | **Create** |
| `.../requirements/RequirementStatePill.tsx` | **Create** |
| `.../requirements/RequirementCard.tsx` | **Create** |
| `.../requirements/SubmissionTimeline.tsx` | **Create** |
| `.../requirements/DocumentChip.tsx` | **Create** |
| `.../requirements/StackedDocsBadge.tsx` | **Create** |
| `.../requirements/RespondPanel.tsx` | **Create** |
| `.../requirements/NewRequirementModal.tsx` | Rewrite |
| `.../requirements/requirementForm.ts` | Rewrite |
| `.../requirements/BulkImportModal.tsx` | Modify — copy only |
| `.../requirements/PriorityChip.tsx` | Unchanged |
| `frontend/src/pages/auditor/RequirementsTab.tsx` | Rewrite |
| `frontend/src/pages/company/auditease/RequirementsTab.tsx` | Rewrite |

### Frontend tests

| File | Action |
|---|---|
| `.../requirements/progress.test.ts` | **Create** |
| `.../requirements/RequirementsOverview.test.tsx` | **Create** |
| `.../requirements/RequirementCard.test.tsx` | **Create** |
| `.../requirements/RespondPanel.test.tsx` | **Create** |
| `.../requirements/NewRequirementModal.test.tsx` | Rewrite |

---

## 7. Backend — file by file

### 7.1 `app/models/auditease.py`

**Replace** `RequestStatus` (currently lines 56–59):

```python
class RequestStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
```

**Delete** `ExpectedFormat` entirely (currently lines 62–66).

**Replace** `RequirementRequest` (currently lines 254–293) with:

```python
class RequirementRequest(Base, TimestampMixin):
    """One information request against an engagement. Open from creation; only an
    auditor closes it. The requirement text is a single free-form field — there is
    deliberately no title, period, entity, or hierarchy."""
    __tablename__ = "requirement_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"),
        nullable=False, index=True)
    raised_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auditors.id"), nullable=False)
    seq_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        SAEnum(RequestStatus, name="request_status"),
        default=RequestStatus.open, server_default="open", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auditors.id", ondelete="SET NULL"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __init__(self, **kwargs):
        # SQLAlchemy applies Python-side column defaults at flush, not at construction;
        # seed them eagerly so a freshly built (unflushed) instance reads correctly.
        super().__init__(**kwargs)
        if kwargs.get("priority") is None:
            self.priority = 1
        if kwargs.get("status") is None:
            self.status = RequestStatus.open

    @property
    def requirement_id(self) -> str:
        return f"REQ-{self.seq_number or 0:03d}"
```

**Replace** `RequirementResponse` (currently lines 294–307) and **add** the join table:

```python
class RequirementResponse(Base):
    """One submission round ("edition") against a requirement: optional text plus
    any number of documents. Append-only — round 2 never overwrites round 1."""
    __tablename__ = "requirement_responses"
    __table_args__ = (
        UniqueConstraint("requirement_id", "round_number", name="uq_req_response_round"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requirement_requests.id", ondelete="CASCADE"),
        nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nullable only for legacy rows whose respondent was never recorded.
    responded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True)
    text_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # lazy="raise": every read path must selectinload() this explicitly.
    documents = relationship(
        "RequirementResponseDocument", cascade="all, delete-orphan", lazy="raise")


class RequirementResponseDocument(Base):
    """A document attached to one submission round.

    `document_id` is SET NULL rather than CASCADE and is paired with a `filename`
    snapshot: if the company later deletes the document from docVault, the audit
    history must still truthfully show that six files were submitted, not four.
    """
    __tablename__ = "requirement_response_documents"
    __table_args__ = (
        UniqueConstraint("response_id", "document_id", name="uq_req_response_document"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    response_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requirement_responses.id", ondelete="CASCADE"),
        nullable=False, index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
```

`RequirementRequest` gets **no** `responses` relationship — read paths query explicitly,
which avoids async lazy-load hazards.

### 7.2 `alembic/versions/<rev>_requirements_open_closed.py` — new

`revision = "<new>"`, `down_revision = "a4b5c6d7e8f9"`.

**Upgrade, in this exact order:**

1. **Create `requirement_response_documents`** with the columns, indexes, and unique
   constraint from §7.1.

2. **Backfill it** from existing single-document responses:

```sql
INSERT INTO requirement_response_documents (id, response_id, document_id, filename)
SELECT gen_random_uuid(), rr.id, rr.document_id,
       COALESCE(dv.original_filename, d.title, 'document')
FROM requirement_responses rr
JOIN documents d ON d.id = rr.document_id
LEFT JOIN document_versions dv ON dv.id = d.current_version_id
WHERE rr.document_id IS NOT NULL;
```

3. **Add `round_number`** nullable, backfill, then enforce:

```sql
ALTER TABLE requirement_responses ADD COLUMN round_number INTEGER;
WITH ranked AS (
  SELECT id, row_number() OVER (PARTITION BY requirement_id ORDER BY created_at, id) AS rn
  FROM requirement_responses)
UPDATE requirement_responses r SET round_number = ranked.rn
FROM ranked WHERE ranked.id = r.id;
ALTER TABLE requirement_responses ALTER COLUMN round_number SET NOT NULL;
```
Then add `uq_req_response_round`.

4. **Drop** `requirement_responses.document_id` (drop its FK constraint first).

5. **Swap the status enum.** Postgres cannot remove enum values in place:

```sql
CREATE TYPE request_status_new AS ENUM ('open', 'closed');
ALTER TABLE requirement_requests ALTER COLUMN status DROP DEFAULT;
ALTER TABLE requirement_requests
  ALTER COLUMN status TYPE request_status_new
  USING (CASE WHEN status::text = 'accepted' THEN 'closed' ELSE 'open' END)::request_status_new;
DROP TYPE request_status;
ALTER TYPE request_status_new RENAME TO request_status;
ALTER TABLE requirement_requests ALTER COLUMN status SET DEFAULT 'open';
```

6. **Backfill `seq_number`, then enforce NOT NULL:**

```sql
WITH ranked AS (
  SELECT id, row_number() OVER (PARTITION BY engagement_id ORDER BY created_at, id) AS rn
  FROM requirement_requests WHERE seq_number IS NULL)
UPDATE requirement_requests r
SET seq_number = ranked.rn + COALESCE(
      (SELECT max(seq_number) FROM requirement_requests x
       WHERE x.engagement_id = r.engagement_id), 0)
FROM ranked WHERE ranked.id = r.id;
ALTER TABLE requirement_requests ALTER COLUMN seq_number SET NOT NULL;
```

7. **Drop the eleven columns** — drop the `parent_requirement_id` and
   `responsible_person_id` FK constraints first, then drop: `title`,
   `additional_details`, `period_from`, `period_to`, `entity`, `responsible_person_id`,
   `expected_format`, `auditor_notes`, `parent_requirement_id`, `clarification_note`,
   `company_eta`. Then `DROP TYPE expected_format`.

8. **Add `closed_by`, `closed_at`.** Backfill `closed_at = updated_at` where
   `status = 'closed'`; leave `closed_by` NULL (retroactively unknowable).

**Downgrade** recreates the eleven columns nullable and empty, restores a four-value enum
mapping `closed → accepted` and `open → pending`, re-adds `document_id` populated from the
first join row per response, and drops the join table and `round_number`.
It is **lossy by design** and the docstring must say so: requirements that were
`submitted` or `clarification_needed` are indistinguishable after upgrade, and the eleven
dropped columns are gone.

> **Operational:** take a database backup before running. Agreed as acceptable — all
> existing requirement metadata may be lost.

### 7.3 `app/schemas/auditease.py`

Delete the `ExpectedFormat` import. **Replace** `RequirementRequestCreate`,
`RequirementResponseOut`, and `RequirementRequestResponse` (currently lines 421–477):

```python
class RequirementRequestCreate(BaseModel):
    description: str = Field(min_length=1)
    priority: int = Field(default=1, ge=1, le=5)
    due_date: Optional[date] = None


class RequirementResponseDocumentOut(BaseModel):
    # None when the document was later deleted from docVault; `filename` survives.
    document_id: Optional[uuid.UUID] = None
    filename: str
    size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    model_config = {"from_attributes": True}


class RequirementSubmissionOut(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    round_number: int
    responded_by: Optional[uuid.UUID] = None
    responded_by_name: Optional[str] = None
    text_answer: Optional[str] = None
    created_at: datetime
    documents: List[RequirementResponseDocumentOut] = []
    model_config = {"from_attributes": True}


class RequirementRequestResponse(BaseModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    raised_by: uuid.UUID
    raised_by_name: Optional[str] = None
    seq_number: int
    requirement_id_str: Optional[str] = None   # display id, e.g. REQ-001
    description: str
    status: RequestStatus
    priority: int = 1
    due_date: Optional[date] = None
    closed_by: Optional[uuid.UUID] = None
    closed_by_name: Optional[str] = None
    closed_at: Optional[datetime] = None
    submissions: List[RequirementSubmissionOut] = []
    submission_count: int = 0
    document_count: int = 0
    linked_query_count: int = 0
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
```

**Renames and removals to note:** `RequirementResponseOut` → `RequirementSubmissionOut`;
the `responses` field → `submissions`; `latest_response` is **removed** (the timeline
renders all rounds); `title`, `company_eta`, `additional_details`, `period_from`,
`period_to`, `entity`, `responsible_person_id`, `responsible_person_name`,
`expected_format`, `auditor_notes`, `parent_requirement_id`, `clarification_note` are all
**removed**.

### 7.4 `app/services/requirements.py` — new

Holds everything shared by the two routers. Exact public surface:

```python
async def next_seq(db: AsyncSession, engagement_id: uuid.UUID) -> int:
    """Next per-engagement sequence number (max + 1)."""

async def enrich_requirements(
    db: AsyncSession, engagement_id: uuid.UUID, req_list: Sequence[RequirementRequest]
) -> list[dict]:
    """Build API dicts: submission rounds with their documents (filename, size,
    mime type), submission/document counts, linked-query counts, raiser and closer
    names, and the REQ-xxx display id. One batched query per concern — never N+1."""

def submission_document_title(req_display_id: str, round_number: int, filename: str) -> str:
    """e.g. 'REQ-003 · Sub 2 · bank-statement-jan.pdf' (truncated to 255 chars)."""

def submission_document_tags(engagement_id: uuid.UUID, req_display_id: str) -> list[str]:
    """['audit-attachment', 'engagement:<uuid>', 'REQ-003']"""

async def validate_document_ids(
    db: AsyncSession, company_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
) -> None:
    """Raise HTTPException(404) unless EVERY id is a document of `company_id`.
    All-or-nothing: one bad id rejects the whole submission."""

async def create_submission(
    db: AsyncSession, *, req: RequirementRequest, engagement_id: uuid.UUID,
    company_id: uuid.UUID, user_id: uuid.UUID, text_answer: str | None,
    files: Sequence[UploadFile], document_ids: Sequence[uuid.UUID],
) -> RequirementResponse:
    """Create one round at max(round_number)+1, upload each file into the shared
    Audit Attachments bucket via create_attachment_document(), link every uploaded
    and picked document with its filename snapshot, and grant read to every
    accepted auditor holding the requirements area. Does NOT commit."""
```

`enrich_requirements` moves here verbatim-in-spirit from
`app/routers/auditor_engagements.py:75` and is rewritten for the new shape.

**Filename resolution** for the snapshot and for `size_bytes`/`mime_type` in the payload
comes from `document_versions` joined via `documents.current_version_id`.

### 7.5 `app/services/document_access.py`

**Move** `grant_document_access_to_auditors(db, engagement_id, document_id)` here from
`app/routers/auditease.py:1307-1331` — unchanged logic. It belongs beside the existing
`grant_auditor_read` and `create_attachment_document`, and both routers now need it.

### 7.6 `app/services/requirement_import.py` — rewrite

```python
IMPORT_HEADERS = ["S. No.", "Requirement", "Due Date", "Priority"]

_INSTRUCTIONS = [
    "AuditEase — bulk requirement import.",
    "Fill the Requirements sheet. One row per requirement. Do not rename columns.",
    "Requirement is mandatory. Every other column is optional.",
    "S. No. is for your own reference only — AuditEase assigns REQ ids itself, "
    "continuing after the requirements already on the page.",
    "Due Date: blank, or YYYY-MM-DD / a real Excel date.",
    "Priority: blank (= 1) or a whole number 1-5.",
    "Documents cannot be attached here — the company attaches them from the requirement.",
    "Any row with an error aborts the whole file — fix it and re-upload.",
]

def build_template_xlsx() -> bytes:
    """Two sheets: 'Instructions' (the lines above) and 'Requirements' (the four
    bold headers plus one example row the auditor deletes before use)."""

def parse_rows(rows: List[list]) -> List[dict]:
    """Structural parsing only. Each dict is {row, description, due_date, priority}.
    Raises RowError(row, message) on the first malformed row."""

async def import_requirements(
    db: AsyncSession, engagement_id: uuid.UUID, raised_by: uuid.UUID, rows: List[list],
) -> List[RequirementRequest]:
    """Parse and validate every row, then stage creations on the caller's session
    with sequential seq_numbers continuing from the engagement's current maximum.
    Rolls back and raises ImportRejected on any failure. Does NOT commit."""
```

Column semantics:

| Column | Index | Rule |
|---|---|---|
| `S. No.` | 0 | **Read but never stored, never validated, never used for ordering.** Duplicates and blanks tolerated |
| `Requirement` | 1 | Mandatory. Blank → `RowError` |
| `Due Date` | 2 | Optional. Excel date or `YYYY-MM-DD`; anything else → `RowError` |
| `Priority` | 3 | Optional. Blank → 1. Must be a whole number 1–5 |

- `seq_number` continues from the engagement's current maximum in **sheet row order**, so
  a file numbered 1–50 imported into an engagement holding REQ-001…REQ-010 lands as
  REQ-011…REQ-060.
- Error reports cite the **Excel row number** (header = row 1, first data row = row 2),
  not `S. No.`
- All-or-nothing and the 422 `[{row, message}]` report are preserved. Blank spacer rows
  are still skipped.
- **Deleted:** `_to_format`, `_email_key`, the `company_id` parameter, responsible-person
  email resolution, parent-requirement resolution, and period parsing. `_to_date` and
  `_to_priority` are kept.

### 7.7 `app/routers/auditor_engagements.py`

**Delete:**
- `_next_seq` (lines 69–72) — moved to the service
- `enrich_requirements` (lines 75–112) — moved to the service
- `_validate_refs` (lines 115–127) — both branches gone
- `_would_cycle` (lines 130–144) — hierarchy gone
- `_apply_metadata` (lines 147–159) — replaced by a 3-field inline assignment
- `class RequirementReviewCreate` and `review_requirement` (lines 475–517)

**Imports:** drop `RequirementResponse`; add
`from app.services.requirements import next_seq, enrich_requirements`. Verify whether
`CompanyUser` is still used elsewhere in the file before removing its import.

**`create_requirement`** — unchanged shape; builds with `description`, `priority`,
`due_date`, `seq_number=await next_seq(...)`.

**`update_requirement`** — remove the creator-only `raised_by` filter, the parent/cycle
block, and the "text only while pending" rule. New body:

```
403/404 as today (by id + engagement_id only)
if db_req.status == RequestStatus.closed: 400 "Reopen the requirement before editing it"
assign description, priority, due_date
log_activity(... "requirement.updated" ...)
```

**`delete_requirement`** — remove the creator-only filter and the child check. New guard:

```
if a RequirementResponse exists for req_id:
    400 "This requirement has company submissions and cannot be deleted. Close it instead."
```

**Add two endpoints:**

```python
@router.post("/engagements/{engagement_id}/requirement-requests/{req_id}/close",
             response_model=RequirementRequestResponse)
# area="requirements"; 400 "Requirement is already closed"
# sets status=closed, closed_by=current_auditor.id, closed_at=now(utc)
# logs requirement.closed

@router.post("/engagements/{engagement_id}/requirement-requests/{req_id}/reopen",
             response_model=RequirementRequestResponse)
# area="requirements"; 400 "Requirement is already open"
# sets status=open, closed_by=None, closed_at=None
# logs requirement.reopened
```

**`import_requirements_endpoint`** — drop the `eng.company_id` argument from the
`import_requirements(...)` call.

### 7.8 `app/routers/auditease.py`

**Line 40:** replace `from app.routers.auditor_engagements import enrich_requirements`
with `from app.services.requirements import enrich_requirements, create_submission`.

**Delete:**
- `class RequirementRespond` (JSON body) — replaced by Form/File parameters
- `class CompanyEtaUpdate`
- `grant_document_access_to_auditors` (lines 1307–1331) — moved to `document_access.py`
- `set_requirement_eta` (lines 1388–1410)

**Keep** `_owned_requirement` unchanged — it is the tenant gate.

**Rewrite `respond_requirement`** as multipart:

```python
@router.post("/engagements/{engagement_id}/requirement-requests/{req_id}/respond",
             response_model=RequirementRequestResponse)
async def respond_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    text_answer: Annotated[Optional[str], Form()] = None,
    document_ids: Annotated[Optional[List[uuid.UUID]], Form()] = None,
    files: Annotated[Optional[List[UploadFile]], File()] = None,
):
    req = await _owned_requirement(db, current_user, engagement_id, req_id)
    if req.status == RequestStatus.closed:
        raise HTTPException(400, "This requirement is closed. Ask the auditor to reopen it.")
    text = (text_answer or "").strip() or None
    docs, ups = document_ids or [], files or []
    if not text and not docs and not ups:
        raise HTTPException(422, "Provide an answer, attach a document, or upload a file")

    submission = await create_submission(
        db, req=req, engagement_id=engagement_id, company_id=current_user.company_id,
        user_id=current_user.id, text_answer=text, files=ups, document_ids=docs)

    await log_activity(db, current_user.company_id, current_user.id,
        "requirement.submitted", "requirement_request", req.id,
        metadata_={"round_number": submission.round_number,
                   "file_count": len(ups) + len(docs)},
        actor_type=ActorType.company_user, engagement_id=engagement_id)
    await db.commit()
    await db.refresh(req)
    await attach_actor_names(db, [req], "raised_by", "raised_by_name")
    return (await enrich_requirements(db, engagement_id, [req]))[0]
```

`create_submission` calls `validate_document_ids` **before** writing anything, so a bad id
leaves no `Document`, no `DocumentVersion`, and no file on disk.

### 7.9 `app/services/account_admin.py`

No code change — the join table's `response_id` CASCADE cleans up behind the existing
`delete(RequirementResponse)` at line 177. Update the docstring at lines 123–125 to
mention `requirement_response_documents`, and prove the cascade with a test (§10).

---

## 8. Frontend — file by file

### 8.1 `frontend/src/api/enums.ts`

```ts
export const REQUEST_STATUS = ['open', 'closed'] as const
```

In `STATUS_TONE`, **delete** the three-line RequestStatus block (`pending`,
`clarification_needed`, `accepted`) and its comment. **Add nothing** — see §12.1: `closed`
already maps to `neutral` for `EngagementStatus`, so requirement state must not render
through this shared map.

The `_guards` block (`l: REQUEST_STATUS satisfies readonly S['RequestStatus'][]`) will fail
to compile until `schema.d.ts` is regenerated — these land together.

### 8.2 `frontend/src/api/schema.d.ts` and `types.ts`

Regenerate: start the backend, then `cd frontend && npm run gen:api`.

In `types.ts`, keep the two existing aliases and add:

```ts
export type RequirementSubmission = S['RequirementSubmissionOut']
export type RequirementSubmissionDocument = S['RequirementResponseDocumentOut']
```

### 8.3 `endpoints/auditorEngagements.ts`

**Remove** `reviewRequirement` (lines 52–60). **Add** — note the client signature is
`post<T>(path, opts?)` with the body inside `opts` (`{ body }` for JSON, `{ formData }` for
multipart), never positional:

```ts
closeRequirement: (id: string, reqId: string) =>
  auditorClient.post<RequirementRequestResponse>(
    `/api/v1/auditor/engagements/${id}/requirement-requests/${reqId}/close`,
  ),
reopenRequirement: (id: string, reqId: string) =>
  auditorClient.post<RequirementRequestResponse>(
    `/api/v1/auditor/engagements/${id}/requirement-requests/${reqId}/reopen`,
  ),
```

Both endpoints take no body, so `opts` is omitted entirely.

### 8.4 `endpoints/auditease.ts`

**Remove** `setRequirementEta` (lines 145–148). **Change** `respondRequirement` from
`{ body }` to `{ formData }` — `RequestOptions.formData` (`http.ts:22`) already exists and
is what `bulkImportRequirements` and `createQuery` use:

```ts
respondRequirement: (engagementId: string, reqId: string, formData: FormData) =>
  companyClient.post<RequirementRequestResponse>(
    `/api/v1/auditease/engagements/${engagementId}/requirement-requests/${reqId}/respond`,
    { formData },
  ),
```

### 8.5 Hooks

`hooks/auditorEngagements.ts` — remove `useAuditorReviewRequirement` (lines 109–117); add
`useAuditorCloseRequirement` and `useAuditorReopenRequirement`, both invalidating
`['auditor', 'requirements', engagementId]`.

`hooks/auditease.ts` — remove `useSetRequirementEta` (lines 309–316); change
`useRespondToRequirement` to take `{ engagementId, reqId, formData }`.

### 8.6 `progress.ts` — rewrite

```ts
export type DisplayState = 'awaiting' | 'responded' | 'closed'
export type RequirementFilter = DisplayState | 'overdue'

export interface RequirementLite {
  status: string
  submission_count?: number
  document_count?: number
  due_date?: string | null
}

export function deriveState(r: RequirementLite): DisplayState
export function isOverdue(r: RequirementLite): boolean
export function matchesFilter(r: RequirementLite, f: RequirementFilter | null): boolean
export function computeCounts(rs: RequirementLite[]): Record<DisplayState, number>
export function overdueCount(rs: RequirementLite[]): number
export function documentTotal(rs: RequirementLite[]): number
export function percentComplete(rs: RequirementLite[]): number  // closed / total
```

`isOverdue` and `fmtDate` currently duplicated as local helpers in
`pages/auditor/RequirementsTab.tsx:42` and the company tab move here (`fmtDate` into a
shared place or `DocumentChip`/card as appropriate) — remove the duplicates.

### 8.7 `RequirementsOverview.tsx` — new

Replaces `RequirementsProgress.tsx` (delete it and its test).

- **Donut:** three concentric SVG arcs on `r=44` (circumference ≈ 276.46), drawn
  closed → responded → awaiting, animated on `stroke-dashoffset` with the existing
  framer-motion spring (`stiffness: 120, damping: 20`). Animates from zero **on mount
  only**, not on refetch. Centre shows `percentComplete` via `CountUp` + the label
  "closed".
- **Tiles:** four, built on the existing `StatCard` (`label`, `value`, `tone`) —
  Requirements, Documents in, Awaiting review (info tone), Overdue (danger tone).
- **Filter pills** below a divider: Closed / Responded / Awaiting / Overdue, each with a
  colour dot and `CountUp` count, toggling `activeFilter`.

Props: `{ requirements, activeFilter, onFilterChange }`.

### 8.8 `RequirementStatePill.tsx` — new

Exists specifically to fix §12.1. Maps `DisplayState` → label + explicit `StatusBadge`
tone, bypassing the shared `STATUS_TONE` map:

| State | Label | tone |
|---|---|---|
| `awaiting` | `Awaiting` | `neutral` |
| `responded` | `Responded` | `info` |
| `closed` | `Closed` | `success` |

### 8.9 `RequirementCard.tsx` — new

Props: `{ req, expanded, onToggle, actions, accent: 'company' | 'auditor' }`.

- **Collapsed:** chevron, mono `REQ-003` chip, single-line truncated description,
  `StackedDocsBadge` when `document_count > 0`, `PriorityChip` when `priority > 1`,
  `RequirementStatePill`, due date (red + "overdue" when `isOverdue`).
- **Expanded:** full description, a Documents / History tab strip, `SubmissionTimeline`,
  and a footer strip carrying the linked-query count and the `actions` slot.
- Row is focusable; Enter/Space toggles. Expansion state is owned by the parent tab so it
  survives query refetches.

### 8.10 `SubmissionTimeline.tsx`, `DocumentChip.tsx`, `StackedDocsBadge.tsx` — new

- **`SubmissionTimeline`** — rounds newest-first on a vertical rail: "Submission N",
  date, respondent name, file count, optional text, then a two-column grid of
  `DocumentChip`. The **History** tab additionally shows created / closed / reopened
  markers from the requirement's own fields.
- **`DocumentChip`** — file-type square (extension-derived), truncating filename, size,
  download action. When `document_id` is `null` the chip renders disabled with a
  "removed from docVault" title, still showing the snapshot filename.
- **`StackedDocsBadge`** — three offset page rectangles plus a count.

### 8.11 `RespondPanel.tsx` — new (company only)

Uses the **existing** `FileUploadDropzone` (`onFilesSelected`, `multiple`, `hint`) — no
new upload primitive needed.

- Textarea for the written answer.
- Dropzone with `multiple`, listing staged files with per-file remove.
- Multi-select picker over DocVault documents (`useDocuments()`).
- Submit disabled until text, a staged file, or a picked document exists.
- Builds `FormData`: `text_answer`, repeated `files`, repeated `document_ids`.
- On failure, keeps typed text and remaining selections and surfaces the server message.
- **No size or count limits** (§13).

### 8.12 `NewRequirementModal.tsx` and `requirementForm.ts` — rewrite

Modal keeps: next-`REQ-xxx` preview, requirement **Textarea** (was an Input — the field is
now the whole requirement), priority selector, due date. **Delete:** the `advancedOpen`
state and the entire advanced block (title, additional details, period from/to, entity,
responsible person, expected format, parent requirement, auditor notes) — lines 116–168 —
plus the props that fed them.

`requirementForm.ts`:

```ts
export type RequirementFormState = { description: string; priority: number; due_date: string }
export function validateRequirementForm(f: RequirementFormState): string | null
  // description required; due_date not in the past
export function buildRequirementPayload(f: Partial<RequirementFormState>): RequirementRequestCreate
```

### 8.13 `BulkImportModal.tsx`

Structure unchanged (template download, file pick, upload, per-row 422 list). Only the
guidance copy changes to name the four columns and state that `S. No.` is for reference
and that REQ ids continue from the existing list.

### 8.14 `pages/auditor/RequirementsTab.tsx` — rewrite

Layout: `RequirementsOverview` → header row with Bulk import / New requirement →
`RequirementCard` list.

- Remove the flat-vs-child machinery entirely: `roots`, `childrenOf`,
  `visibleChildrenOf`, `expandedChildren`, `visibleRootFilter` (line 409), the `ChildRow`
  component (line 413), `historyFor`, `clarifyFor`, `clarifyNote`, and the local
  `isOverdue`.
- Replace `useAuditorReviewRequirement` with the close/reopen hooks.
- `actions` slot: Edit, Raise query (keeping the existing circular button with
  `hover:scale-[1.15]` and the linked-query badge), Close **or** Reopen, and Delete
  (only when `submission_count === 0`, behind the existing `ConfirmDialog`).
- Keep `nextReqId` for the modal preview.

### 8.15 `pages/company/auditease/RequirementsTab.tsx` — rewrite

Same overview and cards; `actions` slot is a single **Respond** button opening
`RespondPanel` inside the expanded card. Remove the ETA popover (lines ~180–195), the
`expected_format` hint, the clarification banner, the entity/period metadata line, the
"You're responsible" badge, `useMe()`, and `useSetRequirementEta`.

Empty states: no requirements / all closed / nothing matches this filter — three distinct
`EmptyState` copies.

---

## 9. Security & authorization

Requirements are the one place a company's encrypted documents are deliberately exposed to
an outside auditor, so every rule is explicit and test-backed.

1. **Principal isolation unchanged.** Auditor routes depend on `get_current_auditor`
   (`principal_type: "auditor"`); company routes on `get_current_company_user`
   (`principal_type: "company_user"`). No route accepts either.
2. **Every auditor route — including the new `close` and `reopen` —** calls
   `check_auditor_access(db, auditor_id, engagement_id, area="requirements")`, requiring a
   grant in `invited`/`accepted` on an `active` engagement **and**
   `area_permissions["requirements"] is True`.
3. **Every company route** resolves through `_owned_requirement()`, asserting
   `AuditEngagement.company_id == current_user.company_id`.
4. **No IDOR on `req_id`.** Every lookup filters on both `id` **and** `engagement_id`, and
   the engagement is already scoped to the caller's tenant or grant.
5. **Cross-tenant document attachment is blocked.** `validate_document_ids` checks **every**
   entry of `document_ids[]` against `Document.company_id` and rejects the whole request on
   the first failure. This is the highest-risk new code in the change; today's code checks
   only a single id, so the loop is a new opportunity to get it wrong.
6. **No upload limits are introduced** — see §13. Nothing else in this section relaxes.
7. **Auditor read access is granted narrowly.** `grant_document_access_to_auditors` grants
   `read` only to auditors whose grant is `accepted` **and** who hold the `requirements`
   area, and is idempotent.
8. **Download is unchanged and independently gated.** `auditor_can_access_document`
   requires an override row, a live non-revoked grant to a non-closed engagement of that
   document's company, **and** the `documents` area — so revoking either area, or closing
   the engagement, ends access even though the override row persists.
9. **Encryption untouched.** Uploads go through `handle_file_upload()`: per-file DEK,
   AES-GCM payload, DEK wrapped under the company KEK. No plaintext is written and no new
   storage path is introduced.
10. **Untrusted workbooks** stay behind `openpyxl` in `read_only` mode via `load_sheet()`.
11. **Every mutation is logged** with the correct `ActorType`, including the two new events.
12. **Deleting a requirement cannot destroy company evidence** — `DELETE` is refused while
    any submission exists.
13. **Rejected submissions write nothing** — validation precedes all encryption and disk I/O.

---

## 10. Test inventory

### Backend

**`unit_tests/test_requirement_models.py`** (rewrite) — new column set; `status` defaults
to `open`; `priority` defaults to 1 on an unflushed instance; `REQ-007` formatting;
`RequirementResponse` requires `round_number`; `RequirementResponseDocument` holds a
`filename` with a null `document_id`.

**`unit_tests/test_requirement_import.py`** (rewrite) — template has exactly the four
headers plus an example row; minimal row defaults (`priority == 1`, `due_date is None`);
full row parses; missing requirement → `RowError` on row 2; non-numeric priority;
priority 0 and 6; malformed date; real `datetime` cell accepted; blank spacer rows skipped;
duplicate and blank `S. No.` ignored.

**`tests/test_auditease.py`**
- `test_requirements_and_queries` (lines 803–897) — rewrite: create → `status == "open"`,
  `REQ-001`, `priority == 1`; second → `REQ-002`; respond with text → still `open`,
  `submission_count == 1`; respond again → `round_number == 2`, two `submissions`; close →
  `closed`, `closed_at` set; respond while closed → 400; edit while closed → 400; reopen →
  `open`; edit now succeeds; delete with submissions → 400; empty respond → 422; query
  links to the requirement.
- `test_requirement_parenting_guards` (line 900) — **delete** (hierarchy removed).
- `test_requirement_bulk_import_roundtrip` (line 1468) — rewrite for four columns; drop the
  parent-reference row; assert `REQ-001`/`REQ-002`, `priority == 4`, and that a second
  import appends `REQ-003`+.

**`tests/test_requirement_submissions.py`** (new)
- Six files in one call → one `RequirementResponse`, six join rows, `document_count == 6`.
- Text-only, files-only, picked-documents-only, and mixed all succeed; empty → 422.
- `round_number` increments 1 → 2 → 3; `submissions` ordered.
- Every accepted auditor with the `requirements` area gets a `DocumentAccessOverride` for
  each document; an auditor without the area does not.
- Uploaded documents land in the `"Audit Attachments"` bucket, titled
  `REQ-003 · Sub 1 · <filename>` and tagged with `engagement:<id>` and `REQ-003`.
- Deleting a document via `DELETE /api/v1/docvault/documents/{id}` leaves the join row with
  `document_id is None` and the `filename` intact, and `document_count` unchanged.
- **Security:** a `document_id` from another company → 404, including when mixed with valid
  ids, **and no `RequirementResponse` row is created**; another tenant's user → 404; an
  auditor with no grant → 403; a `req_id` from another engagement → 404.

**`tests/test_auditease_multi_auditor.py`** — replace the `review` probe (line 220) with
`close` and `reopen` probes; add that a non-creating auditor with the area may edit, close,
and reopen; update the logged-action set at line 259 to
`{"auditor.grant_accepted", "requirement.raised", "requirement.deleted", ...}` plus
`requirement.closed` / `requirement.reopened` where exercised; update line 375's
respond call to multipart.

**`tests/test_account_admin.py`** — after a company purge, assert zero rows remain in
`requirement_response_documents`.

### Frontend

**`progress.test.ts`** (new) — `deriveState` for all combinations; `isOverdue` boundary at
today and for closed requirements; `computeCounts`; `overdueCount`; `documentTotal`;
`percentComplete` including the empty list.

**`RequirementsOverview.test.tsx`** (new) — donut arc offsets for a known mix; the four tile
values; pill toggling calls `onFilterChange` with the right value and `null` on re-click;
zero-requirements renders 0% without dividing by zero.

**`RequirementCard.test.tsx`** (new) — collapsed shows truncated text and the stacked badge
count; expanded shows the timeline; a `document_id: null` chip renders disabled with its
filename; Enter toggles expansion.

**`RespondPanel.test.tsx`** (new) — staging and removing multiple files; empty submission
blocked; DocVault multi-select; `FormData` carries repeated `files` and `document_ids`;
typed text and remaining selections survive a rejected submit.

**`NewRequirementModal.test.tsx`** (rewrite) — three fields only; requirement required;
priority defaults to 1; due date optional; a past due date is rejected; no advanced section
exists.

---

## 11. Verification

```bash
# Backend
uv run alembic upgrade head
uv run alembic downgrade -1 && uv run alembic upgrade head   # migration round-trip
uv run pytest unit_tests/test_requirement_models.py unit_tests/test_requirement_import.py -q
uv run pytest tests/test_auditease.py tests/test_requirement_submissions.py \
              tests/test_auditease_multi_auditor.py tests/test_account_admin.py -q
uv run pytest -q                                              # full suite

# Frontend (backend must be up on :8000 for gen:api)
cd frontend
npm run gen:api
npm run build      # tsc -b catches the enums.ts _guards mismatch
npm test
npm run lint
```

## 12. Findings from the code review — must be handled

### 12.1 `StatusBadge` cannot express Open vs Closed

`STATUS_TONE` (`frontend/src/api/enums.ts:100`) is a **single flat map keyed by raw status
string, shared across every module**. `closed` is already mapped to `neutral` for
`EngagementStatus`, and `open` is absent (falling through to `neutral`). So
`<StatusBadge status={req.status} />` would render Open and Closed **identically grey**,
and adding `closed: 'success'` would wrongly recolour engagement and query badges.

**Resolution:** requirement state renders through the new `RequirementStatePill` (§8.8),
which passes an explicit `tone` to `StatusBadge` and labels the derived state. The
RequestStatus entries are deleted from `STATUS_TONE` and nothing is added.

### 12.2 Two UI primitives already exist — do not rebuild them

- **`FileUploadDropzone`** (`frontend/src/components/ui/FileUploadDropzone.tsx`) already
  supports `multiple`, `accept`, `hint`, `disabled`. `RespondPanel` uses it.
- **`StatCard`** (`frontend/src/components/ui/StatCard.tsx`) already animates a numeric
  `value` and takes a `tone`. `RequirementsOverview` uses it for all four tiles.

A `Drawer` primitive also exists but is deliberately unused — the chosen layout expands in
place.

### 12.3 Router-to-router import

`app/routers/auditease.py:40` does `from app.routers.auditor_engagements import
enrich_requirements`. §7.4 removes this coupling by moving the function to
`app/services/requirements.py`.

### 12.4 `main` and `graph` have diverged on this module

`main` still has `RequestStatus = open|fulfilled`, `PATCH /fulfill`, no
`RequirementResponse` table, no import service, and no requirements components — and a live
bug where `RequirementRequestResponse` exposes `fulfilled_document_id` that the model no
longer defines. **All work happens on `graph`.** Merging `graph` to `main` is a separate
exercise.

## 13. Accepted risks

1. **The Postgres enum swap is irreversible** with respect to which requirements were
   `submitted` versus `pending` — both become `open`.
2. **The hard column drop is unrecoverable** without a backup. Eleven columns of
   auditor-entered text are deleted by explicit decision, accepted as fine.
3. **Backend enum, `enums.ts`, and `schema.d.ts` must ship together** or the frontend will
   not compile; `gen:api` needs a running backend.
4. **Multi-document validation is the highest-risk new code** (§9.5).
5. **All engagements' documents continue to share one bucket** by explicit decision.
   Grouping is correct inside the Requirements tab, but DocVault browsing stays flat and
   will grow busy.
6. **Unbounded uploads are an accepted exposure.** No file-size, file-count, or import-row
   limits exist anywhere today and none are added. `respond` widens the surface from one
   document per request to many, so an authenticated company user can submit arbitrarily
   many files of arbitrary size, each encrypted and written to `VAULT_STORAGE_PATH`. Disk
   exhaustion is the realistic failure mode; tenant isolation and access control are
   unaffected. Deferred to a team decision on where limits belong.

## 14. Out of scope

- Any upload, file-count, or row-count limit (§13.6).
- Bulk zip download of a requirement's documents.
- Nested DocVault buckets / `parent_bucket_id`.
- Notifications or email on close, reopen, or submission.
- Requirement hierarchy, responsible-person assignment, expected-format hints, and company
  ETA — deliberately **deleted, not deferred**.
- Merging `graph` into `main`.
