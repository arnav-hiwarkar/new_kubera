import json
import uuid
from typing import Annotated, List, Optional
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, ValidationError, model_validator
from sqlalchemy import select, and_, or_, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_company_user, require_manager_or_admin
from app.models.company import CompanyUser
from app.models.auditor import Auditor
from app.models.activity_log import ActorType, ActivityLog
from app.models.auditease import (
    TrialBalanceAccount, LedgerGroup, AuditEngagement, AuditorEngagementGrant,
    PendingAuditorInvite, AuditEntry, AuditEntryLine, RequirementRequest, RequirementResponse,
    Query, QueryMessage,
    EngagementStatus, GrantStatus, AuditEntryStatus, EntryLineSide, RequestStatus, QueryStatus,
    SenderType, BalanceNature, TBSignConvention,
    FULL_AREA_PERMISSIONS, AREA_LABELS,
)
from app.schemas.auditease import (
    TrialBalanceAccountResponse, LedgerGroupResponse, LedgerGroupCreate, LedgerGroupRename,
    MapLedgerRequest, BulkMapRequest, UnmapRequest, MappingSourceResponse,
    MappingImportRequest, MappingImportResult, MappingImportIssue, AuditEngagementCreate,
    AuditEngagementResponse, AuditEntryResponse, RequirementRequestResponse,
    QueryResponse, QueryMessageResponse, QueryMessageCreate,
    EngagementAuditorResponse, AuditorInviteCreate, AuditorPermissionsUpdate,
    ActivityEventResponse,
    TBColumnMap, TBInspectResponse, TBImportResult, TBDiagnostics, TBRowIssue,
    TBParsedRow, TBPreviewResponse, TBReimportImpact, TrialBalanceViewResponse,
    SetSignConventionRequest,
    ReportLine, ReportTotals, ReportBalanceCheck, ReportEntrySummary,
    ReportEntriesBlock, ReportPreviewResponse,
)
from app.services.activity import log_activity
from app.services.auditor_access import area_enabled, attach_actor_names, attach_sender_names, normalize_area_permissions
from app.services.requirements import enrich_requirements, create_submission
from app.config import get_settings
from app.services import import_service
from app.services import ledger_groups as lg
from app.services import mapping_import
from app.services import tb_reimport
from app.services import trial_balance as tb
from app.services import trial_balance_query as tbq

router = APIRouter(prefix="/api/v1/auditease", tags=["auditease-company"])


async def _get_owned_engagement(db: AsyncSession, company_id: uuid.UUID, engagement_id: uuid.UUID) -> AuditEngagement:
    result = await db.execute(
        select(AuditEngagement).where(
            and_(AuditEngagement.id == engagement_id, AuditEngagement.company_id == company_id)
        )
    )
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return eng


async def _list_auditors(db: AsyncSession, engagement_id: uuid.UUID) -> list[dict]:
    """Every grant row (incl. revoked) plus pending unregistered invites."""
    rows = await db.execute(
        select(AuditorEngagementGrant, Auditor.name, Auditor.email)
        .join(Auditor, Auditor.id == AuditorEngagementGrant.auditor_id)
        .where(AuditorEngagementGrant.engagement_id == engagement_id)
        .order_by(AuditorEngagementGrant.invited_at.desc())
    )
    out = [
        {
            "auditor_id": g.auditor_id,
            "name": name,
            "email": email,
            "status": g.status.value,
            "area_permissions": g.area_permissions or dict(FULL_AREA_PERMISSIONS),
            "invited_at": g.invited_at,
            "accepted_at": g.accepted_at,
        }
        for g, name, email in rows.all()
    ]
    pend = await db.execute(
        select(PendingAuditorInvite)
        .where(PendingAuditorInvite.engagement_id == engagement_id)
        .order_by(PendingAuditorInvite.created_at.desc())
    )
    for p in pend.scalars().all():
        out.append({
            "auditor_id": None, "name": None, "email": p.email,
            "status": "pending", "area_permissions": dict(FULL_AREA_PERMISSIONS),
            "invited_at": p.created_at, "accepted_at": None,
        })
    return out


async def _hydrate_auditors(db: AsyncSession, eng: AuditEngagement) -> AuditEngagement:
    """Attach the `auditors` array consumed by AuditEngagementResponse."""
    eng.auditors = await _list_auditors(db, eng.id)
    return eng


# --- Trial Balance (per engagement, server-side file import) ---
#
# Flow: inspect (headers + suggested map) -> map -> preview (diagnostics, writes
# nothing) -> import. All accounting lives in app.services.trial_balance; these
# handlers only do HTTP and persistence.

MAX_REPORTED_ISSUES = 200


