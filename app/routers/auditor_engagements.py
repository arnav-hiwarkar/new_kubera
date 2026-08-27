import uuid
from typing import Annotated, List, Literal, Optional
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response
import aiofiles
from pydantic import BaseModel
from sqlalchemy import select, and_, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_auditor
from app.models.auditor import Auditor
from app.models.docvault import Document, DocumentVersion
from app.models.auditease import (
    AuditEngagement, AuditorEngagementGrant, AuditEntry, AuditEntryLine,
    RequirementRequest, RequirementResponse, Query, QueryMessage, TrialBalanceAccount,
    EngagementStatus, GrantStatus, AuditEntryStatus, RequestStatus, QueryStatus, SenderType,
    AREA_LABELS
)
from app.schemas.auditease import (
    AuditEngagementResponse, AuditEntryCreate, AuditEntryResponse,
    RequirementRequestCreate, RequirementRequestResponse,
    QueryCreate, QueryResponse, QueryMessageCreate, QueryMessageResponse,
    TrialBalanceAccountResponse, TrialBalanceViewResponse
)
from app.schemas.docvault import DocumentResponse
from app.services import document_access as doc_access
from app.services.auditor_access import area_enabled, attach_actor_names, attach_sender_names
from app.services.requirements import next_seq, enrich_requirements
from app.models.activity_log import ActorType
from app.services.activity import log_activity
from app.encryption import decrypt_dek, decrypt_file_data
from app.routers.docvault import get_company_kek

router = APIRouter(prefix="/api/v1/auditor", tags=["auditease-auditor"])


