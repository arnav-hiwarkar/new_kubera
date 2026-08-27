"""AuditEase Requirements business logic: sequencing, submissions, access, and enrichment."""
import uuid
from typing import Optional, Sequence

from fastapi import HTTPException, UploadFile
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auditease import (
    RequirementRequest,
    RequirementResponse,
    RequirementResponseDocument,
    Query,
)
from app.models.auditor import Auditor
from app.models.company import CompanyUser
from app.models.docvault import Document, DocumentVersion
from app.services.document_access import (
    ensure_audit_bucket,
    grant_document_access_to_auditors,
)


async def next_seq(db: AsyncSession, engagement_id: uuid.UUID) -> int:
    """Next per-engagement sequence number (max + 1)."""
    res = await db.execute(
        select(func.max(RequirementRequest.seq_number)).where(
            RequirementRequest.engagement_id == engagement_id
        )
    )
    return (res.scalar() or 0) + 1


def submission_document_title(req_display_id: str, round_number: int, filename: str) -> str:
    """e.g. 'REQ-003 · Sub 2 · bank-statement-jan.pdf' (truncated to 255 chars)."""
    return f"{req_display_id} · Sub {round_number} · {filename}"[:255]


def submission_document_tags(engagement_id: uuid.UUID, req_display_id: str) -> list[str]:
    """['audit-attachment', 'engagement:<uuid>', 'REQ-003']"""
    return ["audit-attachment", f"engagement:{engagement_id}", req_display_id]


async def validate_document_ids(
    db: AsyncSession, company_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
) -> None:
    """Raise HTTPException(404) unless EVERY id is a document of `company_id`.
    All-or-nothing: one bad id rejects the whole submission."""
    if not document_ids:
        return
    unique_ids = list(set(document_ids))
    res = await db.execute(
        select(Document.id).where(
            and_(
                Document.id.in_(unique_ids),
                Document.company_id == company_id,
            )
        )
    )
    found_ids = set(res.scalars().all())
    if len(found_ids) != len(unique_ids):
        raise HTTPException(status_code=404, detail="One or more documents not found")


async def create_submission(
    db: AsyncSession,
    *,
    req: RequirementRequest,
    engagement_id: uuid.UUID,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    text_answer: Optional[str],
    files: Sequence[UploadFile],
    document_ids: Sequence[uuid.UUID],
) -> RequirementResponse:
    """Create one round at max(round_number)+1, upload each file into the shared
    Audit Attachments bucket via create_attachment_document() / handle_file_upload,
    link every uploaded and picked document with its filename snapshot, and grant
    read to every accepted auditor holding the requirements area. Does NOT commit."""
    from app.routers.docvault import handle_file_upload

    # Validate picked documents first (all-or-nothing check before creating any records)
    if document_ids:
        await validate_document_ids(db, company_id, document_ids)

    # Next round number for this requirement
    res = await db.execute(
        select(func.max(RequirementResponse.round_number)).where(
            RequirementResponse.requirement_id == req.id
        )
    )
    next_round = (res.scalar() or 0) + 1

    submission = RequirementResponse(
        id=uuid.uuid4(),
        requirement_id=req.id,
        round_number=next_round,
        responded_by=user_id,
        text_answer=text_answer,
    )
    db.add(submission)
    await db.flush()

    # Upload files
    if files:
        bucket = await ensure_audit_bucket(db, company_id, user_id)
        for f in files:
            orig_filename = f.filename or "attachment"
            doc_title = submission_document_title(req.requirement_id, next_round, orig_filename)
            doc_tags = submission_document_tags(engagement_id, req.requirement_id)
            doc = Document(
                company_id=company_id,
                bucket_id=bucket.id,
                title=doc_title,
                tags=doc_tags,
                is_editable=False,
                created_by=user_id,
            )
            db.add(doc)
            await db.flush()
            version = await handle_file_upload(f, doc.id, company_id, user_id, 1, db)
            doc.current_version_id = version.id
            await grant_document_access_to_auditors(db, engagement_id, doc.id)

            join_row = RequirementResponseDocument(
                id=uuid.uuid4(),
                response_id=submission.id,
                document_id=doc.id,
                filename=orig_filename,
            )
            db.add(join_row)

    # Attach picked documents
    if document_ids:
        unique_picked = list(dict.fromkeys(document_ids))
        res_docs = await db.execute(
            select(Document.id, Document.title, DocumentVersion.original_filename)
            .join(DocumentVersion, DocumentVersion.id == Document.current_version_id, isouter=True)
            .where(Document.id.in_(unique_picked))
        )
        picked_meta = {
            row[0]: (row[2] or row[1] or "document")
            for row in res_docs.all()
        }
        for doc_id in unique_picked:
            fname = picked_meta.get(doc_id, "document")
            join_row = RequirementResponseDocument(
                id=uuid.uuid4(),
                response_id=submission.id,
                document_id=doc_id,
                filename=fname,
            )
            db.add(join_row)
            await grant_document_access_to_auditors(db, engagement_id, doc_id)

    await db.flush()
    return submission


