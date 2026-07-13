import uuid
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_company_user
from app.models.company import CompanyUser
from app.models.compliance import ComplianceDomain, DocumentType, MeetingRecord
from app.schemas.compliance import DocumentTypeCreate, DocumentTypeResponse, MeetingRecordCreate, MeetingRecordResponse


def create_compliance_router(domain: ComplianceDomain, prefix: str, tags: List[str]) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags)

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
            
        await db.delete(db_dt)
        await db.commit()
        return {"message": "Deleted"}

    @router.post("/meeting-records", response_model=MeetingRecordResponse, status_code=status.HTTP_201_CREATED)
    async def create_meeting_record(
        record: MeetingRecordCreate,
        current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
        db: Annotated[AsyncSession, Depends(get_db)]
    ):
        # Validate doc type exists for this domain
        dt_res = await db.execute(select(DocumentType).where(and_(DocumentType.id == record.doc_type_id, DocumentType.domain == domain)))
        if not dt_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid document type for this domain")
            
        db_rec = MeetingRecord(
            company_id=current_user.company_id,
            doc_type_id=record.doc_type_id,
            document_id=record.document_id,
            structured_metadata=record.structured_metadata
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
            select(MeetingRecord)
            .join(DocumentType, MeetingRecord.doc_type_id == DocumentType.id)
            .where(
                and_(
                    MeetingRecord.company_id == current_user.company_id,
                    DocumentType.domain == domain
                )
            )
        )
        return result.scalars().all()

    return router


secretarial_router = create_compliance_router(ComplianceDomain.secretarial, "/api/v1/secretarial", ["secretarialease"])
roc_router = create_compliance_router(ComplianceDomain.roc, "/api/v1/roc", ["roc-compliance"])
