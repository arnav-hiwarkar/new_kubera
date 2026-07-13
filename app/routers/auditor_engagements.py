import uuid
from typing import Annotated, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response
import aiofiles
from pydantic import BaseModel
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_auditor
from app.models.auditor import Auditor
from app.models.docvault import Document, DocumentVersion
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
from app.schemas.docvault import DocumentResponse
from app.services import document_access as doc_access
from app.encryption import decrypt_dek, decrypt_file_data
from app.routers.docvault import get_company_kek

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
        select(AuditEngagement, AuditorEngagementGrant.status)
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
    
    rows = result.all()
    out = []
    for eng, grant_status in rows:
        # If the grant is accepted, the engagement is active from the auditor's perspective.
        # This prevents Pydantic validation errors since 'accepted' is not a valid EngagementStatus.
        display_status = grant_status
        if grant_status == GrantStatus.accepted:
            display_status = EngagementStatus.active
            
        out.append({
            "id": eng.id,
            "company_id": eng.company_id,
            "period_label": eng.period_label,
            "status": display_status,
            "created_by": eng.created_by,
            "created_at": eng.created_at,
            "updated_at": eng.updated_at
        })
    return out


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
<<<<<<< HEAD
    
    from sqlalchemy.orm import aliased
    L1 = aliased(LedgerGroup)
    L2 = aliased(LedgerGroup)
    L3 = aliased(LedgerGroup)
    
    result = await db.execute(
        select(
            TrialBalanceAccount,
            L1.name,
            L2.name,
            L3.name
        )
        .outerjoin(L1, TrialBalanceAccount.mapped_group_id == L1.id)
        .outerjoin(L2, L1.parent_id == L2.id)
        .outerjoin(L3, L2.parent_id == L3.id)
        .where(TrialBalanceAccount.company_id == eng.company_id)
        .order_by(TrialBalanceAccount.ledger_code)
    )
    
    out = []
    for tb, g1, g2, g3 in result.all():
        data = tb.__dict__.copy()
        data["mapped_group_name"] = g1
        data["parent_group_name"] = g2
        data["top_group_name"] = g3
        out.append(data)
        
    return out


@router.get("/engagements/{engagement_id}/entries", response_model=List[AuditEntryResponse])
async def list_entries(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    
    result = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines))
        .where(
            and_(
                AuditEntry.engagement_id == engagement_id,
                AuditEntry.created_by == current_auditor.id
            )
        )
        .order_by(AuditEntry.created_at.desc())
    )
    return result.scalars().all()
=======
    result = await db.execute(
        select(TrialBalanceAccount)
        .where(TrialBalanceAccount.engagement_id == engagement_id)
        .order_by(TrialBalanceAccount.ledger_name)
    )
    accounts = list(result.scalars().all())
    from app.services import ledger_groups as lg
    path_map = await lg.resolve_group_paths(db, eng.company_id)
    return lg.attach_group_paths(accounts, path_map)
>>>>>>> new_frontend


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
    
    # reload with lines + ledger for the response
    res = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines).selectinload(AuditEntryLine.ledger))
        .where(AuditEntry.id == db_entry.id)
    )
    return res.scalar_one()


<<<<<<< HEAD
@router.put("/engagements/{engagement_id}/entries/{entry_id}", response_model=AuditEntryResponse)
async def update_entry(
    engagement_id: uuid.UUID,
    entry_id: uuid.UUID,
    entry: AuditEntryCreate,
=======
@router.get("/engagements/{engagement_id}/entries", response_model=List[AuditEntryResponse])
async def list_auditor_entries(
    engagement_id: uuid.UUID,
>>>>>>> new_frontend
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
<<<<<<< HEAD
    
    # Check debits == credits
    total_debit = sum(l.amount for l in entry.lines if l.side == "debit")
    total_credit = sum(l.amount for l in entry.lines if l.side == "credit")
    if total_debit != total_credit:
        raise HTTPException(status_code=400, detail="Debits must equal credits")
        
    result = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines))
        .where(
            and_(
                AuditEntry.id == entry_id,
                AuditEntry.engagement_id == engagement_id,
                AuditEntry.created_by == current_auditor.id
            )
        )
    )
    db_entry = result.scalar_one_or_none()
    
    if not db_entry:
        raise HTTPException(status_code=404, detail="Audit entry not found")
        
    if db_entry.status == AuditEntryStatus.approved:
        raise HTTPException(status_code=400, detail="Cannot edit an approved audit entry")
        
    # Update fields and reset status
    db_entry.code = entry.code
    db_entry.description = entry.description
    db_entry.status = AuditEntryStatus.proposed
    db_entry.rejection_comment = None
    
    # Delete old lines
    for line in db_entry.lines:
        await db.delete(line)
        
    # Add new lines
    for line in entry.lines:
        db.add(AuditEntryLine(
            entry_id=db_entry.id,
            ledger_id=line.ledger_id,
            side=line.side,
            amount=line.amount
        ))
        
    await db.commit()
    
    # reload with lines
    res = await db.execute(select(AuditEntry).options(selectinload(AuditEntry.lines)).where(AuditEntry.id == db_entry.id))
    return res.scalar_one()


