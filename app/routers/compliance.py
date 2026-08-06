import uuid
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_company_user, require_module
from app.models.company import CompanyUser
from sqlalchemy import func
from app.models.compliance import ComplianceDomain, DocumentType, MeetingRecord
from app.models.docvault import Document, DocumentStatus, DocumentVersion
from app.schemas.compliance import (
    BucketRefResponse,
    DocumentTypeCreate,
    DocumentTypeResponse,
    MeetingRecordCreate,
    MeetingRecordResponse,
    MeetingRecordUpdate,
    SyncResultResponse,
    UnsyncedDocumentResponse,
)
from app.services.compliance_bucket import ensure_compliance_bucket, find_compliance_bucket


def create_compliance_router(domain: ComplianceDomain, prefix: str, tags: List[str]) -> APIRouter:
    router = APIRouter(
        prefix=prefix,
        tags=tags,
        dependencies=[Depends(require_module(domain.value))],
    )

    @router.post("/document-types", response_model=DocumentTypeResponse, status_code=status.HTTP_201_CREATED)
    async def create_document_type(
        dt: DocumentTypeCreate,
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        db_dt = DocumentType(
            company_id=current_user.company_id,
            domain=domain,
            name=dt.name,
            template_file_id=dt.template_file_id,
            metadata_schema=dt.metadata_schema,
            due_date_rule=dt.due_date_rule
        )
        db.add(db_dt)
        await db.commit()
        await db.refresh(db_dt)
        return db_dt

    @router.get("/document-types", response_model=List[DocumentTypeResponse])
    async def list_document_types(
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        # Fetch both system-shipped (company_id=None) and company-owned
        result = await db.execute(
            select(DocumentType).where(
                and_(
                    DocumentType.domain == domain,
                    or_(DocumentType.company_id.is_(None), DocumentType.company_id == current_user.company_id)
                )
            )
        )
        return result.scalars().all()

    @router.put("/document-types/{dt_id}", response_model=DocumentTypeResponse)
    async def update_document_type(
        dt_id: uuid.UUID,
        dt_update: DocumentTypeCreate,
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        result = await db.execute(select(DocumentType).where(and_(DocumentType.id == dt_id, DocumentType.company_id == current_user.company_id, DocumentType.domain == domain)))
        db_dt = result.scalar_one_or_none()
        if not db_dt:
            raise HTTPException(status_code=404, detail="Document type not found or not owned by company")
            
        db_dt.name = dt_update.name
        db_dt.template_file_id = dt_update.template_file_id
        db_dt.metadata_schema = dt_update.metadata_schema
        db_dt.due_date_rule = dt_update.due_date_rule
        
        await db.commit()
        await db.refresh(db_dt)
        return db_dt

    @router.delete("/document-types/{dt_id}")
    async def delete_document_type(
        dt_id: uuid.UUID,
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        result = await db.execute(select(DocumentType).where(and_(DocumentType.id == dt_id, DocumentType.company_id == current_user.company_id, DocumentType.domain == domain)))
        db_dt = result.scalar_one_or_none()
        if not db_dt:
            raise HTTPException(status_code=404, detail="Document type not found or not owned by company")

        # Guard: a type with records can't be hard-deleted (would orphan/FK-break them).
        count_res = await db.execute(
            select(func.count()).select_from(MeetingRecord).where(MeetingRecord.doc_type_id == dt_id)
        )
        if count_res.scalar_one() > 0:
            raise HTTPException(status_code=409, detail="This document type has records — remove them first.")

        await db.delete(db_dt)
        await db.commit()
        return {"message": "Deleted"}

    async def _validate_doc_type(db: AsyncSession, company_id: uuid.UUID, doc_type_id: uuid.UUID) -> None:
        """A usable type is in this domain and either company-owned or system-shipped."""
        res = await db.execute(
            select(DocumentType.id).where(
                and_(
                    DocumentType.id == doc_type_id,
                    DocumentType.domain == domain,
                    or_(DocumentType.company_id.is_(None), DocumentType.company_id == company_id),
                )
            )
        )
        if not res.first():
            raise HTTPException(status_code=400, detail="Invalid document type for this domain")

    async def _unsynced_documents(db: AsyncSession, company_id: uuid.UUID) -> list[tuple]:
        """Live documents in the domain's bucket that no record points at yet.

        Returns (Document, DocumentVersion|None) rows. The bucket may not exist
        yet, in which case there is trivially nothing to sync.
        """
        bucket = await find_compliance_bucket(db, company_id, domain)
        if not bucket:
            return []

        claimed = (
            select(MeetingRecord.document_id)
            .where(
                and_(
                    MeetingRecord.company_id == company_id,
                    MeetingRecord.domain == domain,
                    MeetingRecord.document_id.is_not(None),
                )
            )
            .scalar_subquery()
        )
        result = await db.execute(
            select(Document, DocumentVersion)
            .outerjoin(DocumentVersion, DocumentVersion.id == Document.current_version_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.bucket_id == bucket.id,
                    Document.status != DocumentStatus.archived,
                    Document.id.not_in(claimed),
                )
            )
            .order_by(Document.created_at)
        )
        return list(result.all())

    @router.get("/bucket", response_model=BucketRefResponse)
    async def get_domain_bucket(
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        """The docVault bucket this domain files into, created on first ask."""
        bucket = await ensure_compliance_bucket(db, current_user.company_id, domain, current_user.id)
        await db.commit()
        await db.refresh(bucket)
        return bucket

    @router.post("/meeting-records", response_model=MeetingRecordResponse, status_code=status.HTTP_201_CREATED)
    async def create_meeting_record(
        record: MeetingRecordCreate,
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        # A record may be staged without a type; validate one only if given.
        if record.doc_type_id is not None:
            await _validate_doc_type(db, current_user.company_id, record.doc_type_id)

        db_rec = MeetingRecord(
            company_id=current_user.company_id,
            domain=domain,
            doc_type_id=record.doc_type_id,
            title=record.title,
            document_id=record.document_id,
            structured_metadata=record.structured_metadata,
            record_date=record.record_date
        )
        db.add(db_rec)
        await db.commit()
        await db.refresh(db_rec)
        return db_rec

    @router.get("/meeting-records", response_model=List[MeetingRecordResponse])
    async def list_meeting_records(
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        result = await db.execute(
            select(MeetingRecord).where(
                and_(
                    MeetingRecord.company_id == current_user.company_id,
                    MeetingRecord.domain == domain
                )
            )
        )
        return result.scalars().all()

    @router.get("/meeting-records/unsynced", response_model=List[UnsyncedDocumentResponse])
    async def list_unsynced_documents(
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        rows = await _unsynced_documents(db, current_user.company_id)
        return [
            UnsyncedDocumentResponse(
                id=doc.id,
                title=doc.title,
                original_filename=version.original_filename if version else None,
                size_bytes=version.size_bytes if version else None,
                uploaded_at=version.uploaded_at if version else None,
            )
            for doc, version in rows
        ]

    @router.post("/meeting-records/sync", response_model=SyncResultResponse)
    async def sync_from_docvault(
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        """Import every unclaimed bucket document as an untyped record.

        Additive only: existing records are never updated or removed, so running
        this twice in a row imports nothing the second time.
        """
        rows = await _unsynced_documents(db, current_user.company_id)
        created: list[MeetingRecord] = []
        for doc, version in rows:
            rec = MeetingRecord(
                company_id=current_user.company_id,
                domain=domain,
                doc_type_id=None,
                title=doc.title,
                document_id=doc.id,
                structured_metadata=None,
                record_date=doc.created_at.date() if doc.created_at else None,
            )
            db.add(rec)
            created.append(rec)
        await db.commit()
        for rec in created:
            await db.refresh(rec)
        return SyncResultResponse(imported=len(created), records=created)

    @router.patch("/meeting-records/{record_id}", response_model=MeetingRecordResponse)
    async def update_meeting_record(
        record_id: uuid.UUID,
        update: MeetingRecordUpdate,
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        result = await db.execute(
            select(MeetingRecord).where(
                and_(
                    MeetingRecord.id == record_id,
                    MeetingRecord.company_id == current_user.company_id,
                    MeetingRecord.domain == domain,
                )
            )
        )
        db_rec = result.scalar_one_or_none()
        if not db_rec:
            raise HTTPException(status_code=404, detail="Record not found")

        fields = update.model_dump(exclude_unset=True)
        if fields.get("doc_type_id") is not None:
            await _validate_doc_type(db, current_user.company_id, fields["doc_type_id"])
        for key, value in fields.items():
            setattr(db_rec, key, value)

        await db.commit()
        await db.refresh(db_rec)
        return db_rec

    return router


secretarial_router = create_compliance_router(ComplianceDomain.secretarial, "/api/v1/secretarial", ["secretarialease"])
roc_router = create_compliance_router(ComplianceDomain.roc, "/api/v1/roc", ["roc-compliance"])