async def check_auditor_access(
    db: AsyncSession,
    auditor_id: uuid.UUID,
    engagement_id: uuid.UUID,
    area: str | None = None,
) -> AuditEngagement:
    query = (
        select(AuditEngagement, AuditorEngagementGrant.area_permissions)
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
    row = (await db.execute(query)).first()
    if not row:
        raise HTTPException(status_code=403, detail="No access to this engagement")
    eng, perms = row
    if area is not None and not area_enabled(perms, area):
        raise HTTPException(
            status_code=403,
            detail=f"Your access to {AREA_LABELS.get(area, area)} was removed by the company.",
        )
    return eng



@router.get("/engagements", response_model=List[AuditEngagementResponse])
async def list_engagements(
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(AuditEngagement, AuditorEngagementGrant.status, AuditorEngagementGrant.area_permissions)
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
    for eng, grant_status, perms in rows:
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
            "updated_at": eng.updated_at,
            "area_permissions": perms or {},
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

    await log_activity(db, eng.company_id, current_auditor.id,
                 "auditor.grant_accepted", "audit_engagement", engagement_id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)

    await db.commit()
    return {"message": "Engagement accepted"}


@router.get("/engagements/{engagement_id}/trial-balance", response_model=TrialBalanceViewResponse)
async def get_trial_balance(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Same envelope as the company endpoint, and the same totals implementation.

    Read-only for the auditor: correcting a sign convention is a company action.
    """
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="trial_balance")
    from app.services import trial_balance_query as tbq

    figures = await tbq.load_engagement_figures(db, eng.company_id, engagement_id)
    return TrialBalanceViewResponse(
        accounts=[TrialBalanceAccountResponse.model_validate(a) for a in figures.accounts],
        totals=tbq.totals_response(figures.summary),
        sign_convention=eng.tb_sign_convention,
        sign_unresolved_count=figures.summary.sign_unresolved_count,
        inconsistent_row_count=sum(
            1 for a in figures.accounts if a.source_row_consistent is False
        ),
        warnings=tbq.view_warnings(figures.figures, figures.summary, eng.tb_sign_convention),
    )


@router.post("/engagements/{engagement_id}/entries", response_model=AuditEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_entry(
    engagement_id: uuid.UUID,
    entry: AuditEntryCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="entries")
    
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

    await log_activity(db, eng.company_id, current_auditor.id,
                 "entry.created", "audit_entry", db_entry.id,
                 metadata_={"description": db_entry.description},
                 actor_type=ActorType.auditor, engagement_id=engagement_id)

    await db.commit()
    await db.refresh(db_entry)
    
    # reload with lines + ledger for the response
    res = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines).selectinload(AuditEntryLine.ledger))
        .where(AuditEntry.id == db_entry.id)
    )
    entry = res.scalar_one()
    await attach_actor_names(db, [entry], "created_by", "created_by_name")
    return entry


@router.get("/engagements/{engagement_id}/entries", response_model=List[AuditEntryResponse])
async def list_auditor_entries(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id, area="entries")
    result = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines).selectinload(AuditEntryLine.ledger))
        .where(AuditEntry.engagement_id == engagement_id)
        .order_by(AuditEntry.created_at.desc())
    )
    entries = result.scalars().all()
    await attach_actor_names(db, entries, "created_by", "created_by_name")
    return entries


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_auditor_entry(
    entry_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng_res = await db.execute(select(AuditEntry.engagement_id).where(AuditEntry.id == entry_id))
    eng_id = eng_res.scalar_one_or_none()
    check = None
    if eng_id:
        try:
            check = await check_auditor_access(db, current_auditor.id, eng_id, area="entries")
        except HTTPException as e:
            if e.status_code != 403:
                raise
    if check is None:
        raise HTTPException(status_code=404, detail="Entry not found or access denied")

    result = await db.execute(
        select(AuditEntry).where(and_(AuditEntry.id == entry_id, AuditEntry.engagement_id == eng_id))
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found or access denied")
        
    if entry.status != AuditEntryStatus.proposed:
        raise HTTPException(status_code=400, detail="Only proposed entries can be deleted")

    await log_activity(db, check.company_id, current_auditor.id,
                 "entry.deleted", "audit_entry", entry.id,
                 actor_type=ActorType.auditor, engagement_id=eng_id)

    await db.delete(entry)
    await db.commit()
    return None


@router.post("/engagements/{engagement_id}/requirement-requests", response_model=RequirementRequestResponse)
async def create_requirement(
    engagement_id: uuid.UUID,
    req: RequirementRequestCreate,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")

    db_req = RequirementRequest(
        engagement_id=engagement_id,
        raised_by=current_auditor.id,
        seq_number=await next_seq(db, engagement_id),
        description=req.description,
        priority=req.priority,
        due_date=req.due_date,
    )
    db.add(db_req)
    await db.flush()

    await log_activity(db, eng.company_id, current_auditor.id,
                 "requirement.raised", "requirement_request", db_req.id,
                 metadata_={"title": db_req.requirement_id},
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
    await db.commit()
    await db.refresh(db_req)
    return (await enrich_requirements(db, engagement_id, [db_req]))[0]


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
        RequirementRequest.id == req_id, RequirementRequest.engagement_id == engagement_id
    )))).scalar_one_or_none()
    if not db_req:
        raise HTTPException(status_code=404, detail="Requirement request not found")
    if db_req.status == RequestStatus.closed:
        raise HTTPException(status_code=400, detail="Reopen the requirement before editing it")

    db_req.description = req.description
    db_req.priority = req.priority
    db_req.due_date = req.due_date

    await log_activity(db, eng.company_id, current_auditor.id,
                 "requirement.updated", "requirement_request", db_req.id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)

    await db.commit()
    await db.refresh(db_req)
    return (await enrich_requirements(db, engagement_id, [db_req]))[0]


@router.delete("/engagements/{engagement_id}/requirement-requests/{req_id}")
async def delete_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")
    
    result = await db.execute(select(RequirementRequest).where(and_(
        RequirementRequest.id == req_id, RequirementRequest.engagement_id == engagement_id
    )))
    db_req = result.scalar_one_or_none()
    if not db_req:
        raise HTTPException(status_code=404, detail="Requirement request not found")

    has_response = (await db.execute(
        select(RequirementResponse.id).where(RequirementResponse.requirement_id == req_id).limit(1)
    )).scalar_one_or_none()
    if has_response:
        raise HTTPException(status_code=400, detail="This requirement has company submissions and cannot be deleted. Close it instead.")

    await log_activity(db, eng.company_id, current_auditor.id,
                 "requirement.deleted", "requirement_request", db_req.id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)

    await db.delete(db_req)
    await db.commit()
    return {"message": "Requirement request deleted"}


@router.post("/engagements/{engagement_id}/requirement-requests/{req_id}/close",
             response_model=RequirementRequestResponse)
async def close_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")
    db_req = (await db.execute(select(RequirementRequest).where(and_(
        RequirementRequest.id == req_id,
        RequirementRequest.engagement_id == engagement_id)))).scalar_one_or_none()
    if not db_req:
        raise HTTPException(status_code=404, detail="Requirement request not found")
    if db_req.status == RequestStatus.closed:
        raise HTTPException(status_code=400, detail="Requirement is already closed")

    db_req.status = RequestStatus.closed
    db_req.closed_by = current_auditor.id
    db_req.closed_at = datetime.now(timezone.utc)

    await log_activity(db, eng.company_id, current_auditor.id,
                 "requirement.closed", "requirement_request", db_req.id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
    await db.commit()
    await db.refresh(db_req)
    return (await enrich_requirements(db, engagement_id, [db_req]))[0]


@router.post("/engagements/{engagement_id}/requirement-requests/{req_id}/reopen",
             response_model=RequirementRequestResponse)
async def reopen_requirement(
    engagement_id: uuid.UUID,
    req_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="requirements")
    db_req = (await db.execute(select(RequirementRequest).where(and_(
        RequirementRequest.id == req_id,
        RequirementRequest.engagement_id == engagement_id)))).scalar_one_or_none()
    if not db_req:
        raise HTTPException(status_code=404, detail="Requirement request not found")
    if db_req.status == RequestStatus.open:
        raise HTTPException(status_code=400, detail="Requirement is already open")

    db_req.status = RequestStatus.open
    db_req.closed_by = None
    db_req.closed_at = None

    await log_activity(db, eng.company_id, current_auditor.id,
                 "requirement.reopened", "requirement_request", db_req.id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
    await db.commit()
    await db.refresh(db_req)
    return (await enrich_requirements(db, engagement_id, [db_req]))[0]


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
        # The shipped template leads with an "Instructions" sheet; target the
        # "Requirements" sheet explicitly, falling back to the first sheet.
        try:
            _, rows = load_sheet(file.filename or "", content, sheet_name="Requirements")
        except ValueError:
            _, rows = load_sheet(file.filename or "", content, sheet_name=None)
        created = await import_requirements(
            db, engagement_id, current_auditor.id, rows)
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


@router.get("/engagements/{engagement_id}/queries", response_model=List[QueryResponse])
async def list_queries(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id, area="queries")
    
    result = await db.execute(
        select(Query)
        .options(selectinload(Query.messages))
        .where(Query.engagement_id == engagement_id)
        .order_by(Query.updated_at.desc())
    )
    query_list = result.scalars().all()
    for q in query_list:
        await attach_sender_names(db, q.messages)
    return query_list


@router.get("/engagements/{engagement_id}/queries/{query_id}", response_model=QueryResponse)
async def get_query(
    engagement_id: uuid.UUID,
    query_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    await check_auditor_access(db, current_auditor.id, engagement_id, area="queries")
    
    result = await db.execute(
        select(Query)
        .options(selectinload(Query.messages))
        .where(and_(Query.id == query_id, Query.engagement_id == engagement_id))
    )
    db_query = result.scalar_one_or_none()
    if not db_query:
        raise HTTPException(status_code=404, detail="Query not found")
    await attach_sender_names(db, db_query.messages)
    return db_query


@router.post("/engagements/{engagement_id}/queries", response_model=QueryResponse)
async def create_query(
    engagement_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    initial_message: Annotated[str, Form(...)],
    file: Annotated[Optional[UploadFile], File()] = None,
    requirement_id: Annotated[Optional[uuid.UUID], Form()] = None,
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="queries")
    
    db_query = Query(
        engagement_id=engagement_id,
        opened_by=current_auditor.id
    )
    db.add(db_query)
    await db.flush()

    if requirement_id is not None:
        target = (await db.execute(select(RequirementRequest.id).where(and_(
            RequirementRequest.id == requirement_id,
            RequirementRequest.engagement_id == engagement_id)))).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=400, detail="Requirement not found in this engagement")
        db_query.requirement_id = requirement_id
    
    attached_document_id = None
    if file:
        doc = await doc_access.create_attachment_document(
            db, company_id=eng.company_id, file=file, created_by=None, grant_auditor_id=current_auditor.id, engagement_id=engagement_id
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

    await log_activity(db, eng.company_id, current_auditor.id,
                 "query.opened", "query", db_query.id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)

    await db.commit()
    
    res = await db.execute(select(Query).options(selectinload(Query.messages)).where(Query.id == db_query.id))
    query = res.scalar_one()
    await attach_sender_names(db, query.messages)
    return query


@router.post("/engagements/{engagement_id}/queries/{query_id}/messages", response_model=QueryMessageResponse)
async def add_query_message(
    engagement_id: uuid.UUID,
    query_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    text: Annotated[str, Form(...)],
    file: Annotated[Optional[UploadFile], File()] = None,
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="queries")
    
    q_res = await db.execute(select(Query).where(and_(Query.id == query_id, Query.engagement_id == engagement_id)))
    query = q_res.scalar_one_or_none()
    if not query or query.status == QueryStatus.closed:
        raise HTTPException(status_code=400, detail="Query not found or closed")
        
    attached_document_id = None
    if file:
        doc = await doc_access.create_attachment_document(
            db, company_id=eng.company_id, file=file, created_by=None, grant_auditor_id=current_auditor.id, engagement_id=engagement_id
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

    await log_activity(db, eng.company_id, current_auditor.id,
                 "query.replied", "query", query_id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)

    await db.commit()
    await db.refresh(db_msg)
    await attach_sender_names(db, [db_msg])
    return db_msg


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
    return await enrich_requirements(db, engagement_id, req_list)


@router.post("/engagements/{engagement_id}/queries/{query_id}/close", response_model=QueryResponse)
async def close_query(
    engagement_id: uuid.UUID,
    query_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng = await check_auditor_access(db, current_auditor.id, engagement_id, area="queries")
    q_res = await db.execute(select(Query).options(selectinload(Query.messages)).where(and_(Query.id == query_id, Query.engagement_id == engagement_id)))
    query = q_res.scalar_one_or_none()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    if query.opened_by != current_auditor.id:
        raise HTTPException(status_code=403, detail="Only the opener can close this query")
        
    query.status = QueryStatus.closed

    await log_activity(db, eng.company_id, current_auditor.id,
                 "query.closed", "query", query_id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)

    await db.commit()
    await db.refresh(query)
    await attach_sender_names(db, query.messages)
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

    await log_activity(db, doc_full.company_id, current_auditor.id,
                 "document.downloaded", "document", document_id,
                 metadata_={"filename": version.original_filename},
                 actor_type=ActorType.auditor)

    return Response(
        content=plaintext, 
        media_type=version.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{version.original_filename}"'}
    )