@router.post("/engagements/{engagement_id}/trial-balance/inspect", response_model=TBInspectResponse)
async def inspect_trial_balance(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Step 1: every sheet's headers, preview rows, detected header row and suggested map."""
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    content = await file.read()
    try:
        sheets = import_service.inspect_spreadsheet(
            file.filename or "", content, preview=8, detect_header=True
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"sheets": sheets}


def _parse_column_map(column_map: str) -> TBColumnMap:
    try:
        return TBColumnMap.model_validate_json(column_map)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Invalid column_map: {e.errors()}")


def _build_diagnostics(
    parsed: import_service.ParsedTrialBalance,
    stated_dr: float | None,
    stated_cr: float | None,
) -> TBDiagnostics:
    v = parsed.validation
    c = parsed.convention
    dropped_by_kind: dict[str, int] = {}
    for d in parsed.dropped:
        dropped_by_kind[d["kind"]] = dropped_by_kind.get(d["kind"], 0) + 1

    issues: list[TBRowIssue] = []
    for e in parsed.errors:
        issues.append(TBRowIssue(
            row=e["row"], kind="error", reason="; ".join(e["errors"]),
        ))
    for d in parsed.dropped:
        if d["kind"] == "blank":
            continue  # blank rows are noise, not something to show a user
        issues.append(TBRowIssue(
            row=d["row"], kind="dropped", reason=d["reason"], raw=d.get("raw") or None,
        ))
    from app.services.reporting.format import format_money
    for m in v.inconsistent_rows:
        issues.append(TBRowIssue(
            row=m["row"], ledger_name=m.get("ledger_name"), kind="warning",
            reason=(f"opening + debit - credit = {format_money(m['expected'])} but the file's "
                    f"closing balance is {format_money(m['found'])}"),
        ))
    issues.sort(key=lambda i: i.row)

    return TBDiagnostics(
        header_row=parsed.header_row + 1,
        rows_scanned=len(parsed.rows) + len(parsed.errors) + len(parsed.dropped),
        rows_imported=len(parsed.rows),
        rows_dropped_blank=dropped_by_kind.get("blank", 0),
        rows_dropped_total=dropped_by_kind.get("total", 0),
        rows_dropped_repeated_header=dropped_by_kind.get("repeated_header", 0),
        rows_section=parsed.section_count,
        rows_error=len(parsed.errors),
        detected_convention=c.convention,
        convention_confidence=c.confidence,
        convention_evidence=list(c.evidence),
        negative_closing_count=c.negative_count,
        explicit_marker_count=c.explicit_marker_count,
        derived_fields=list(v.derived_fields),
        total_debit=float(v.total_debit_movement),
        total_credit=float(v.total_credit_movement),
        debit_credit_difference=float(v.total_debit_movement - v.total_credit_movement),
        movement_balanced=v.movement_balanced,
        closing_sum=float(v.sum_net_debit),
        closing_sums_to_zero=v.balanced,
        opening_sum=float(v.sum_opening_net_debit),
        opening_sums_to_zero=v.opening_balanced,
        row_consistency_mismatches=v.inconsistent_count,
        inconsistent_rows=v.inconsistent_rows,
        sign_unresolved_count=v.sign_unresolved_count,
        sheet_stated_total_debit=stated_dr,
        sheet_stated_total_credit=stated_cr,
        issues=issues[:MAX_REPORTED_ISSUES],
    )


async def _reimport_impact(
    db: AsyncSession, engagement_id: uuid.UUID, parsed_rows: list[dict]
) -> tuple[TBReimportImpact | None, tb_reimport.ReimportPlan | None, list[TrialBalanceAccount]]:
    """What a re-import would do to the stored trial balance, if one already exists."""
    res = await db.execute(
        select(TrialBalanceAccount).where(TrialBalanceAccount.engagement_id == engagement_id)
    )
    existing = list(res.scalars().all())
    if not existing:
        return None, None, existing

    status_res = await db.execute(
        select(AuditEntry.status).where(AuditEntry.engagement_id == engagement_id)
    )
    statuses = list(status_res.scalars().all())
    approved_count = sum(1 for s in statuses if s == AuditEntryStatus.approved)
    proposed_count = sum(1 for s in statuses if s == AuditEntryStatus.proposed)

    ref_res = await db.execute(
        select(AuditEntryLine.ledger_id)
        .join(AuditEntry, AuditEntry.id == AuditEntryLine.entry_id)
        .where(AuditEntry.engagement_id == engagement_id)
    )
    referenced = set(ref_res.scalars().all())

    plan = tb_reimport.plan_reimport(existing, parsed_rows, referenced)
    impact = TBReimportImpact(
        existing_ledger_count=len(existing),
        approved_entry_count=approved_count,
        proposed_entry_count=proposed_count,
        mapped_ledger_count=sum(1 for a in existing if a.mapped_group_id),
        matched_by_code=plan.matched_by_code,
        matched_by_name=plan.matched_by_name,
        new_ledger_count=len(plan.to_insert),
        will_lose_mapping=plan.will_lose_mapping,
        retained_referenced=plan.retained_referenced,
        ambiguous_matches=plan.ambiguous_matches,
        # Only an APPROVED entry means the trial balance is being relied upon. The old
        # guard counted any entry, so a single rejected proposal locked the TB forever.
        requires_confirmation=bool(
            approved_count or plan.will_lose_mapping or plan.ambiguous_matches
        ),
    )
    return impact, plan, existing


@router.post("/engagements/{engagement_id}/trial-balance/preview", response_model=TBPreviewResponse)
async def preview_trial_balance(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    column_map: str = Form(...),
    sheet: Optional[str] = Form(None),
    header_row: Optional[int] = Form(None),
    sign_convention: Optional[str] = Form(None),
):
    """Step 3: report what WOULD happen. Writes nothing.

    Only a structurally unusable mapping is a 400 -- every other finding (dropped
    rows, inconsistent rows, an out-of-balance file) comes back as data, so the
    review screen is non-blocking by construction.
    """
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    cmap = _parse_column_map(column_map)
    content = await file.read()
    convention = _coerce_convention(sign_convention)
    hr = None if header_row is None else max(0, header_row - 1)

    try:
        parsed = import_service.parse_trial_balance(
            file.filename or "", content, sheet, cmap.model_dump(),
            convention=convention, header_row=hr,
        )
        stated_dr, stated_cr = import_service.stated_totals(
            file.filename or "", content, sheet, cmap.model_dump(), hr
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    impact, _, _ = await _reimport_impact(db, engagement_id, parsed.rows)
    return TBPreviewResponse(
        diagnostics=_build_diagnostics(parsed, stated_dr, stated_cr),
        sample_rows=[TBParsedRow(**r) for r in parsed.sample_rows],
        reimport_impact=impact,
        would_import=len(parsed.rows),
        would_skip=len(parsed.errors) + len(parsed.dropped),
    )


def _coerce_convention(value: Optional[str]) -> TBSignConvention | None:
    if not value:
        return None
    try:
        return TBSignConvention(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown sign_convention: {value!r}")


@router.post("/engagements/{engagement_id}/trial-balance/import", response_model=TBImportResult)
async def import_trial_balance(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    column_map: str = Form(...),
    sheet: Optional[str] = Form(None),
    header_row: Optional[int] = Form(None),
    sign_convention: Optional[str] = Form(None),
    confirm: bool = Form(False),
):
    """Step 4: parse `sheet` with `column_map` and upsert this engagement's TB.

    Upsert, not delete-and-reinsert: matching rows keep their `id`, so both the
    user's `mapped_group_id` work and every `audit_entry_lines.ledger_id` foreign key
    survive a re-import. A ledger that vanished from the file but is still referenced
    by an entry line is retained, because `ledger_id` is ON DELETE CASCADE and
    dropping it would take an approved adjustment with it.
    """
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    cmap = _parse_column_map(column_map)
    content = await file.read()
    convention = _coerce_convention(sign_convention)
    hr = None if header_row is None else max(0, header_row - 1)

    try:
        parsed = import_service.parse_trial_balance(
            file.filename or "", content, sheet, cmap.model_dump(),
            convention=convention, header_row=hr,
        )
        stated_dr, stated_cr = import_service.stated_totals(
            file.filename or "", content, sheet, cmap.model_dump(), hr
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    impact, plan, existing = await _reimport_impact(db, engagement_id, parsed.rows)
    if (
        impact
        and impact.retained_referenced
        and eng.tb_sign_convention is not None
        and eng.tb_sign_convention != parsed.convention.convention
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "The new file uses a different sign convention but omits ledgers "
                    "referenced by audit entries. Include those ledgers or keep the "
                    "existing convention; mixing conventions is unsafe."
                ),
                "reimport_impact": impact.model_dump(),
            },
        )
    if impact and impact.requires_confirmation and not confirm:
        raise HTTPException(
            status_code=409,
            detail={
                "message": ("This engagement already has a trial balance that audit "
                            "entries rely on. Re-importing will update it in place. "
                            "Re-send with confirm=true to proceed."),
                "reimport_impact": impact.model_dump(),
            },
        )

    by_id = {a.id: a for a in existing}
    accounts: List[TrialBalanceAccount] = []

    if plan is None:
        for rec in parsed.rows:
            acc = TrialBalanceAccount(
                company_id=current_user.company_id, engagement_id=engagement_id, **rec
            )
            db.add(acc)
            accounts.append(acc)
    else:
        for acc_id, rec in plan.to_update:
            acc = by_id[acc_id]
            for key, value in rec.items():
                setattr(acc, key, value)
            accounts.append(acc)
        for rec in plan.to_insert:
            acc = TrialBalanceAccount(
                company_id=current_user.company_id, engagement_id=engagement_id, **rec
            )
            db.add(acc)
            accounts.append(acc)
        for acc_id in plan.to_retain:
            accounts.append(by_id[acc_id])
        if plan.to_delete:
            await db.execute(
                delete(TrialBalanceAccount).where(TrialBalanceAccount.id.in_(plan.to_delete))
            )

    eng.tb_sign_convention = parsed.convention.convention
    await db.flush()
    # A magnitude-convention file takes its sign from the mapped group's nature, so
    # any mapping that survived the upsert has to be re-applied to the canonical value.
    await tbq.recanonicalize(
        db, engagement_id, current_user.company_id,
        convention=parsed.convention.convention,
    )
    await db.commit()

    figures = await tbq.load_engagement_figures(db, current_user.company_id, engagement_id)
    diagnostics = _build_diagnostics(parsed, stated_dr, stated_cr)
    totals = tbq.totals_response(figures.summary)
    return TBImportResult(
        imported=len(parsed.rows),
        skipped=len(parsed.errors) + len(parsed.dropped),
        errors=parsed.errors,
        total_debit=diagnostics.total_debit,
        total_credit=diagnostics.total_credit,
        # The authoritative answer: does the trial balance sum to zero?
        balanced=totals.balanced,
        accounts=[TrialBalanceAccountResponse.model_validate(a) for a in figures.accounts],
        diagnostics=diagnostics,
        sign_convention=parsed.convention.convention,
        totals=totals,
    )


@router.get("/engagements/{engagement_id}/trial-balance", response_model=TrialBalanceViewResponse)
async def get_trial_balance(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Accounts PLUS server-computed totals.

    The totals travel with the accounts deliberately: when this returned a bare
    array, both workspace pages re-derived their own debit/credit/balanced figures in
    TypeScript and drifted from the report's answer. There is now exactly one
    implementation, in trial_balance.summarize.
    """
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    return await _trial_balance_view(db, current_user.company_id, eng)


async def _trial_balance_view(
    db: AsyncSession, company_id: uuid.UUID, eng: AuditEngagement
) -> TrialBalanceViewResponse:
    figures = await tbq.load_engagement_figures(db, company_id, eng.id)
    return TrialBalanceViewResponse(
        accounts=[TrialBalanceAccountResponse.model_validate(a) for a in figures.accounts],
        totals=tbq.totals_response(figures.summary),
        sign_convention=eng.tb_sign_convention,
        sign_unresolved_count=figures.summary.sign_unresolved_count,
        inconsistent_row_count=sum(
            1 for a in figures.accounts if a.source_row_consistent is False
        ),
        warnings=tbq.view_warnings(
            figures.figures, figures.summary, eng.tb_sign_convention
        ),
    )


@router.post(
    "/engagements/{engagement_id}/trial-balance/sign-convention",
    response_model=TrialBalanceViewResponse,
)
async def set_sign_convention(
    engagement_id: uuid.UUID,
    payload: SetSignConventionRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Correct a mis-detected sign convention without re-importing.

    Deliberately allowed even when audit entries exist: it rewrites only the
    canonical figures derived from the stored source columns, never row identity, so
    every `audit_entry_lines.ledger_id` stays valid. This is the escape hatch that
    makes an ambiguous detection recoverable instead of permanent.
    """
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    await tbq.apply_sign_convention(db, eng, payload.convention)
    await db.commit()
    return await _trial_balance_view(db, current_user.company_id, eng)


# --- Chart of accounts (ledger groups) ---

async def _get_owned_group(db: AsyncSession, company_id: uuid.UUID, group_id: uuid.UUID) -> LedgerGroup:
    """Fetch a group the company may edit — must be company-owned (not seeded)."""
    res = await db.execute(select(LedgerGroup).where(LedgerGroup.id == group_id))
    group = res.scalar_one_or_none()
    if not group or group.company_id not in (None, company_id):
        raise HTTPException(status_code=404, detail="Group not found")
    if group.company_id is None:
        raise HTTPException(status_code=403, detail="Seeded top-level groups cannot be modified")
    return group


async def _visible_group(db: AsyncSession, company_id: uuid.UUID, group_id: uuid.UUID) -> LedgerGroup:
    res = await db.execute(
        select(LedgerGroup).where(
            and_(LedgerGroup.id == group_id, or_(LedgerGroup.company_id.is_(None), LedgerGroup.company_id == company_id))
        )
    )
    group = res.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


async def _has_children(db: AsyncSession, company_id: uuid.UUID, group_id: uuid.UUID) -> bool:
    """Children visible to THIS company. `has_children` cannot be a stored flag on
    the shared seeded top groups, so it is always computed per-company here."""
    res = await db.execute(
        select(LedgerGroup.id).where(
            and_(
                LedgerGroup.parent_id == group_id,
                or_(LedgerGroup.company_id.is_(None), LedgerGroup.company_id == company_id),
            )
        ).limit(1)
    )
    return res.first() is not None


@router.get("/ledger-groups", response_model=List[LedgerGroupResponse])
async def list_ledger_groups(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await lg.ensure_default_ledger_groups(db)
    await db.commit()
    groups = await lg.load_visible_groups(db, current_user.company_id)
    parent_ids = {g.parent_id for g in groups if g.parent_id}
    natures = lg.build_nature_map(groups)
    return [
        LedgerGroupResponse(
            id=g.id,
            company_id=g.company_id,
            parent_id=g.parent_id,
            name=g.name,
            level=g.level,
            has_children=g.id in parent_ids,
            nature=natures.get(g.id),
        )
        for g in groups
    ]


@router.post("/ledger-groups", response_model=LedgerGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_ledger_group(
    payload: LedgerGroupCreate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    parent = await _visible_group(db, current_user.company_id, payload.parent_id)
    if parent.level >= 2:
        raise HTTPException(status_code=400, detail="Maximum depth reached (group → subgroup → subsubgroup)")

    # Leaf invariant: can't add a child to a group that ledgers are mapped to directly.
    mapped = await db.execute(
        select(func.count()).select_from(TrialBalanceAccount).where(
            and_(
                TrialBalanceAccount.company_id == current_user.company_id,
                TrialBalanceAccount.mapped_group_id == parent.id,
            )
        )
    )
    if mapped.scalar_one() > 0:
        raise HTTPException(
            status_code=409,
            detail="Ledgers are mapped directly to this group. Remap them before adding subgroups.",
        )

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    group = LedgerGroup(
        company_id=current_user.company_id,
        parent_id=parent.id,
        name=name,
        level=parent.level + 1,
        has_children=False,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    index = await lg.resolve_group_index(db, current_user.company_id)
    # A freshly created group is always a leaf.
    return LedgerGroupResponse(
        id=group.id, company_id=group.company_id, parent_id=group.parent_id,
        name=group.name, level=group.level, has_children=False,
        nature=index.natures.get(group.id),
    )


@router.patch("/ledger-groups/{group_id}", response_model=LedgerGroupResponse)
async def rename_ledger_group(
    group_id: uuid.UUID,
    payload: LedgerGroupRename,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    group = await _get_owned_group(db, current_user.company_id, group_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    group.name = name
    await db.commit()
    await db.refresh(group)
    has_children = await _has_children(db, current_user.company_id, group.id)
    index = await lg.resolve_group_index(db, current_user.company_id)
    return LedgerGroupResponse(
        id=group.id, company_id=group.company_id, parent_id=group.parent_id,
        name=group.name, level=group.level, has_children=has_children,
        nature=index.natures.get(group.id),
    )


@router.delete("/ledger-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ledger_group(
    group_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    group = await _get_owned_group(db, current_user.company_id, group_id)
    if await _has_children(db, current_user.company_id, group.id):
        raise HTTPException(status_code=409, detail="Delete subgroups first")

    mapped = await db.execute(
        select(func.count()).select_from(TrialBalanceAccount).where(
            and_(
                TrialBalanceAccount.company_id == current_user.company_id,
                TrialBalanceAccount.mapped_group_id == group.id,
            )
        )
    )
    if mapped.scalar_one() > 0:
        raise HTTPException(status_code=409, detail="Ledgers are mapped to this group. Remap them first.")

    await db.delete(group)
    await db.commit()
    return None


# --- Ledger mapping (per engagement) ---

async def _require_leaf_group(db: AsyncSession, company_id: uuid.UUID, group_id: uuid.UUID) -> LedgerGroup:
    group = await _visible_group(db, company_id, group_id)
    if await _has_children(db, company_id, group.id):
        raise HTTPException(
            status_code=400,
            detail="Select a leaf group — this group has subgroups, choose one of them.",
        )
    return group


@router.post("/engagements/{engagement_id}/ledgers/{ledger_id}/map", response_model=TrialBalanceAccountResponse)
async def map_ledger(
    engagement_id: uuid.UUID,
    ledger_id: uuid.UUID,
    payload: MapLedgerRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    group = await _require_leaf_group(db, current_user.company_id, payload.group_id)

    res = await db.execute(
        select(TrialBalanceAccount).where(
            and_(TrialBalanceAccount.id == ledger_id, TrialBalanceAccount.engagement_id == engagement_id)
        )
    )
    ledger = res.scalar_one_or_none()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")

    ledger.mapped_group_id = group.id
    await db.flush()
    await tbq.recanonicalize(db, engagement_id, current_user.company_id, ledger_ids=[ledger.id])
    await db.commit()
    refreshed = await tbq.load_engagement_figures(db, current_user.company_id, engagement_id)
    return next(a for a in refreshed.accounts if a.id == ledger.id)


@router.post("/engagements/{engagement_id}/ledgers/bulk-map")
async def bulk_map_ledgers(
    engagement_id: uuid.UUID,
    payload: BulkMapRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    group = await _require_leaf_group(db, current_user.company_id, payload.group_id)
    if not payload.ledger_ids:
        return {"updated": 0}
    result = await db.execute(
        update(TrialBalanceAccount)
        .where(
            and_(
                TrialBalanceAccount.engagement_id == engagement_id,
                TrialBalanceAccount.id.in_(payload.ledger_ids),
            )
        )
        .values(mapped_group_id=group.id)
    )
    await db.flush()
    await tbq.recanonicalize(
        db, engagement_id, current_user.company_id, ledger_ids=payload.ledger_ids
    )
    await db.commit()
    return {"updated": result.rowcount}


@router.post("/engagements/{engagement_id}/ledgers/unmap")
async def unmap_ledgers(
    engagement_id: uuid.UUID,
    payload: UnmapRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    if not payload.ledger_ids:
        return {"updated": 0}
    result = await db.execute(
        update(TrialBalanceAccount)
        .where(
            and_(
                TrialBalanceAccount.engagement_id == engagement_id,
                TrialBalanceAccount.id.in_(payload.ledger_ids),
            )
        )
        .values(mapped_group_id=None)
    )
    await db.flush()
    await tbq.recanonicalize(
        db, engagement_id, current_user.company_id, ledger_ids=payload.ledger_ids
    )
    await db.commit()
    return {"updated": result.rowcount}


@router.get(
    "/engagements/{engagement_id}/mapping-sources",
    response_model=List[MappingSourceResponse],
)
async def list_mapping_sources(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List other company engagements that have at least one mapped ledger."""
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    result = await db.execute(
        select(
            AuditEngagement,
            func.count(TrialBalanceAccount.id).label("total_ledger_count"),
            func.count(TrialBalanceAccount.id)
            .filter(TrialBalanceAccount.mapped_group_id.is_not(None))
            .label("mapped_ledger_count"),
        )
        .outerjoin(
            TrialBalanceAccount,
            TrialBalanceAccount.engagement_id == AuditEngagement.id,
        )
        .where(
            and_(
                AuditEngagement.company_id == current_user.company_id,
                AuditEngagement.id != engagement_id,
            )
        )
        .group_by(AuditEngagement.id)
        .having(
            func.count(TrialBalanceAccount.id)
            .filter(TrialBalanceAccount.mapped_group_id.is_not(None))
            > 0
        )
        .order_by(AuditEngagement.created_at.desc())
    )
    return [
        MappingSourceResponse(
            engagement_id=eng.id,
            period_label=eng.period_label,
            status=eng.status,
            total_ledger_count=total_count,
            mapped_ledger_count=mapped_count,
        )
        for eng, total_count, mapped_count in result.all()
    ]


@router.post(
    "/engagements/{engagement_id}/mappings/import",
    response_model=MappingImportResult,
)
async def import_mappings(
    engagement_id: uuid.UUID,
    payload: MappingImportRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Copy ledger mappings from another engagement as a one-time snapshot."""
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    if payload.source_engagement_id == engagement_id:
        raise HTTPException(status_code=400, detail="An engagement cannot import mappings from itself")
    await _get_owned_engagement(db, current_user.company_id, payload.source_engagement_id)

    target_result = await db.execute(
        select(TrialBalanceAccount)
        .where(TrialBalanceAccount.engagement_id == engagement_id)
        .order_by(TrialBalanceAccount.created_at, TrialBalanceAccount.id)
        .with_for_update()
    )
    targets = list(target_result.scalars().all())
    if not targets:
        raise HTTPException(
            status_code=409,
            detail="Import a trial balance before importing ledger mappings.",
        )

    source_result = await db.execute(
        select(TrialBalanceAccount)
        .where(
            and_(
                TrialBalanceAccount.engagement_id == payload.source_engagement_id,
                TrialBalanceAccount.mapped_group_id.is_not(None),
            )
        )
        .order_by(TrialBalanceAccount.created_at, TrialBalanceAccount.id)
        .with_for_update()
    )
    sources = list(source_result.scalars().all())
    if not sources:
        raise HTTPException(
            status_code=409,
            detail="The source engagement has no mapped ledgers.",
        )

    source_rows = [
        mapping_import.LedgerForMapping(
            id=source.id,
            ledger_code=source.ledger_code,
            ledger_name=source.ledger_name,
            mapped_group_id=source.mapped_group_id,
            order=index,
        )
        for index, source in enumerate(sources)
    ]
    target_rows = [
        mapping_import.LedgerForMapping(
            id=target.id,
            ledger_code=target.ledger_code,
            ledger_name=target.ledger_name,
            mapped_group_id=target.mapped_group_id,
            order=index,
        )
        for index, target in enumerate(targets)
    ]
    plan = mapping_import.plan_mapping_import(source_rows, target_rows)
    target_by_id = {target.id: target for target in targets}

    if len(plan.assignments) > len(sources):
        raise HTTPException(status_code=500, detail="Mapping import cardinality check failed")
    if len({item.source_id for item in plan.assignments}) != len(plan.assignments):
        raise HTTPException(status_code=500, detail="Mapping import reused a source ledger")
    if len({item.target_id for item in plan.assignments}) != len(plan.assignments):
        raise HTTPException(status_code=500, detail="Mapping import reused a target ledger")

    updated_count = 0
    already_correct_count = 0
    preserved_existing_count = 0

    for assignment in plan.assignments:
        target = target_by_id[assignment.target_id]
        if target.mapped_group_id is not None and not payload.overwrite_existing:
            preserved_existing_count += 1
            continue
        if target.mapped_group_id == assignment.group_id:
            already_correct_count += 1
        else:
            target.mapped_group_id = assignment.group_id
            updated_count += 1

    issues = []
    for issue in plan.issues:
        target = target_by_id[issue.target_id]
        issues.append(MappingImportIssue(
            target_ledger_id=target.id,
            ledger_code=target.ledger_code,
            ledger_name=target.ledger_name,
            reason=issue.reason,
        ))

    await db.flush()
    # This is a mapping write path too, so the canonical figures of a
    # magnitude-convention trial balance have to be re-derived here as well.
    await tbq.recanonicalize(db, engagement_id, current_user.company_id)
    await db.commit()
    return MappingImportResult(
        total_target_ledgers=len(targets),
        source_mapped_count=len(sources),
        assigned_count=len(plan.assignments),
        updated_count=updated_count,
        already_correct_count=already_correct_count,
        preserved_existing_count=preserved_existing_count,
        unused_source_count=len(plan.unused_source_ids),
        unresolved_count=len(plan.issues),
        issues=issues,
    )


# --- Engagements ---

@router.post("/engagements", response_model=AuditEngagementResponse, status_code=status.HTTP_201_CREATED)
async def create_engagement(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    engagement: AuditEngagementCreate
):
    eng = AuditEngagement(
        company_id=current_user.company_id,
        period_label=engagement.period_label,
        status=EngagementStatus.draft,
        created_by=current_user.id
    )
    db.add(eng)
    await db.commit()
    await db.refresh(eng)
    return await _hydrate_auditors(db, eng)


@router.get("/engagements", response_model=List[AuditEngagementResponse])
async def list_engagements(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(AuditEngagement)
        .where(AuditEngagement.company_id == current_user.company_id)
        .order_by(AuditEngagement.created_at.desc())
    )
    engagements = list(result.scalars().all())
    for eng in engagements:
        await _hydrate_auditors(db, eng)
    return engagements


@router.get("/engagements/{engagement_id}", response_model=AuditEngagementResponse)
async def get_engagement(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    return await _hydrate_auditors(db, eng)


@router.patch("/engagements/{engagement_id}/close", response_model=AuditEngagementResponse)
async def close_engagement(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)

    eng.status = EngagementStatus.closed

    # Revoke all grants and drop any unaccepted pending invites.
    await db.execute(
        update(AuditorEngagementGrant)
        .where(AuditorEngagementGrant.engagement_id == engagement_id)
        .values(status=GrantStatus.revoked)
    )
    await db.execute(
        delete(PendingAuditorInvite).where(PendingAuditorInvite.engagement_id == engagement_id)
    )

    revoked_ids_res = await db.execute(
        select(AuditorEngagementGrant.auditor_id).where(
            and_(AuditorEngagementGrant.engagement_id == engagement_id,
                 AuditorEngagementGrant.status == GrantStatus.revoked)
        )
    )
    await log_activity(
        db, current_user.company_id, current_user.id,
        "engagement.closed", "audit_engagement", eng.id,
        metadata_={"revoked_auditor_ids": [str(a) for a in revoked_ids_res.scalars().all()]},
        actor_type=ActorType.company_user, engagement_id=eng.id,
    )

    await db.commit()
    await db.refresh(eng)
    return await _hydrate_auditors(db, eng)


@router.delete("/engagements/{engagement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_engagement(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Hard-delete an engagement and everything under it (cascade). Allowed only
    while draft/invited (before real audit work), or closed (cleanup)."""
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    if eng.status == EngagementStatus.active:
        raise HTTPException(
            status_code=409,
            detail="An active engagement cannot be deleted — close it first.",
        )
    # These children reference the engagement without an ON DELETE CASCADE FK, so
    # remove them explicitly first (their own children — entry lines, query
    # messages — cascade via their FKs). Trial-balance accounts, auditor grants and
    # pending invites do have cascade and are handled by deleting the engagement.
    await db.execute(delete(AuditEntry).where(AuditEntry.engagement_id == engagement_id))
    await db.execute(delete(Query).where(Query.engagement_id == engagement_id))
    await db.execute(delete(RequirementRequest).where(RequirementRequest.engagement_id == engagement_id))
    await db.delete(eng)
    await db.commit()
    return None


@router.post("/engagements/{engagement_id}/auditors/invite", response_model=AuditEngagementResponse)
async def invite_auditor(
    engagement_id: uuid.UUID,
    invite: AuditorInviteCreate,
    current_user: Annotated[CompanyUser, Depends(require_manager_or_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Invite one auditor by email without disturbing other auditors. Registered
    emails get a grant (revoked grants are resurrected); unknown emails get a
    pending invite that auto-converts on registration."""
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    if eng.status == EngagementStatus.closed:
        raise HTTPException(status_code=409, detail="Cannot invite on a closed engagement")

    try:
        perms = normalize_area_permissions(invite.area_permissions)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    email = invite.email.strip().lower()

    aud_res = await db.execute(select(Auditor).where(func.lower(Auditor.email) == email))
    auditor = aud_res.scalar_one_or_none()

    if auditor:
        g_res = await db.execute(
            select(AuditorEngagementGrant).where(
                and_(
                    AuditorEngagementGrant.auditor_id == auditor.id,
                    AuditorEngagementGrant.engagement_id == engagement_id,
                )
            )
        )
        grant = g_res.scalar_one_or_none()
        if grant and grant.status != GrantStatus.revoked:
            raise HTTPException(status_code=400, detail="Auditor is already invited to this engagement")
        if grant:  # resurrect the revoked row — keeps uq_grant_auditor_engagement intact
            grant.status = GrantStatus.invited
            grant.invited_at = datetime.now(timezone.utc)
            grant.accepted_at = None
            grant.area_permissions = perms
        else:
            db.add(AuditorEngagementGrant(
                auditor_id=auditor.id, engagement_id=engagement_id,
                status=GrantStatus.invited, area_permissions=perms,
            ))
    else:
        pend_res = await db.execute(
            select(PendingAuditorInvite).where(
                and_(
                    PendingAuditorInvite.engagement_id == engagement_id,
                    func.lower(PendingAuditorInvite.email) == email,
                )
            )
        )
        if pend_res.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="An invite for this email is already pending")
        db.add(PendingAuditorInvite(engagement_id=engagement_id, email=email))

    await log_activity(
        db, current_user.company_id, current_user.id,
        "auditor.invited", "audit_engagement", eng.id,
        metadata_={"email": email}, actor_type=ActorType.company_user,
        engagement_id=eng.id,
    )

    if eng.status == EngagementStatus.draft:
        eng.status = EngagementStatus.invited

    await db.commit()
    await db.refresh(eng)
    return await _hydrate_auditors(db, eng)


@router.get("/engagements/{engagement_id}/auditors", response_model=List[EngagementAuditorResponse])
async def list_engagement_auditors(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    return await _list_auditors(db, eng.id)


@router.patch("/engagements/{engagement_id}/auditors/{auditor_id}", response_model=EngagementAuditorResponse)
async def update_auditor_access(
    engagement_id: uuid.UUID,
    auditor_id: uuid.UUID,
    body: AuditorPermissionsUpdate,
    current_user: Annotated[CompanyUser, Depends(require_manager_or_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    try:
        perms = normalize_area_permissions(body.area_permissions)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    g_res = await db.execute(
        select(AuditorEngagementGrant).where(
            and_(
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.engagement_id == engagement_id,
                AuditorEngagementGrant.status != GrantStatus.revoked,
            )
        )
    )
    grant = g_res.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=404, detail="No active grant for this auditor on this engagement")

    grant.area_permissions = perms
    await log_activity(
        db, current_user.company_id, current_user.id,
        "auditor.permissions_updated", "auditor_engagement_grant", grant.id,
        metadata_={"area_permissions": perms},
        actor_type=ActorType.company_user, engagement_id=eng.id,
    )
    await db.commit()

    aud_res = await db.execute(select(Auditor).where(Auditor.id == auditor_id))
    auditor = aud_res.scalar_one()
    return {
        "auditor_id": auditor.id, "name": auditor.name, "email": auditor.email,
        "status": grant.status.value, "area_permissions": grant.area_permissions,
        "invited_at": grant.invited_at, "accepted_at": grant.accepted_at,
    }


@router.delete("/engagements/{engagement_id}/auditors/{auditor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_engagement_auditor(
    engagement_id: uuid.UUID,
    auditor_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_manager_or_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    g_res = await db.execute(
        select(AuditorEngagementGrant).where(
            and_(
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.engagement_id == engagement_id,
                AuditorEngagementGrant.status != GrantStatus.revoked,
            )
        )
    )
    grant = g_res.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=404, detail="No active grant for this auditor on this engagement")

    grant.status = GrantStatus.revoked
    await log_activity(
        db, current_user.company_id, current_user.id,
        "auditor.access_revoked", "auditor_engagement_grant", grant.id,
        actor_type=ActorType.company_user, engagement_id=eng.id,
    )
    await db.commit()
    return None


@router.get("/engagements/{engagement_id}/auditors/{auditor_id}/activity", response_model=List[ActivityEventResponse])
async def get_auditor_activity(
    engagement_id: uuid.UUID,
    auditor_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
):
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    res = await db.execute(
        select(ActivityLog)
        .where(
            and_(
                ActivityLog.company_id == current_user.company_id,
                ActivityLog.engagement_id == engagement_id,
                ActivityLog.actor_type == ActorType.auditor,
                ActivityLog.actor_id == auditor_id,
            )
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": r.id, "action": r.action, "entity_type": r.entity_type,
            "entity_id": r.entity_id, "metadata": r.metadata_, "created_at": r.created_at,
        }
        for r in res.scalars().all()
    ]


# --- Entries (Approval) ---

class EntryApproval(BaseModel):
    status: AuditEntryStatus # approved or rejected


@router.patch("/entries/{entry_id}/approve", response_model=AuditEntryResponse)
async def approve_reject_entry(
    entry_id: uuid.UUID,
    approval: EntryApproval,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # Verify the entry belongs to an engagement owned by this company
    result = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines).selectinload(AuditEntryLine.ledger))
        .join(AuditEngagement, AuditEngagement.id == AuditEntry.engagement_id)
        .where(and_(AuditEntry.id == entry_id, AuditEngagement.company_id == current_user.company_id))
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if approval.status not in [AuditEntryStatus.approved, AuditEntryStatus.rejected]:
        raise HTTPException(status_code=400, detail="Invalid status")

    entry.status = approval.status
    await db.commit()
    # Re-select with lines + ledger eager-loaded for the response.
    result = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines).selectinload(AuditEntryLine.ledger))
        .where(AuditEntry.id == entry_id)
    )
    entry = result.scalar_one()
    await attach_actor_names(db, [entry], "created_by", "created_by_name")
    return entry


@router.get("/engagements/{engagement_id}/entries", response_model=List[AuditEntryResponse])
async def list_entries(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    result = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines).selectinload(AuditEntryLine.ledger))
        .where(AuditEntry.engagement_id == engagement_id)
        .order_by(AuditEntry.created_at.desc())
    )
    entries = result.scalars().all()
    await attach_actor_names(db, entries, "created_by", "created_by_name")
    return entries


# --- Requirements ---

@router.get("/engagements/{engagement_id}/requirement-requests", response_model=List[RequirementRequestResponse])
async def list_requirements(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # check engagement ownership
    result = await db.execute(select(AuditEngagement).where(and_(AuditEngagement.id == engagement_id, AuditEngagement.company_id == current_user.company_id)))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")

    req_list = (await db.execute(
        select(RequirementRequest).where(RequirementRequest.engagement_id == engagement_id)
        .order_by(RequirementRequest.seq_number.nulls_first(), RequirementRequest.created_at)
    )).scalars().all()
    return await enrich_requirements(db, engagement_id, req_list)


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
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    text_answer: Annotated[Optional[str], Form()] = None,
    document_ids: Annotated[Optional[List[uuid.UUID]], Form()] = None,
    files: Annotated[Optional[List[UploadFile]], File()] = None,
):
    req = await _owned_requirement(db, current_user, engagement_id, req_id)
    if req.status == RequestStatus.closed:
        raise HTTPException(status_code=400, detail="This requirement is closed. Ask the auditor to reopen it.")
    text = (text_answer or "").strip() or None
    docs, ups = document_ids or [], files or []
    if not text and not docs and not ups:
        raise HTTPException(status_code=422, detail="Provide an answer, attach a document, or upload a file")

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
    return (await enrich_requirements(db, engagement_id, [req]))[0]


# --- Queries ---

@router.get("/engagements/{engagement_id}/queries", response_model=List[QueryResponse])
async def list_queries(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(AuditEngagement).where(and_(AuditEngagement.id == engagement_id, AuditEngagement.company_id == current_user.company_id)))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    queries = await db.execute(select(Query).options(selectinload(Query.messages)).where(Query.engagement_id == engagement_id))
    query_list = queries.scalars().all()
    for q in query_list:
        await attach_sender_names(db, q.messages)
    return query_list


@router.post("/engagements/{engagement_id}/queries/{query_id}/messages", response_model=QueryMessageResponse)
async def add_query_message(
    engagement_id: uuid.UUID,
    query_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    text: Annotated[str, Form(...)],
    attached_document_id: Annotated[Optional[uuid.UUID], Form()] = None,
    file: Annotated[Optional[UploadFile], File()] = None,
):
    result = await db.execute(select(AuditEngagement).where(and_(AuditEngagement.id == engagement_id, AuditEngagement.company_id == current_user.company_id)))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    q_res = await db.execute(select(Query).where(and_(Query.id == query_id, Query.engagement_id == engagement_id)))
    query = q_res.scalar_one_or_none()
    if not query or query.status == QueryStatus.closed:
        raise HTTPException(status_code=400, detail="Query not found or closed")
        
    final_attached_document_id = None
    if attached_document_id:
        from app.models.docvault import Document, DocumentAccessOverride, PrincipalType
        doc_res = await db.execute(select(Document).where(and_(Document.id == attached_document_id, Document.company_id == current_user.company_id)))
        if not doc_res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Document not found")
            
        grant = DocumentAccessOverride(
            document_id=attached_document_id,
            principal_type=PrincipalType.auditor,
            principal_id=query.opened_by,
            permission_level="read"
        )
        db.add(grant)
        final_attached_document_id = attached_document_id
    elif file:
        from app.services import document_access as doc_access
        doc = await doc_access.create_attachment_document(
            db, company_id=current_user.company_id, file=file, created_by=current_user.id, grant_auditor_id=query.opened_by
        )
        final_attached_document_id = doc.id
        
    message = QueryMessage(
        query_id=query_id,
        sender_type=SenderType.company_user,
        sender_id=current_user.id,
        text=text,
        attached_document_id=final_attached_document_id
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


def _round2(v: float) -> float:
    return round(float(v), 2)


async def _compute_report(db: AsyncSession, company_id: uuid.UUID, eng: AuditEngagement) -> ReportPreviewResponse:
    """Build the Balance Sheet + P&L + entries summary for an engagement.

    All the accounting is `trial_balance.summarize`, shared with the trial-balance
    endpoint, so the report and the grid cannot report different totals. There is no
    abs() and no branching on group names here: nature comes from the persisted
    `LedgerGroup.nature`, and a contra balance simply arrives with the opposite sign
    and subtracts.
    """
    figures = await tbq.load_engagement_figures(db, company_id, eng.id)
    summary = figures.summary
    equity_before_profit = summary.equity - summary.net_profit
    other_liabilities = summary.liabilities - equity_before_profit

    # The Balance Sheet's balancing figure, as a real renderable row. Without it the
    # Liabilities section total is `liabilities` while the footer says
    # `liabilities + net_profit`, so the statement visibly does not balance.
    rendered = [*figures.figures, tb.make_profit_figure(summary.net_profit)]

    lines = [
        ReportLine(
            ledger_id=f.ledger_id,
            ledger_name=f.ledger_name,
            ledger_code=f.ledger_code,
            top_group=f.top_group,
            group_path=f.group_path,
            nature=f.nature,
            # Presented figures, so closing + adjustment == final on EVERY row --
            # including unmapped ones, whose adjustment used to be silently dropped.
            closing=_round2(f.presented_closing),
            adjustment=_round2(tb.present(f.adjustment, f.nature)),
            final=_round2(f.presented_final),
            net_debit=_round2(f.net_debit),
            sign_unresolved=f.sign_unresolved,
            is_synthetic=f.is_synthetic,
        )
        for f in rendered
    ]

    entry_summaries = [
        ReportEntrySummary(
            id=e.id,
            code=e.code,
            description=e.description,
            total=_round2(sum(float(l.amount) for l in e.lines if l.side == EntryLineSide.debit)),
            line_count=len(e.lines),
        )
        for e in figures.approved_entries
    ]

    warnings = tbq.view_warnings(figures.figures, summary, eng.tb_sign_convention)
    # An approved double entry with one leg on an unmapped ledger contributes only its
    # mapped leg to the totals, which breaks the balance check for a reason no generic
    # "some ledgers are unmapped" banner explains. Name it.
    unmapped_ids = {f.ledger_id for f in figures.figures if f.top_group is None}
    for entry in figures.approved_entries:
        touched = sorted({
            f.ledger_name for f in figures.figures
            if f.ledger_id in unmapped_ids
            and any(l.ledger_id == f.ledger_id for l in entry.lines)
        })
        for name in touched:
            warnings.append(
                f"Approved entry {entry.code or entry.description} adjusts unmapped "
                f"ledger '{name}' — the statements cannot balance until it is mapped."
            )

    return ReportPreviewResponse(
        period_label=eng.period_label,
        lines=lines,
        totals=ReportTotals(
            assets=_round2(summary.assets),
            liabilities=_round2(summary.liabilities),
            income=_round2(summary.income),
            expenditure=_round2(summary.expenditure),
            equity=_round2(summary.equity),
            other_liabilities=_round2(other_liabilities),
            groups=tbq.totals_response(summary).groups,
        ),
        net_profit=_round2(summary.net_profit),
        balance_check=ReportBalanceCheck(
            assets=_round2(summary.assets),
            liabilities_plus_equity=_round2(summary.liabilities_plus_equity),
            difference=_round2(summary.difference),
            balanced=summary.balanced,
            statement_ready=summary.statement_ready,
            unmapped_net_debit=_round2(summary.unmapped_net_debit),
            difference_including_unmapped=_round2(summary.difference_including_unmapped),
        ),
        entries=ReportEntriesBlock(
            approved=entry_summaries,
            approved_count=len(figures.approved_entries),
            proposed_count=figures.proposed_count,
        ),
        unmapped_count=summary.unmapped_count,
        unresolved_nature_count=summary.unresolved_nature_count,
        sign_convention=eng.tb_sign_convention,
        warnings=warnings,
    )


from fastapi.responses import Response, StreamingResponse
from app.models.company import Company
from app.services.reporting.auditease_reports import (
    AUDITEASE_BUILDERS,
    build_all_auditease_reports,
    build_balance_sheet,
    get_auditease_report_builder,
)
from app.services.reporting.pdf import render_html, render_pdf, render_pack_pdf, render_pack_html
from app.services.reporting.workbook import write_document, write_workbook
from app.services.reporting.vault import archive_report


async def _get_engagement_reporting_context(db: AsyncSession, company_id: uuid.UUID, engagement_id: uuid.UUID):
    eng = await _get_owned_engagement(db, company_id, engagement_id)
    company = await db.get(Company, company_id)
    company_name = (company.legal_name if company else None) or (company.name if company else None) or "Company"
    figures = await tbq.load_engagement_figures(db, company_id, eng.id)
    warnings = tbq.view_warnings(figures.figures, figures.summary, eng.tb_sign_convention)
    return eng, company_name, figures, warnings


@router.get("/engagements/{engagement_id}/reports/preview", response_model=ReportPreviewResponse)
async def preview_report(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    return await _compute_report(db, current_user.company_id, eng)


@router.get("/engagements/{engagement_id}/reports/{report_key}/preview-html")
async def preview_report_html(
    engagement_id: uuid.UUID,
    report_key: str,
    units: str = "absolute",
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    eng, company_name, figures, warnings = await _get_engagement_reporting_context(db, current_user.company_id, engagement_id)
    if report_key not in AUDITEASE_BUILDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report '{report_key}' not found")
    
    builder = get_auditease_report_builder(report_key)
    if report_key == "adjusting_entries":
        doc = builder(figures.approved_entries, company_name, eng.period_label, units, warnings)
    elif report_key in ("balance_sheet", "profit_and_loss", "notes_to_accounts", "trial_balance_detailed", "trial_balance_summary", "extended_trial_balance"):
        doc = builder(figures.figures, figures.summary, company_name, eng.period_label, units, warnings)
    elif report_key == "ledger_mapping":
        doc = builder(figures.figures, company_name, eng.period_label, units, warnings)
    else:  # exceptions
        doc = builder(figures.summary, figures.figures, company_name, eng.period_label, units, warnings)

    html_str = render_html(doc)
    return {"html": html_str, "title": doc.title, "units": doc.units}


@router.get("/engagements/{engagement_id}/reports/{report_key}/export")
async def export_report(
    engagement_id: uuid.UUID,
    report_key: str,
    format: str = "xlsx",
    units: str = "absolute",
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    eng, company_name, figures, warnings = await _get_engagement_reporting_context(db, current_user.company_id, engagement_id)
    if report_key not in AUDITEASE_BUILDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report '{report_key}' not found")
    
    builder = get_auditease_report_builder(report_key)
    if report_key == "adjusting_entries":
        doc = builder(figures.approved_entries, company_name, eng.period_label, units, warnings)
    elif report_key in ("balance_sheet", "profit_and_loss", "notes_to_accounts", "trial_balance_detailed", "trial_balance_summary", "extended_trial_balance"):
        doc = builder(figures.figures, figures.summary, company_name, eng.period_label, units, warnings)
    elif report_key == "ledger_mapping":
        doc = builder(figures.figures, company_name, eng.period_label, units, warnings)
    else:  # exceptions
        doc = builder(figures.summary, figures.figures, company_name, eng.period_label, units, warnings)

    safe_period = eng.period_label.replace(" ", "_").replace("/", "-")
    if format == "pdf":
        pdf_bytes = render_pdf(doc)
        filename = f"{report_key}_{safe_period}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    
    # XLSX default
    stream = write_document(doc)
    filename = f"{report_key}_{safe_period}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/engagements/{engagement_id}/reports/pack")
async def export_report_pack(
    engagement_id: uuid.UUID,
    format: str = "xlsx",
    units: str = "absolute",
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    eng, company_name, figures, warnings = await _get_engagement_reporting_context(db, current_user.company_id, engagement_id)
    sheets = build_all_auditease_reports(
        figures=figures.figures,
        summary=figures.summary,
        approved_entries=figures.approved_entries,
        company_name=company_name,
        period_label=eng.period_label,
        units=units,
        warnings=warnings,
    )

    safe_period = eng.period_label.replace(" ", "_").replace("/", "-")
    if format == "pdf":
        docs = [d for _, d in sheets]
        pdf_bytes = render_pack_pdf(docs)
        filename = f"Audited_Financial_Statements_Pack_{safe_period}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # XLSX default
    stream = write_workbook(sheets)
    filename = f"Audited_Financial_Statements_Pack_{safe_period}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/engagements/{engagement_id}/reports/archive")
async def archive_engagement_report(
    engagement_id: uuid.UUID,
    report_key: str = "pack",
    format: str = "pdf",
    units: str = "absolute",
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    eng, company_name, figures, warnings = await _get_engagement_reporting_context(db, current_user.company_id, engagement_id)
    safe_period = eng.period_label.replace(" ", "_").replace("/", "-")

    if report_key == "pack":
        sheets = build_all_auditease_reports(
            figures=figures.figures,
            summary=figures.summary,
            approved_entries=figures.approved_entries,
            company_name=company_name,
            period_label=eng.period_label,
            units=units,
            warnings=warnings,
        )
        if format == "pdf":
            docs = [d for _, d in sheets]
            content = render_pack_pdf(docs)
            filename = f"Audited_Financial_Statements_Pack_{safe_period}.pdf"
            mime_type = "application/pdf"
        else:
            stream = write_workbook(sheets)
            content = stream.getvalue()
            filename = f"Audited_Financial_Statements_Pack_{safe_period}.xlsx"
            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        if report_key not in AUDITEASE_BUILDERS:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report '{report_key}' not found")
        builder = get_auditease_report_builder(report_key)
        if report_key == "adjusting_entries":
            doc = builder(figures.approved_entries, company_name, eng.period_label, units, warnings)
        elif report_key in ("balance_sheet", "profit_and_loss", "notes_to_accounts", "trial_balance_detailed", "trial_balance_summary", "extended_trial_balance"):
            doc = builder(figures.figures, figures.summary, company_name, eng.period_label, units, warnings)
        elif report_key == "ledger_mapping":
            doc = builder(figures.figures, company_name, eng.period_label, units, warnings)
        else:  # exceptions
            doc = builder(figures.summary, figures.figures, company_name, eng.period_label, units, warnings)

        if format == "pdf":
            content = render_pdf(doc)
            filename = f"{report_key}_{safe_period}.pdf"
            mime_type = "application/pdf"
        else:
            stream = write_document(doc)
            content = stream.getvalue()
            filename = f"{report_key}_{safe_period}.xlsx"
            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    doc = await archive_report(
        db=db,
        company_id=eng.company_id,
        user_id=current_user.id,
        bucket_name="Final Reports",
        filename=filename,
        content=content,
        mime_type=mime_type,
    )
    return {"id": str(doc.id), "url": f"/api/v1/docvault/documents/{doc.id}/download"}


@router.post("/engagements/{engagement_id}/reports/generate")
async def generate_report(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng, company_name, figures, warnings = await _get_engagement_reporting_context(db, current_user.company_id, engagement_id)
    sheets = build_all_auditease_reports(
        figures=figures.figures,
        summary=figures.summary,
        approved_entries=figures.approved_entries,
        company_name=company_name,
        period_label=eng.period_label,
        units="absolute",
        warnings=warnings,
    )
    docs = [d for _, d in sheets]
    html = render_pack_html(docs, pack_title=f"Annual Report - {eng.period_label}")
    
    filename = f"Annual Report - {eng.period_label}.html"
    doc = await archive_report(
        db=db,
        company_id=eng.company_id,
        user_id=current_user.id,
        bucket_name="Final Reports",
        filename=filename,
        content=html.encode("utf-8"),
        mime_type="text/html",
    )
    
    return {"id": str(doc.id), "url": f"/api/v1/docvault/documents/{doc.id}/download"}


@router.get("/engagements/{engagement_id}/auditors/{auditor_id}/activity-report")
async def export_auditor_activity_report(
    engagement_id: uuid.UUID,
    auditor_id: uuid.UUID,
    format: str = "xlsx",
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    from fastapi.responses import StreamingResponse

    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)

    aud_res = await db.execute(select(Auditor).where(Auditor.id == auditor_id))
    auditor = aud_res.scalar_one_or_none()
    if not auditor:
        raise HTTPException(status_code=404, detail="Auditor not found")

    ev_res = await db.execute(
        select(ActivityLog)
        .where(
            and_(
                ActivityLog.company_id == current_user.company_id,
                ActivityLog.engagement_id == engagement_id,
                ActivityLog.actor_type == ActorType.auditor,
                ActivityLog.actor_id == auditor_id,
            )
        )
        .order_by(ActivityLog.created_at.asc())
    )
    events = [
        {"action": r.action, "entity_type": r.entity_type,
         "metadata": r.metadata_, "created_at": r.created_at}
        for r in ev_res.scalars().all()
    ]

    from app.services.reporting.activity_report import build_auditor_activity_report

    company = await db.get(Company, current_user.company_id)
    company_name = ((company.legal_name if company else None) or (company.name if company else None) or "Company")
    doc = build_auditor_activity_report(
        events, auditor.name, auditor.email, company_name, eng.period_label,
    )

    safe_period = eng.period_label.replace(" ", "_").replace("/", "-")
    if format == "pdf":
        pdf_bytes = render_pdf(doc)
        filename = f"auditor_activity_{safe_period}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    stream = write_document(doc)
    filename = f"auditor_activity_{safe_period}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

