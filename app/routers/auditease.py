import json
import uuid
from typing import Annotated, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, and_, or_, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_company_user
from app.models.company import CompanyUser
from app.models.auditor import Auditor
from app.models.auditease import (
    TrialBalanceAccount, LedgerGroup, AuditEngagement, AuditorEngagementGrant,
    PendingAuditorInvite, AuditEntry, AuditEntryLine, RequirementRequest, Query, QueryMessage,
    EngagementStatus, GrantStatus, AuditEntryStatus, EntryLineSide, RequestStatus, QueryStatus, SenderType
)
from app.schemas.auditease import (
    TrialBalanceAccountResponse, LedgerGroupResponse, LedgerGroupCreate, LedgerGroupRename,
    MapLedgerRequest, BulkMapRequest, UnmapRequest, AuditEngagementCreate,
    AuditEngagementResponse, AuditEntryResponse, RequirementRequestResponse,
    QueryResponse, QueryMessageResponse, QueryMessageCreate,
    TBColumnMap, TBInspectResponse, TBImportResult,
    ReportLine, ReportTotals, ReportBalanceCheck, ReportEntrySummary,
    ReportEntriesBlock, ReportPreviewResponse,
)
from app.config import get_settings
from app.services import import_service
from app.services import ledger_groups as lg

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


async def _hydrate_auditor_info(db: AsyncSession, eng: AuditEngagement) -> AuditEngagement:
    """Attach auditor_email + auditor_grant_status (single-auditor model) for the response."""
    grant_res = await db.execute(
        select(AuditorEngagementGrant, Auditor.email)
        .join(Auditor, Auditor.id == AuditorEngagementGrant.auditor_id)
        .where(
            and_(
                AuditorEngagementGrant.engagement_id == eng.id,
                AuditorEngagementGrant.status != GrantStatus.revoked,
            )
        )
        .order_by(AuditorEngagementGrant.invited_at.desc())
    )
    row = grant_res.first()
    if row:
        grant, email = row
        eng.auditor_email = email
        eng.auditor_grant_status = grant.status.value
        return eng
    pend_res = await db.execute(
        select(PendingAuditorInvite)
        .where(PendingAuditorInvite.engagement_id == eng.id)
        .order_by(PendingAuditorInvite.created_at.desc())
    )
    pend = pend_res.scalars().first()
    if pend:
        eng.auditor_email = pend.email
        eng.auditor_grant_status = "pending"
    return eng


# --- Trial Balance (per engagement, server-side file import) ---

