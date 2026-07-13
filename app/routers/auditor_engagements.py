import uuid
from typing import Annotated, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_auditor
from app.models.auditor import Auditor
from app.models.auditease import (
    AuditEngagement, AuditorEngagementGrant, AuditEntry, AuditEntryLine,
    RequirementRequest, Query, QueryMessage, TrialBalanceAccount,
    EngagementStatus, GrantStatus, AuditEntryStatus, RequestStatus, QueryStatus, SenderType
)
from app.schemas.auditease import (
    AuditEngagementResponse, AuditEntryCreate, AuditEntryResponse,
    RequirementRequestCreate, RequirementRequestResponse,
    QueryCreate, QueryResponse, QueryMessageCreate, QueryMessageResponse,
    TrialBalanceAccountResponse
)

router = APIRouter(prefix="/api/v1/auditor", tags=["auditease-auditor"])


async def check_auditor_access(db: AsyncSession, auditor_id: uuid.UUID, engagement_id: uuid.UUID) -> AuditEngagement:
    result = await db.execute(
        select(AuditEngagement)
        .join(AuditorEngagementGrant, AuditEngagement.id == AuditorEngagementGrant.engagement_id)
        .where(
            and_(
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.engagement_id == engagement_id,
                AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
                AuditEngagement.status == EngagementStatus.active
            )
        )
    )
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=403, detail="No access to this engagement")
    return eng


@router.get("/engagements", response_model=List[AuditEngagementResponse])
async def list_engagements(
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(AuditEngagement)
        .join(AuditorEngagementGrant, AuditEngagement.id == AuditorEngagementGrant.engagement_id)
        .where(
            and_(
                AuditorEngagementGrant.auditor_id == current_auditor.id,
                AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
                AuditEngagement.status != EngagementStatus.closed,
            )
        )
        .order_by(AuditEngagement.created_at.desc())
    )
    return result.scalars().all()


@router.post("/engagements/{engagement_id}/accept")
async def accept_engagement(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(AuditorEngagementGrant)
        .where(
            and_(
                AuditorEngagementGrant.auditor_id == current_auditor.id,
                AuditorEngagementGrant.engagement_id == engagement_id,
                AuditorEngagementGrant.status == GrantStatus.invited
            )
        )
    )
    grant = result.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=404, detail="Invite not found or already accepted")

    grant.status = GrantStatus.accepted
    grant.accepted_at = datetime.now(timezone.utc)

    # Acceptance activates the engagement.
    eng_res = await db.execute(select(AuditEngagement).where(AuditEngagement.id == engagement_id))
    eng = eng_res.scalar_one_or_none()
    if eng and eng.status == EngagementStatus.invited:
        eng.status = EngagementStatus.active

    await db.commit()
    return {"message": "Engagement accepted"}


@router.get("/engagements/{engagement_id}/trial-balance", response_model=List[TrialBalanceAccountResponse])
async def get_trial_balance(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id)
    result = await db.execute(
        select(TrialBalanceAccount)
        .where(TrialBalanceAccount.engagement_id == engagement_id)
        .order_by(TrialBalanceAccount.ledger_name)
    )
    accounts = list(result.scalars().all())
    from app.services import ledger_groups as lg
    path_map = await lg.resolve_group_paths(db, eng.company_id)
    return lg.attach_group_paths(accounts, path_map)


@router.post("/engagements/{engagement_id}/entries", response_model=AuditEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_entry(
    engagement_id: uuid.UUID,
    entry: AuditEntryCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id)
    
    # Check debits == credits
    total_debit = sum(l.amount for l in entry.lines if l.side == "debit")
    total_credit = sum(l.amount for l in entry.lines if l.side == "credit")
    if total_debit != total_credit:
        raise HTTPException(status_code=400, detail="Debits must equal credits")
        
    db_entry = AuditEntry(
        engagement_id=engagement_id,
        created_by=current_auditor.id,
        code=entry.code,
        description=entry.description
    )
    db.add(db_entry)
    await db.flush()
    
    for line in entry.lines:
        db.add(AuditEntryLine(
            entry_id=db_entry.id,
            ledger_id=line.ledger_id,
            side=line.side,
            amount=line.amount
        ))
        
    await db.commit()
    await db.refresh(db_entry)
    
    # reload with lines
    res = await db.execute(select(AuditEntry).options(selectinload(AuditEntry.lines)).where(AuditEntry.id == db_entry.id))
    return res.scalar_one()


@router.post("/engagements/{engagement_id}/requirement-requests", response_model=RequirementRequestResponse)
async def create_requirement(
    engagement_id: uuid.UUID,
    req: RequirementRequestCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    
    db_req = RequirementRequest(
        engagement_id=engagement_id,
        raised_by=current_auditor.id,
        description=req.description
    )
    db.add(db_req)
    await db.commit()
    await db.refresh(db_req)
    return db_req


@router.post("/engagements/{engagement_id}/queries", response_model=QueryResponse)
async def create_query(
    engagement_id: uuid.UUID,
    query: QueryCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    
    db_query = Query(
        engagement_id=engagement_id,
        opened_by=current_auditor.id
    )
    db.add(db_query)
    await db.flush()
    
    msg = QueryMessage(
        query_id=db_query.id,
        sender_type=SenderType.auditor,
        sender_id=current_auditor.id,
        text=query.initial_message,
        attached_document_id=query.attached_document_id
    )
    db.add(msg)
    await db.commit()
    
    res = await db.execute(select(Query).options(selectinload(Query.messages)).where(Query.id == db_query.id))
    return res.scalar_one()


@router.post("/engagements/{engagement_id}/queries/{query_id}/messages", response_model=QueryMessageResponse)
async def add_query_message(
    engagement_id: uuid.UUID,
    query_id: uuid.UUID,
    msg: QueryMessageCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    
    q_res = await db.execute(select(Query).where(and_(Query.id == query_id, Query.engagement_id == engagement_id)))
    query = q_res.scalar_one_or_none()
    if not query or query.status == QueryStatus.closed:
        raise HTTPException(status_code=400, detail="Query not found or closed")
        
    db_msg = QueryMessage(
        query_id=query_id,
        sender_type=SenderType.auditor,
        sender_id=current_auditor.id,
        text=msg.text,
        attached_document_id=msg.attached_document_id
    )
    db.add(db_msg)
    await db.commit()
    await db.refresh(db_msg)
    return db_msg