@router.get("/engagements/{engagement_id}/requirement-requests", response_model=List[RequirementRequestResponse])
async def get_requirements(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    
    result = await db.execute(
        select(RequirementRequest).where(
            and_(
                RequirementRequest.engagement_id == engagement_id,
                RequirementRequest.raised_by == current_auditor.id
            )
        )
=======
    result = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines).selectinload(AuditEntryLine.ledger))
        .where(AuditEntry.engagement_id == engagement_id)
        .order_by(AuditEntry.created_at.desc())
>>>>>>> new_frontend
    )
    return result.scalars().all()


<<<<<<< HEAD
=======
@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_auditor_entry(
    entry_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(AuditEntry)
        .join(AuditorEngagementGrant, AuditorEngagementGrant.engagement_id == AuditEntry.engagement_id)
        .where(
            and_(
                AuditEntry.id == entry_id,
                AuditorEngagementGrant.auditor_id == current_auditor.id,
                AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted])
            )
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found or access denied")
        
    if entry.status != AuditEntryStatus.proposed:
        raise HTTPException(status_code=400, detail="Only proposed entries can be deleted")
        
    await db.delete(entry)
    await db.commit()
    return None



>>>>>>> new_frontend
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
        title=req.title,
        description=req.description
    )
    db.add(db_req)
    await db.commit()
    await db.refresh(db_req)
    return db_req


@router.put("/engagements/{engagement_id}/requirement-requests/{req_id}", response_model=RequirementRequestResponse)
async def update_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    req: RequirementRequestCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    
    result = await db.execute(select(RequirementRequest).where(and_(RequirementRequest.id == req_id, RequirementRequest.engagement_id == engagement_id, RequirementRequest.raised_by == current_auditor.id)))
    db_req = result.scalar_one_or_none()
    if not db_req:
        raise HTTPException(status_code=404, detail="Requirement request not found")
    if db_req.status != RequestStatus.open:
        raise HTTPException(status_code=400, detail="Cannot edit a fulfilled requirement request")
        
    db_req.title = req.title
    db_req.description = req.description
    await db.commit()
    await db.refresh(db_req)
    return db_req


@router.delete("/engagements/{engagement_id}/requirement-requests/{req_id}")
async def delete_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    
    result = await db.execute(select(RequirementRequest).where(and_(RequirementRequest.id == req_id, RequirementRequest.engagement_id == engagement_id, RequirementRequest.raised_by == current_auditor.id)))
    db_req = result.scalar_one_or_none()
    if not db_req:
        raise HTTPException(status_code=404, detail="Requirement request not found")
    if db_req.status != RequestStatus.open:
        raise HTTPException(status_code=400, detail="Cannot delete a fulfilled requirement request")
        
    await db.delete(db_req)
    await db.commit()
    return {"message": "Requirement request deleted"}