@router.post("/engagements/{engagement_id}/trial-balance/inspect", response_model=TBInspectResponse)
async def inspect_trial_balance(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Step 1: return every sheet's headers + preview rows so the client can map columns."""
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    content = await file.read()
    try:
        sheets = import_service.inspect_spreadsheet(file.filename or "", content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"sheets": sheets}


@router.post("/engagements/{engagement_id}/trial-balance/import", response_model=TBImportResult)
async def import_trial_balance(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    column_map: str = Form(...),
    sheet: Optional[str] = Form(None),
):
    """Step 2: parse `sheet` with `column_map` (JSON) and replace this engagement's TB."""
    await _get_owned_engagement(db, current_user.company_id, engagement_id)

    # Guard: re-import is blocked once audit entries reference this TB.
    entry_count = await db.execute(
        select(func.count()).select_from(AuditEntry).where(AuditEntry.engagement_id == engagement_id)
    )
    if entry_count.scalar_one() > 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot re-import: audit entries already exist for this engagement.",
        )

    try:
        cmap = TBColumnMap.model_validate_json(column_map)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Invalid column_map: {e.errors()}")

    content = await file.read()
    try:
        valid, errors = import_service.parse_trial_balance(
            file.filename or "", content, sheet, cmap.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Replace-on-reimport: wipe existing rows for this engagement, insert fresh.
    await db.execute(
        delete(TrialBalanceAccount).where(TrialBalanceAccount.engagement_id == engagement_id)
    )

    accounts: List[TrialBalanceAccount] = []
    for rec in valid:
        acc = TrialBalanceAccount(
            company_id=current_user.company_id,
            engagement_id=engagement_id,
            **rec,
        )
        db.add(acc)
        accounts.append(acc)
    await db.flush()
    await db.commit()
    for acc in accounts:
        await db.refresh(acc)

    total_debit = float(sum(float(a.debit) for a in accounts))
    total_credit = float(sum(float(a.credit) for a in accounts))
    # Set mapped_group_path on each account for serialization (freshly imported = no mapping)
    for acc in accounts:
        acc.mapped_group_path = None  # type: ignore[attr-defined]
    return TBImportResult(
        imported=len(accounts),
        skipped=len(errors),
        errors=errors,
        total_debit=total_debit,
        total_credit=total_credit,
        balanced=(round(total_debit, 2) == round(total_credit, 2)),
        accounts=[TrialBalanceAccountResponse.model_validate(a) for a in accounts],
    )


@router.get("/engagements/{engagement_id}/trial-balance", response_model=List[TrialBalanceAccountResponse])
async def get_trial_balance(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    result = await db.execute(
        select(TrialBalanceAccount)
        .where(TrialBalanceAccount.engagement_id == engagement_id)
        .order_by(TrialBalanceAccount.ledger_name)
    )
    accounts = list(result.scalars().all())
    path_map = await lg.resolve_group_paths(db, current_user.company_id)
    return lg.attach_group_paths(accounts, path_map)


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
    return [
        LedgerGroupResponse(
            id=g.id,
            company_id=g.company_id,
            parent_id=g.parent_id,
            name=g.name,
            level=g.level,
            has_children=g.id in parent_ids,
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
    # A freshly created group is always a leaf.
    return LedgerGroupResponse(
        id=group.id, company_id=group.company_id, parent_id=group.parent_id,
        name=group.name, level=group.level, has_children=False,
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
    return LedgerGroupResponse(
        id=group.id, company_id=group.company_id, parent_id=group.parent_id,
        name=group.name, level=group.level, has_children=has_children,
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
    await db.commit()
    await db.refresh(ledger)
    path_map = await lg.resolve_group_paths(db, current_user.company_id)
    return lg.attach_group_paths([ledger], path_map)[0]


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
    await db.commit()
    return {"updated": result.rowcount}


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
    return eng


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
        await _hydrate_auditor_info(db, eng)
    return engagements


@router.get("/engagements/{engagement_id}", response_model=AuditEngagementResponse)
async def get_engagement(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    return await _hydrate_auditor_info(db, eng)


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

    await db.commit()
    await db.refresh(eng)
    return await _hydrate_auditor_info(db, eng)


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


@router.delete("/engagements/{engagement_id}")
async def delete_engagement(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete engagements")

    result = await db.execute(select(AuditEngagement).where(and_(AuditEngagement.id == engagement_id, AuditEngagement.company_id == current_user.company_id)))
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    # Check for approved entries
    entries_res = await db.execute(
        select(AuditEntry).where(and_(AuditEntry.engagement_id == engagement_id, AuditEntry.status == AuditEntryStatus.approved))
    )
    if entries_res.scalars().first():
        raise HTTPException(status_code=400, detail="Cannot delete engagement with approved entries")

    # Hard delete engagement
    # Manually delete related records since ondelete="CASCADE" is missing on some tables
    await db.execute(delete(AuditorEngagementGrant).where(AuditorEngagementGrant.engagement_id == engagement_id))
    
    # Delete related requirement requests
    await db.execute(delete(RequirementRequest).where(RequirementRequest.engagement_id == engagement_id))
    
    # Delete queries and query messages (query messages have ondelete="CASCADE" but let's be safe)
    queries_res = await db.execute(select(Query.id).where(Query.engagement_id == engagement_id))
    query_ids = queries_res.scalars().all()
    if query_ids:
        await db.execute(delete(QueryMessage).where(QueryMessage.query_id.in_(query_ids)))
        await db.execute(delete(Query).where(Query.engagement_id == engagement_id))
        
    # Delete audit entries and their lines (lines have ondelete="CASCADE")
    entries_res = await db.execute(select(AuditEntry.id).where(AuditEntry.engagement_id == engagement_id))
    entry_ids = entries_res.scalars().all()
    if entry_ids:
        await db.execute(delete(AuditEntryLine).where(AuditEntryLine.entry_id.in_(entry_ids)))
        await db.execute(delete(AuditEntry).where(AuditEntry.engagement_id == engagement_id))
        
    await db.delete(eng)
    await db.commit()
    
    return {"message": "Engagement deleted"}


class AuditorInvite(BaseModel):
    email: str


@router.post("/engagements/{engagement_id}/invite-auditor", response_model=AuditEngagementResponse)
async def invite_auditor(
    engagement_id: uuid.UUID,
    invite: AuditorInvite,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Invite one auditor by email. If they already have an account, a grant is
    created; otherwise a pending invite is stored and auto-converts on registration.
    Re-inviting replaces any prior invite (one auditor per engagement)."""
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    if eng.status == EngagementStatus.closed:
        raise HTTPException(status_code=409, detail="Cannot invite on a closed engagement")

    email = invite.email.strip().lower()

    aud_res = await db.execute(select(Auditor).where(func.lower(Auditor.email) == email))
    auditor = aud_res.scalar_one_or_none()

    # Reject an exact duplicate: the same auditor already has an active/pending grant here.
    if auditor:
        dup_res = await db.execute(
            select(AuditorEngagementGrant).where(
                and_(
                    AuditorEngagementGrant.auditor_id == auditor.id,
                    AuditorEngagementGrant.engagement_id == engagement_id,
                    AuditorEngagementGrant.status != GrantStatus.revoked,
                )
            )
        )
        if dup_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Auditor is already invited to this engagement")

    # One auditor per engagement: clear any prior grant/pending before re-inviting.
    await db.execute(
        update(AuditorEngagementGrant)
        .where(AuditorEngagementGrant.engagement_id == engagement_id)
        .values(status=GrantStatus.revoked)
    )
    await db.execute(
        delete(PendingAuditorInvite).where(PendingAuditorInvite.engagement_id == engagement_id)
    )

    if auditor:
        db.add(AuditorEngagementGrant(
            auditor_id=auditor.id,
            engagement_id=engagement_id,
            status=GrantStatus.invited,
        ))
    else:
        db.add(PendingAuditorInvite(engagement_id=engagement_id, email=email))

    # Moving out of draft: the engagement is now awaiting acceptance.
    if eng.status == EngagementStatus.draft:
        eng.status = EngagementStatus.invited

    await db.commit()
    await db.refresh(eng)
    return await _hydrate_auditor_info(db, eng)


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
    return result.scalar_one()


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
    return result.scalars().all()


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
        
    reqs = await db.execute(select(RequirementRequest).where(RequirementRequest.engagement_id == engagement_id))
    return reqs.scalars().all()


class RequirementFulfill(BaseModel):
    document_id: uuid.UUID


@router.patch("/engagements/{engagement_id}/requirement-requests/{req_id}/fulfill", response_model=RequirementRequestResponse)
async def fulfill_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    payload: RequirementFulfill,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # check engagement ownership
    result = await db.execute(select(AuditEngagement).where(and_(AuditEngagement.id == engagement_id, AuditEngagement.company_id == current_user.company_id)))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    # check document ownership
    from app.models.docvault import Document, DocumentAccessOverride, PrincipalType
    doc_res = await db.execute(select(Document).where(and_(Document.id == payload.document_id, Document.company_id == current_user.company_id)))
    if not doc_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Document not found")
        
    req_res = await db.execute(select(RequirementRequest).where(and_(RequirementRequest.id == req_id, RequirementRequest.engagement_id == engagement_id)))
    req = req_res.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement request not found")
        
    req.status = RequestStatus.fulfilled
    req.fulfilled_document_id = payload.document_id
    
    # Grant access to auditor
    grant = DocumentAccessOverride(
        document_id=payload.document_id,
        principal_type=PrincipalType.auditor,
        principal_id=req.raised_by,
        permission_level="read"
    )
    db.add(grant)
    await db.commit()
    await db.refresh(req)
    return req


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
    return queries.scalars().all()


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
    """Build the Balance Sheet + P&L + entries summary for an engagement, applying
    approved audit-entry adjustments. Shared by the preview and generate endpoints so
    the accounting lives in exactly one place."""
    res_acc = await db.execute(
        select(TrialBalanceAccount)
        .where(TrialBalanceAccount.engagement_id == eng.id)
        .order_by(TrialBalanceAccount.ledger_name)
    )
    accounts = list(res_acc.scalars().all())
    path_map = await lg.resolve_group_paths(db, company_id)
    lg.attach_group_paths(accounts, path_map)

    # Approved entries drive the adjustments; proposed ones are only counted.
    res_ent = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines))
        .where(and_(AuditEntry.engagement_id == eng.id, AuditEntry.status == AuditEntryStatus.approved))
        .order_by(AuditEntry.created_at.asc())
    )
    approved_entries = list(res_ent.scalars().all())
    proposed_res = await db.execute(
        select(func.count()).select_from(AuditEntry).where(
            and_(AuditEntry.engagement_id == eng.id, AuditEntry.status == AuditEntryStatus.proposed)
        )
    )
    proposed_count = int(proposed_res.scalar() or 0)

    # Net-debit adjustment per ledger.
    adjustments: dict[uuid.UUID, float] = {}
    for entry in approved_entries:
        for line in entry.lines:
            delta = float(line.amount) if line.side == EntryLineSide.debit else -float(line.amount)
            adjustments[line.ledger_id] = adjustments.get(line.ledger_id, 0.0) + delta

    lines: list[ReportLine] = []
    totals = {"Assets": 0.0, "Liabilities": 0.0, "Income": 0.0, "Expenditure": 0.0}
    unmapped_count = 0
    for acc in accounts:
        top = acc.mapped_group_path[0] if acc.mapped_group_path else None
        adj = adjustments.get(acc.id, 0.0)
        closing = float(acc.closing_balance)
        # Debit-natured groups grow with a net debit; credit-natured shrink.
        if top in ("Assets", "Expenditure"):
            final = closing + adj
        elif top in ("Liabilities", "Income"):
            final = closing - adj
        else:
            final = closing  # unmapped — excluded from statement totals
        if top is None:
            unmapped_count += 1
        else:
            totals[top] += final
        lines.append(ReportLine(
            ledger_id=acc.id,
            ledger_name=acc.ledger_name,
            ledger_code=acc.ledger_code,
            top_group=top,
            group_path=acc.mapped_group_path,
            closing=_round2(closing),
            adjustment=_round2(adj),
            final=_round2(final),
        ))

    net_profit = totals["Income"] - totals["Expenditure"]
    liab_plus_equity = totals["Liabilities"] + net_profit
    difference = totals["Assets"] - liab_plus_equity

    entry_summaries = [
        ReportEntrySummary(
            id=e.id,
            code=e.code,
            description=e.description,
            total=_round2(sum(float(l.amount) for l in e.lines if l.side == EntryLineSide.debit)),
            line_count=len(e.lines),
        )
        for e in approved_entries
    ]

    return ReportPreviewResponse(
        period_label=eng.period_label,
        lines=lines,
        totals=ReportTotals(
            assets=_round2(totals["Assets"]),
            liabilities=_round2(totals["Liabilities"]),
            income=_round2(totals["Income"]),
            expenditure=_round2(totals["Expenditure"]),
        ),
        net_profit=_round2(net_profit),
        balance_check=ReportBalanceCheck(
            assets=_round2(totals["Assets"]),
            liabilities_plus_equity=_round2(liab_plus_equity),
            difference=_round2(difference),
            balanced=abs(difference) < 0.01,
        ),
        entries=ReportEntriesBlock(
            approved=entry_summaries,
            approved_count=len(approved_entries),
            proposed_count=proposed_count,
        ),
        unmapped_count=unmapped_count,
    )


def _report_to_html(report: ReportPreviewResponse) -> str:
    """Render the computed report as a standalone HTML document for docVault."""
    def money(v: float) -> str:
        return f"{v:,.2f}"

    def section(title: str, groups: list[str]) -> str:
        rows = ""
        for line in report.lines:
            if line.top_group not in groups:
                continue
            path = " › ".join(line.group_path) if line.group_path else (line.top_group or "Unmapped")
            rows += (
                f"<tr><td>{line.ledger_name}</td><td>{path}</td>"
                f"<td class='num'>{money(line.closing)}</td>"
                f"<td class='num'>{money(line.adjustment)}</td>"
                f"<td class='num'>{money(line.final)}</td></tr>"
            )
        return (
            f"<h2>{title}</h2>"
            "<table><thead><tr><th>Ledger</th><th>Group</th>"
            "<th class='num'>Closing</th><th class='num'>Adjustment</th>"
            "<th class='num'>Final</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )

    t = report.totals
    bc = report.balance_check
    entries_rows = "".join(
        f"<tr><td>{e.code or '—'}</td><td>{e.description}</td>"
        f"<td class='num'>{money(e.total)}</td><td class='num'>{e.line_count}</td></tr>"
        for e in report.entries.approved
    ) or "<tr><td colspan='4'>No approved adjusting entries.</td></tr>"

    unmapped_note = (
        f"<p class='warn'>{report.unmapped_count} ledger(s) are unmapped and excluded "
        "from these statements.</p>" if report.unmapped_count else ""
    )
    balance_note = (
        "Balanced" if bc.balanced
        else f"Not balanced — difference {money(bc.difference)}"
    )

    return (
        "<html><head><meta charset='utf-8'><style>"
        "body{font-family:Arial,Helvetica,sans-serif;margin:32px;color:#111}"
        "h1{font-size:20px}h2{font-size:16px;margin-top:24px}"
        "table{border-collapse:collapse;width:100%;margin-top:8px;font-size:13px}"
        "th,td{border:1px solid #ccc;padding:6px 8px;text-align:left}"
        ".num{text-align:right;font-variant-numeric:tabular-nums}"
        ".warn{color:#b45309}.total{font-weight:bold}"
        "</style></head><body>"
        f"<h1>Financial Statements — {report.period_label}</h1>"
        f"{unmapped_note}"
        f"{section('Balance Sheet', ['Assets', 'Liabilities'])}"
        f"<p class='total'>Total Assets: {money(t.assets)} &nbsp;|&nbsp; "
        f"Total Liabilities: {money(t.liabilities)} &nbsp;|&nbsp; "
        f"Liabilities + Equity: {money(bc.liabilities_plus_equity)} &nbsp;|&nbsp; {balance_note}</p>"
        # P&L: keep Income and Expenditure in SEPARATE sections. They have opposite
        # accounting natures, so lumping them into one block invites a meaningless
        # abs(Income)+abs(Expenditure) "total"; the net is the explicit difference below.
        f"<h2>Profit &amp; Loss</h2>"
        f"{section('Income', ['Income'])}"
        f"{section('Expenditure', ['Expenditure'])}"
        f"<p class='total'>Total Income: {money(t.income)} &nbsp;|&nbsp; "
        f"Total Expenditure: {money(t.expenditure)} &nbsp;|&nbsp; "
        f"Net {'Profit' if report.net_profit >= 0 else 'Loss'}: {money(abs(report.net_profit))}</p>"
        "<h2>Approved Adjusting Entries</h2>"
        "<table><thead><tr><th>Code</th><th>Description</th>"
        "<th class='num'>Amount</th><th class='num'>Lines</th></tr></thead>"
        f"<tbody>{entries_rows}</tbody></table>"
        "</body></html>"
    )


@router.get("/engagements/{engagement_id}/reports/preview", response_model=ReportPreviewResponse)
async def preview_report(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    return await _compute_report(db, current_user.company_id, eng)


@router.post("/engagements/{engagement_id}/reports/generate")
async def generate_report(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)

    report = await _compute_report(db, current_user.company_id, eng)
    html = _report_to_html(report)
    
    # Create docVault entry
    from app.models.docvault import Bucket, Document, DocumentVersion, DocumentStatus
    from app.routers.docvault import handle_file_upload
    from fastapi import UploadFile
    from io import BytesIO
    
    # Find or create Final Reports bucket
    bucket_res = await db.execute(select(Bucket).where(and_(Bucket.company_id == eng.company_id, Bucket.name == "Final Reports")))
    bucket = bucket_res.scalar_one_or_none()
    if not bucket:
        bucket = Bucket(company_id=eng.company_id, name="Final Reports", created_by=current_user.id)
        db.add(bucket)
        await db.flush()
        
    # Create Document
    doc = Document(
        company_id=eng.company_id,
        bucket_id=bucket.id,
        title=f"Annual Report - {eng.period_label}.html",
        status=DocumentStatus.uploaded,
        created_by=current_user.id,
        is_editable=False
    )
    db.add(doc)
    await db.flush()
    
    # Call internal method (instead of FastAPI's UploadFile directly)
    from app.encryption import generate_dek, encrypt_dek, encrypt_file_data
    from app.routers.docvault import get_company_kek
    import aiofiles
    import os
    
    file_data = html.encode("utf-8")
    raw_dek, dek_nonce_for_encryption = generate_dek()
    ciphertext, file_nonce = encrypt_file_data(file_data, raw_dek)
    company_kek = await get_company_kek(db, eng.company_id)
    encrypted_dek, dek_nonce_for_kek = encrypt_dek(raw_dek, company_kek)
    
    vault_dir = f"{get_settings().VAULT_STORAGE_PATH}/{eng.company_id}"
    os.makedirs(vault_dir, exist_ok=True)
    file_uuid = str(uuid.uuid4())
    storage_path = f"{vault_dir}/{file_uuid}.enc"
    
    async with aiofiles.open(storage_path, "wb") as f:
        await f.write(file_nonce + ciphertext)
        
    import hashlib
    checksum = hashlib.sha256(file_data).hexdigest()

    version = DocumentVersion(
        document_id=doc.id,
        storage_path=storage_path,
        original_filename=f"Annual Report - {eng.period_label}.html",
        mime_type="text/html",
        size_bytes=len(file_data),
        checksum=checksum,
        encrypted_dek=encrypted_dek,
        dek_nonce=dek_nonce_for_kek,
        uploaded_by=current_user.id,
        version_number=1,
    )
    db.add(version)
    await db.flush()
    doc.current_version_id = version.id
    await db.commit()
    
    return {"id": str(doc.id), "url": f"/api/v1/docvault/documents/{doc.id}/download"}
