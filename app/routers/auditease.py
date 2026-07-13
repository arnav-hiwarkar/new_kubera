import json
import uuid
from typing import Annotated, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, and_, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_company_user
from app.models.company import CompanyUser
from app.models.auditor import Auditor
from app.models.auditease import (
    TrialBalanceAccount, LedgerGroup, AuditEngagement, AuditorEngagementGrant,
    PendingAuditorInvite, AuditEntry, AuditEntryLine, RequirementRequest, Query, QueryMessage,
    EngagementStatus, GrantStatus, AuditEntryStatus, RequestStatus, QueryStatus, SenderType
)
from app.schemas.auditease import (
    TrialBalanceAccountResponse, LedgerGroupResponse, LedgerGroupCreate, LedgerGroupRename,
    MapLedgerRequest, BulkMapRequest, UnmapRequest, AuditEngagementCreate,
    AuditEngagementResponse, AuditEntryResponse, RequirementRequestResponse,
    QueryResponse, QueryMessageResponse, QueryMessageCreate,
    TBColumnMap, TBInspectResponse, TBImportResult,
)
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
            and_(LedgerGroup.id == group_id, LedgerGroup.company_id.in_([None, company_id]))
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
                LedgerGroup.company_id.in_([None, company_id]),
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
    await db.delete(eng)
    await db.commit()
    return None


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

    # One auditor per engagement: clear any prior grant/pending before re-inviting.
    await db.execute(
        update(AuditorEngagementGrant)
        .where(AuditorEngagementGrant.engagement_id == engagement_id)
        .values(status=GrantStatus.revoked)
    )
    await db.execute(
        delete(PendingAuditorInvite).where(PendingAuditorInvite.engagement_id == engagement_id)
    )

    aud_res = await db.execute(select(Auditor).where(func.lower(Auditor.email) == email))
    auditor = aud_res.scalar_one_or_none()
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
        .options(selectinload(AuditEntry.lines))
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
    await db.refresh(entry)
    return entry


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