@router.get("/engagements/{engagement_id}/queries", response_model=List[QueryResponse])
async def list_queries(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    
    result = await db.execute(
        select(Query)
        .options(selectinload(Query.messages))
        .where(Query.engagement_id == engagement_id)
        .order_by(Query.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/engagements/{engagement_id}/queries/{query_id}", response_model=QueryResponse)
async def get_query(
    engagement_id: uuid.UUID,
    query_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    
    result = await db.execute(
        select(Query)
        .options(selectinload(Query.messages))
        .where(and_(Query.id == query_id, Query.engagement_id == engagement_id))
    )
    db_query = result.scalar_one_or_none()
    if not db_query:
        raise HTTPException(status_code=404, detail="Query not found")
    return db_query


@router.post("/engagements/{engagement_id}/queries", response_model=QueryResponse)
async def create_query(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    initial_message: Annotated[str, Form(...)],
    file: Annotated[Optional[UploadFile], File()] = None,
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id)
    
    db_query = Query(
        engagement_id=engagement_id,
        opened_by=current_auditor.id
    )
    db.add(db_query)
    await db.flush()
    
    attached_document_id = None
    if file:
        doc = await doc_access.create_attachment_document(
            db, company_id=eng.company_id, file=file, created_by=None, grant_auditor_id=current_auditor.id
        )
        attached_document_id = doc.id
        
    msg = QueryMessage(
        query_id=db_query.id,
        sender_type=SenderType.auditor,
        sender_id=current_auditor.id,
        text=initial_message,
        attached_document_id=attached_document_id
    )
    db.add(msg)
    await db.commit()
    
    res = await db.execute(select(Query).options(selectinload(Query.messages)).where(Query.id == db_query.id))
    return res.scalar_one()


@router.post("/engagements/{engagement_id}/queries/{query_id}/messages", response_model=QueryMessageResponse)
async def add_query_message(
    engagement_id: uuid.UUID,
    query_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    text: Annotated[str, Form(...)],
    file: Annotated[Optional[UploadFile], File()] = None,
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id)
    
    q_res = await db.execute(select(Query).where(and_(Query.id == query_id, Query.engagement_id == engagement_id)))
    query = q_res.scalar_one_or_none()
    if not query or query.status == QueryStatus.closed:
        raise HTTPException(status_code=400, detail="Query not found or closed")
        
    attached_document_id = None
    if file:
        doc = await doc_access.create_attachment_document(
            db, company_id=eng.company_id, file=file, created_by=None, grant_auditor_id=current_auditor.id
        )
        attached_document_id = doc.id
        
    db_msg = QueryMessage(
        query_id=query_id,
        sender_type=SenderType.auditor,
        sender_id=current_auditor.id,
        text=text,
        attached_document_id=attached_document_id
    )
    db.add(db_msg)
    await db.commit()
    await db.refresh(db_msg)
    return db_msg


<<<<<<< HEAD
@router.put("/engagements/{engagement_id}/queries/{query_id}/close", response_model=QueryResponse)
=======
@router.get("/engagements/{engagement_id}/requirement-requests", response_model=List[RequirementRequestResponse])
async def list_requirements(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    reqs = await db.execute(select(RequirementRequest).where(RequirementRequest.engagement_id == engagement_id))
    return reqs.scalars().all()


@router.get("/engagements/{engagement_id}/queries", response_model=List[QueryResponse])
async def list_queries(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
    queries = await db.execute(select(Query).options(selectinload(Query.messages)).where(Query.engagement_id == engagement_id))
    return queries.scalars().all()


@router.post("/engagements/{engagement_id}/queries/{query_id}/close", response_model=QueryResponse)
>>>>>>> new_frontend
async def close_query(
    engagement_id: uuid.UUID,
    query_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id)
<<<<<<< HEAD
    
    result = await db.execute(select(Query).options(selectinload(Query.messages)).where(and_(Query.id == query_id, Query.engagement_id == engagement_id)))
    db_query = result.scalar_one_or_none()
    if not db_query:
        raise HTTPException(status_code=404, detail="Query not found")
    if db_query.opened_by != current_auditor.id:
        raise HTTPException(status_code=403, detail="Only the auditor who opened the query can close it")
        
    db_query.status = QueryStatus.closed
    await db.commit()
    await db.refresh(db_query)
    return db_query
=======
    q_res = await db.execute(select(Query).options(selectinload(Query.messages)).where(and_(Query.id == query_id, Query.engagement_id == engagement_id)))
    query = q_res.scalar_one_or_none()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    if query.opened_by != current_auditor.id:
        raise HTTPException(status_code=403, detail="Only the opener can close this query")
        
    query.status = QueryStatus.closed
    await db.commit()
    await db.refresh(query)
    return query


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    doc = await doc_access.auditor_can_access_document(db, current_auditor.id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")
        
    result = await db.execute(
        select(Document).options(selectinload(Document.versions)).where(Document.id == document_id)
    )
    return result.scalar_one()


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await doc_access.auditor_can_access_document(db, current_auditor.id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")
        
    result = await db.execute(
        select(Document).options(selectinload(Document.versions)).where(Document.id == document_id)
    )
    doc_full = result.scalar_one()
    
    if not doc_full.current_version_id:
        raise HTTPException(status_code=404, detail="No versions available")
    version = next((v for v in doc_full.versions if v.id == doc_full.current_version_id), None)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
        
    company_kek = await get_company_kek(db, doc_full.company_id)
    raw_dek = decrypt_dek(version.encrypted_dek, version.dek_nonce, company_kek)
    
    async with aiofiles.open(version.storage_path, "rb") as f:
        file_content = await f.read()
        
    nonce = file_content[:12]
    ciphertext = file_content[12:]
    
    plaintext = decrypt_file_data(ciphertext, nonce, raw_dek)
    
    return Response(
        content=plaintext, 
        media_type=version.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{version.original_filename}"'}
    )
>>>>>>> new_frontend