async def enrich_requirements(
    db: AsyncSession, engagement_id: uuid.UUID, req_list: Sequence[RequirementRequest]
) -> list[dict]:
    """Build API dicts: submission rounds with their documents (filename, size,
    mime type), submission/document counts, linked-query counts, raiser and closer
    names, and the REQ-xxx display id. One batched query per concern — never N+1."""
    if not req_list:
        return []

    req_ids = [r.id for r in req_list]

    # Batch query responses and their documents
    res_resp = await db.execute(
        select(RequirementResponse)
        .options(selectinload(RequirementResponse.documents))
        .where(RequirementResponse.requirement_id.in_(req_ids))
        .order_by(RequirementResponse.round_number.desc(), RequirementResponse.created_at.desc())
    )
    all_responses = res_resp.scalars().all()

    # Collect document_ids to query version metadata
    doc_ids = {
        d.document_id
        for resp in all_responses
        for d in resp.documents
        if d.document_id is not None
    }
    doc_meta: dict[uuid.UUID, dict] = {}
    if doc_ids:
        doc_rows = (await db.execute(
            select(Document.id, DocumentVersion.size_bytes, DocumentVersion.mime_type)
            .join(DocumentVersion, DocumentVersion.id == Document.current_version_id, isouter=True)
            .where(Document.id.in_(doc_ids))
        )).all()
        doc_meta = {
            row[0]: {"size_bytes": row[1], "mime_type": row[2]}
            for row in doc_rows
        }

    # Query linked query counts
    q_counts = (await db.execute(
        select(Query.requirement_id, func.count(Query.id))
        .where(Query.requirement_id.in_(req_ids))
        .group_by(Query.requirement_id)
    )).all()
    count_map = {rid: cnt for rid, cnt in q_counts}

    # Batch query auditor names (for raised_by and closed_by)
    auditor_ids = {r.raised_by for r in req_list if r.raised_by} | {
        r.closed_by for r in req_list if r.closed_by
    }
    auditor_names: dict[uuid.UUID, str] = {}
    if auditor_ids:
        aud_rows = (await db.execute(
            select(Auditor.id, Auditor.name).where(Auditor.id.in_(auditor_ids))
        )).all()
        auditor_names = {row[0]: row[1] for row in aud_rows}

    # Batch query company user names (for responded_by)
    user_ids = {resp.responded_by for resp in all_responses if resp.responded_by}
    user_names: dict[uuid.UUID, str] = {}
    if user_ids:
        usr_rows = (await db.execute(
            select(CompanyUser.id, CompanyUser.full_name).where(CompanyUser.id.in_(user_ids))
        )).all()
        user_names = {row[0]: row[1] for row in usr_rows}

    # Group responses by requirement
    by_req: dict[uuid.UUID, list[dict]] = {}
    for resp in all_responses:
        doc_list = []
        for doc in resp.documents:
            meta = doc_meta.get(doc.document_id, {}) if doc.document_id else {}
            doc_list.append({
                "document_id": doc.document_id,
                "filename": doc.filename,
                "size_bytes": meta.get("size_bytes"),
                "mime_type": meta.get("mime_type"),
            })
        by_req.setdefault(resp.requirement_id, []).append({
            "id": resp.id,
            "requirement_id": resp.requirement_id,
            "round_number": resp.round_number,
            "responded_by": resp.responded_by,
            "responded_by_name": user_names.get(resp.responded_by),
            "text_answer": resp.text_answer,
            "created_at": resp.created_at,
            "documents": doc_list,
        })

    out = []
    for r in req_list:
        submissions = by_req.get(r.id, [])
        submission_count = len(submissions)
        document_count = sum(len(s["documents"]) for s in submissions)
        linked_query_count = count_map.get(r.id, 0)
        out.append({
            "id": r.id,
            "engagement_id": r.engagement_id,
            "raised_by": r.raised_by,
            "raised_by_name": auditor_names.get(r.raised_by),
            "seq_number": r.seq_number,
            "requirement_id_str": r.requirement_id,
            "description": r.description,
            "status": r.status,
            "priority": r.priority,
            "due_date": r.due_date,
            "closed_by": r.closed_by,
            "closed_by_name": auditor_names.get(r.closed_by) if r.closed_by else None,
            "closed_at": r.closed_at,
            "submissions": submissions,
            "submission_count": submission_count,
            "document_count": document_count,
            "linked_query_count": linked_query_count,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        })
    return out
