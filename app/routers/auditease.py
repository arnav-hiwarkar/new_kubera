import uuid
from typing import Annotated, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, and_, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_company_user
from app.models.company import CompanyUser
from app.models.auditor import Auditor
from app.models.auditease import (
    TrialBalanceAccount, LedgerGroup, AuditEngagement, AuditorEngagementGrant,
    AuditEntry, AuditEntryLine, RequirementRequest, Query, QueryMessage,
    EngagementStatus, GrantStatus, AuditEntryStatus, RequestStatus, QueryStatus, SenderType
)
from app.schemas.auditease import (
    TrialBalanceAccountResponse, LedgerGroupResponse, AuditEngagementCreate,
    AuditEngagementResponse, AuditEntryResponse, RequirementRequestResponse,
    QueryResponse, QueryMessageResponse, QueryMessageCreate
)

router = APIRouter(prefix="/api/v1/auditease", tags=["auditease-company"])


# --- Trial Balance ---

class TBImportRow(BaseModel):
    ledger_code: Optional[str] = None
    ledger_name: str
    opening_balance: float = 0.0
    debit: float = 0.0
    credit: float = 0.0
    closing_balance: float = 0.0


@router.post("/trial-balance/import", response_model=List[TrialBalanceAccountResponse])
async def import_trial_balance(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    rows: List[TBImportRow]
):
    # This acts as the mapped target from the frontend's column mapper.
    # In V1 we just insert/update them.
    created_accounts = []
    for row in rows:
        acc = TrialBalanceAccount(
            company_id=current_user.company_id,
            ledger_code=row.ledger_code,
            ledger_name=row.ledger_name,
            opening_balance=row.opening_balance,
            debit=row.debit,
            credit=row.credit,
            closing_balance=row.closing_balance
        )
        db.add(acc)
        created_accounts.append(acc)
        
    # Check balance match warning
    total_debit = sum(r.debit for r in rows)
    total_credit = sum(r.credit for r in rows)
    if total_debit != total_credit:
        print(f"Warning: Trial balance mismatch! Debit: {total_debit}, Credit: {total_credit}")
        
    await db.commit()
    for acc in created_accounts:
        await db.refresh(acc)
    return created_accounts


@router.get("/trial-balance", response_model=List[TrialBalanceAccountResponse])
async def get_trial_balance(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(TrialBalanceAccount).where(TrialBalanceAccount.company_id == current_user.company_id))
    return result.scalars().all()


@router.post("/ledgers/{ledger_id}/map-group", response_model=TrialBalanceAccountResponse)
async def map_ledger_group(
    ledger_id: uuid.UUID,
    group_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(TrialBalanceAccount).where(and_(TrialBalanceAccount.id == ledger_id, TrialBalanceAccount.company_id == current_user.company_id)))
    ledger = result.scalar_one_or_none()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")
        
    # Check if group exists (either seeded or company-owned)
    grp_res = await db.execute(select(LedgerGroup).where(and_(LedgerGroup.id == group_id, LedgerGroup.company_id.in_([None, current_user.company_id]))))
    group = grp_res.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
        
    ledger.mapped_group_id = group.id
    await db.commit()
    await db.refresh(ledger)
    return ledger


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
        status=EngagementStatus.active,
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
    result = await db.execute(select(AuditEngagement).where(AuditEngagement.company_id == current_user.company_id))
    return result.scalars().all()


@router.patch("/engagements/{engagement_id}/close", response_model=AuditEngagementResponse)
async def close_engagement(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(AuditEngagement).where(and_(AuditEngagement.id == engagement_id, AuditEngagement.company_id == current_user.company_id)))
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    eng.status = EngagementStatus.closed
    
    # Revoke all grants
    await db.execute(
        update(AuditorEngagementGrant)
        .where(AuditorEngagementGrant.engagement_id == engagement_id)
        .values(status=GrantStatus.revoked)
    )
    
    await db.commit()
    await db.refresh(eng)
    return eng


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


@router.post("/engagements/{engagement_id}/invite-auditor")
async def invite_auditor(
    engagement_id: uuid.UUID,
    invite: AuditorInvite,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(AuditEngagement).where(and_(AuditEngagement.id == engagement_id, AuditEngagement.company_id == current_user.company_id)))
    eng = result.scalar_one_or_none()
    if not eng or eng.status == EngagementStatus.closed:
        raise HTTPException(status_code=404, detail="Active engagement not found")

    aud_res = await db.execute(select(Auditor).where(func.lower(Auditor.email) == invite.email.lower()))
    auditor = aud_res.scalar_one_or_none()
    
    is_new = False
    if not auditor:
        is_new = True
        # Create a placeholder auditor account so they can receive invites before registering
        auditor = Auditor(
            email=invite.email,
            hashed_password="__pending__",
            name="Pending Auditor"
        )
        db.add(auditor)
        await db.flush() # get auditor.id
    else:
        # Check if grant already exists
        grant_res = await db.execute(select(AuditorEngagementGrant).where(
            and_(AuditorEngagementGrant.auditor_id == auditor.id, AuditorEngagementGrant.engagement_id == engagement_id)
        ))
        if grant_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Auditor is already invited to this engagement")
        
    grant = AuditorEngagementGrant(
        auditor_id=auditor.id,
        engagement_id=engagement_id,
        status=GrantStatus.invited if is_new else GrantStatus.accepted,
        accepted_at=None if is_new else datetime.now(timezone.utc)
    )
    db.add(grant)
    await db.commit()
    return {"message": "Auditor invited"}


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
    msg: QueryMessageCreate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(AuditEngagement).where(and_(AuditEngagement.id == engagement_id, AuditEngagement.company_id == current_user.company_id)))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    q_res = await db.execute(select(Query).where(and_(Query.id == query_id, Query.engagement_id == engagement_id)))
    query = q_res.scalar_one_or_none()
    if not query or query.status == QueryStatus.closed:
        raise HTTPException(status_code=400, detail="Query not found or closed")
        
    if msg.attached_document_id:
        from app.models.docvault import Document, DocumentAccessOverride, PrincipalType
        doc_res = await db.execute(select(Document).where(and_(Document.id == msg.attached_document_id, Document.company_id == current_user.company_id)))
        if not doc_res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Document not found")
            
        grant = DocumentAccessOverride(
            document_id=msg.attached_document_id,
            principal_type=PrincipalType.auditor,
            principal_id=query.opened_by,
            permission_level="read"
        )
        db.add(grant)
        
    message = QueryMessage(
        query_id=query_id,
        sender_type=SenderType.company_user,
        sender_id=current_user.id,
        text=msg.text,
        attached_document_id=msg.attached_document_id
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message
