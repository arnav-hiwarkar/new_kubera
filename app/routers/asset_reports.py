"""Asset Register Reporting API endpoints.

Generates XLSX, PDF, and HTML statutory fixed-asset and depreciation reports:
- Fixed Asset Register
- Companies Act / Schedule II PPE statement
- Income Tax Act Section 32 schedule
- IT asset annexure
- Additions register
- Disposals register
- CWIP / uncapitalized register
- Dimension summary
- Physical verification sheet
- GST & ITC summary
"""
import io
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_company_user, require_assets_module
from app.database import get_db
from app.models.assets import Asset, AssetLifecycleStatus
from app.models.asset_masters import AssetCategory, AssetLookup, ItAssetBlock
from app.models.company import Company, CompanyUser
from app.models.depreciation import DepreciationRun, AssetDepreciationLine
from app.models.financial_year import FinancialYear
from app.services.reporting.asset_reports import (
    ALL_ASSET_REPORTS,
    REPORT_FIXED_ASSET_REGISTER,
    REPORT_COMPANIES_ACT_DEPRECIATION,
    REPORT_INCOME_TAX_DEPRECIATION,
    REPORT_IT_ASSET_ANNEXURE,
    REPORT_ADDITIONS_REGISTER,
    REPORT_DISPOSALS_REGISTER,
    REPORT_CWIP_REGISTER,
    REPORT_DIMENSION_SUMMARY,
    REPORT_PHYSICAL_VERIFICATION,
    REPORT_GST_ITC_SUMMARY,
    build_fixed_asset_register_report,
    build_companies_act_schedule_ii_report,
    build_income_tax_appendix_i_report,
    build_it_asset_annexure_report,
    build_additions_register_report,
    build_disposals_register_report,
    build_cwip_register_report,
    build_dimension_summary_report,
    build_physical_verification_report,
    build_gst_itc_summary_report,
)
from app.services.reporting.document import ReportDocument
from app.services.reporting.pdf import render_html, render_pdf, render_pack_pdf
from app.services.reporting.vault import archive_report
from app.services.reporting.workbook import write_document, write_workbook

router = APIRouter(prefix="/api/v1/asset-reports", tags=["asset-reports"])


async def _load_asset_context(
    db: AsyncSession,
    company_id: uuid.UUID,
    financial_year_id: uuid.UUID,
    report_key: Optional[str] = None,
    lifecycle_status: Optional[str] = None,
    operational_status: Optional[str] = None,
    condition: Optional[str] = None,
    category_id: Optional[uuid.UUID] = None,
    location_id: Optional[uuid.UUID] = None,
    branch_id: Optional[uuid.UUID] = None,
    custodian_id: Optional[uuid.UUID] = None,
    acquisition_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    fy = await db.get(FinancialYear, financial_year_id)
    if not fy or fy.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    company = await db.get(Company, company_id)
    company_name = company.name if company else "Company"

    # Default Fixed Asset Register and Dimension Summary to capitalized unless overridden
    effective_lifecycle_status = lifecycle_status
    if effective_lifecycle_status is None and report_key in (REPORT_FIXED_ASSET_REGISTER, REPORT_DIMENSION_SUMMARY):
        effective_lifecycle_status = AssetLifecycleStatus.capitalized.value

    # Query lookups (locations, departments, etc.)
    lookup_stmt = select(AssetLookup).where(AssetLookup.company_id == company_id)
    lookup_res = await db.execute(lookup_stmt)
    lookups_by_id = {str(l.id): l.name for l in lookup_res.scalars().all()}

    # Build asset query with filters
    stmt = (
        select(Asset)
        .where(Asset.company_id == company_id)
        .options(
            selectinload(Asset.category),
            selectinload(Asset.acquisition),
            selectinload(Asset.it_block),
            selectinload(Asset.disposed_by_user),
        )
    )
    for column, value in (
        (Asset.lifecycle_status, effective_lifecycle_status),
        (Asset.operational_status, operational_status),
        (Asset.condition, condition),
        (Asset.category_id, category_id),
        (Asset.location_id, location_id),
        (Asset.branch_id, branch_id),
        (Asset.custodian_id, custodian_id),
        (Asset.acquisition_id, acquisition_id),
    ):
        if value is not None:
            stmt = stmt.where(column == value)

    res = await db.execute(stmt)
    assets = list(res.scalars().all())
    assets_by_id = {str(a.id): a for a in assets}

    # Query latest finalized depreciation run for this FY
    run_stmt = (
        select(DepreciationRun)
        .where(
            and_(
                DepreciationRun.company_id == company_id,
                DepreciationRun.financial_year_id == financial_year_id,
                DepreciationRun.status == "finalized",
            )
        )
        .options(
            selectinload(DepreciationRun.lines),
            selectinload(DepreciationRun.it_lines),
        )
        .order_by(DepreciationRun.finalized_at.desc())
    )
    run_res = await db.execute(run_stmt)
    run = run_res.scalars().first()

    dep_lines_by_asset_id: Dict[str, AssetDepreciationLine] = {}
    if run:
        for l in run.lines:
            dep_lines_by_asset_id[str(l.asset_id)] = l

    # Query IT blocks
    block_stmt = select(ItAssetBlock).where(
        or_(ItAssetBlock.company_id == company_id, ItAssetBlock.company_id.is_(None))
    )
    block_res = await db.execute(block_stmt)
    blocks_by_id = {str(b.id): b for b in block_res.scalars().all()}

    # Format applied filters summary for subtitle
    filters_applied = []
    if effective_lifecycle_status:
        filters_applied.append(f"Status: {effective_lifecycle_status}")
    if operational_status:
        filters_applied.append(f"Operation: {operational_status}")
    if condition:
        filters_applied.append(f"Condition: {condition}")
    if category_id:
        cat_name = next((a.category.name for a in assets if a.category and a.category_id == category_id), None)
        if not cat_name:
            cat_obj = await db.get(AssetCategory, category_id)
            cat_name = cat_obj.name if cat_obj else str(category_id)
        filters_applied.append(f"Category: {cat_name}")
    if location_id:
        loc_name = lookups_by_id.get(str(location_id), str(location_id))
        filters_applied.append(f"Location: {loc_name}")
    if branch_id:
        br_name = lookups_by_id.get(str(branch_id), str(branch_id))
        filters_applied.append(f"Branch: {br_name}")
    if custodian_id:
        cust_name = lookups_by_id.get(str(custodian_id), str(custodian_id))
        filters_applied.append(f"Custodian: {cust_name}")
    if acquisition_id:
        filters_applied.append(f"Acquisition: {acquisition_id}")

    filter_desc = ", ".join(filters_applied) if filters_applied else None

    return {
        "fy": fy,
        "company_name": company_name,
        "assets": assets,
        "assets_by_id": assets_by_id,
        "lookups_by_id": lookups_by_id,
        "run": run,
        "dep_lines_by_asset_id": dep_lines_by_asset_id,
        "blocks_by_id": blocks_by_id,
        "filter_desc": filter_desc,
    }


def _build_doc_by_key(report_key: str, ctx: Dict[str, Any], units: str = "absolute") -> ReportDocument:
    fy: FinancialYear = ctx["fy"]
    co_name: str = ctx["company_name"]
    assets: List[Asset] = ctx["assets"]
    assets_by_id: Dict[str, Asset] = ctx["assets_by_id"]
    lookups_by_id: Dict[str, str] = ctx["lookups_by_id"]
    run: Optional[DepreciationRun] = ctx["run"]
    dep_lines = ctx["dep_lines_by_asset_id"]
    blocks_by_id = ctx["blocks_by_id"]
    filter_desc: Optional[str] = ctx.get("filter_desc")

    doc: ReportDocument

    if report_key == REPORT_FIXED_ASSET_REGISTER:
        doc = build_fixed_asset_register_report(assets, dep_lines, co_name, fy.label, units, lookups_by_id=lookups_by_id)

    elif report_key == REPORT_COMPANIES_ACT_DEPRECIATION:
        if not run:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No finalized depreciation run exists for {fy.label}. Run and finalize depreciation before generating this report.",
            )
        doc = build_companies_act_schedule_ii_report(run, assets_by_id, co_name, fy.label, units)

    elif report_key == REPORT_INCOME_TAX_DEPRECIATION:
        if not run:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No finalized depreciation run exists for {fy.label}. Run and finalize depreciation before generating this report.",
            )
        doc = build_income_tax_appendix_i_report(run, co_name, fy.label, units)

    elif report_key == REPORT_IT_ASSET_ANNEXURE:
        if not run:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No finalized depreciation run exists for {fy.label}. Run and finalize depreciation before generating this report.",
            )
        doc = build_it_asset_annexure_report(assets, blocks_by_id, co_name, fy.label, fy.end_date, units)

    elif report_key == REPORT_ADDITIONS_REGISTER:
        doc = build_additions_register_report(assets, co_name, fy.label, fy.start_date, fy.end_date, units)

    elif report_key == REPORT_DISPOSALS_REGISTER:
        doc = build_disposals_register_report(assets, dep_lines, co_name, fy.label, fy.start_date, fy.end_date, units)

    elif report_key == REPORT_CWIP_REGISTER:
        doc = build_cwip_register_report(assets, co_name, fy.label, units)

    elif report_key == REPORT_DIMENSION_SUMMARY:
        doc = build_dimension_summary_report(assets, dep_lines, co_name, fy.label, units, lookups_by_id=lookups_by_id)

    elif report_key == REPORT_PHYSICAL_VERIFICATION:
        doc = build_physical_verification_report(assets, co_name, fy.label, lookups_by_id=lookups_by_id)

    elif report_key == REPORT_GST_ITC_SUMMARY:
        doc = build_gst_itc_summary_report(assets, co_name, fy.label, units)

    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown asset report key '{report_key}'",
        )

    if filter_desc and report_key in (REPORT_FIXED_ASSET_REGISTER, REPORT_DIMENSION_SUMMARY):
        new_subtitle = f"{doc.subtitle} | Filters: {filter_desc}" if doc.subtitle else f"Filters: {filter_desc}"
        doc = replace(doc, subtitle=new_subtitle)

    return doc


@router.get("", response_model=List[Dict[str, str]])
async def list_available_asset_reports(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
):
    """Returns the list of 10 available asset register reports and descriptions."""
    return [
        {"key": key, "title": title, "description": desc}
        for key, title, desc in ALL_ASSET_REPORTS
    ]


@router.get("/{report_key}/export")
async def export_asset_report(
    report_key: str,
    financial_year_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query("xlsx", pattern="^(xlsx|pdf|html)$"),
    unit: str = Query("absolute", pattern="^(absolute|thousands|lakhs|crores)$"),
    lifecycle_status: Optional[str] = None,
    operational_status: Optional[str] = None,
    condition: Optional[str] = None,
    category_id: Optional[uuid.UUID] = None,
    location_id: Optional[uuid.UUID] = None,
    branch_id: Optional[uuid.UUID] = None,
    custodian_id: Optional[uuid.UUID] = None,
    acquisition_id: Optional[uuid.UUID] = None,
):
    ctx = await _load_asset_context(
        db,
        current_user.company_id,
        financial_year_id,
        report_key=report_key,
        lifecycle_status=lifecycle_status,
        operational_status=operational_status,
        condition=condition,
        category_id=category_id,
        location_id=location_id,
        branch_id=branch_id,
        custodian_id=custodian_id,
        acquisition_id=acquisition_id,
    )
    doc = _build_doc_by_key(report_key, ctx, units=unit)

    filename_base = f"{report_key}_{ctx['fy'].label.replace('/', '_')}"

    if format == "xlsx":
        stream = write_document(doc)
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.xlsx"'},
        )
    elif format == "pdf":
        pdf_bytes = render_pdf(doc)
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.pdf"'},
        )
    elif format == "html":
        html_content = render_html(doc)
        return HTMLResponse(content=html_content)


@router.get("/{report_key}/preview-html", response_class=HTMLResponse)
async def preview_asset_report_html(
    report_key: str,
    financial_year_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    unit: str = Query("absolute", pattern="^(absolute|thousands|lakhs|crores)$"),
    lifecycle_status: Optional[str] = None,
    operational_status: Optional[str] = None,
    condition: Optional[str] = None,
    category_id: Optional[uuid.UUID] = None,
    location_id: Optional[uuid.UUID] = None,
    branch_id: Optional[uuid.UUID] = None,
    custodian_id: Optional[uuid.UUID] = None,
    acquisition_id: Optional[uuid.UUID] = None,
):
    ctx = await _load_asset_context(
        db,
        current_user.company_id,
        financial_year_id,
        report_key=report_key,
        lifecycle_status=lifecycle_status,
        operational_status=operational_status,
        condition=condition,
        category_id=category_id,
        location_id=location_id,
        branch_id=branch_id,
        custodian_id=custodian_id,
        acquisition_id=acquisition_id,
    )
    doc = _build_doc_by_key(report_key, ctx, units=unit)
    return HTMLResponse(content=render_html(doc))


@router.post("/pack")
async def export_asset_report_pack(
    financial_year_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    unit: str = Query("absolute", pattern="^(absolute|thousands|lakhs|crores)$"),
):
    ctx = await _load_asset_context(db, current_user.company_id, financial_year_id)

    docs: List[ReportDocument] = []
    omissions: List[str] = []
    for key, title, _ in ALL_ASSET_REPORTS:
        try:
            docs.append(_build_doc_by_key(key, ctx, units=unit))
        except HTTPException as e:
            if e.status_code == status.HTTP_409_CONFLICT:
                omissions.append(f"{title}: {e.detail}")
            else:
                raise

    if not docs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No reports available for this pack")

    if omissions and docs:
        first_doc = docs[0]
        new_warnings = tuple(list(first_doc.warnings) + [f"Omitted from pack — {om}" for om in omissions])
        docs[0] = replace(first_doc, warnings=new_warnings)

    filename_base = f"Asset_Register_Pack_{ctx['fy'].label.replace('/', '_')}"

    if format == "xlsx":
        sheets = [(d.title, d) for d in docs]
        stream = write_workbook(sheets)
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.xlsx"'},
        )
    elif format == "pdf":
        pdf_bytes = render_pack_pdf(docs, pack_title=f"Asset Register Pack — {ctx['fy'].label}")
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.pdf"'},
        )


@router.post("/archive")
async def archive_asset_report(
    report_key: str,
    financial_year_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query("pdf", pattern="^(xlsx|pdf)$"),
    unit: str = Query("absolute", pattern="^(absolute|thousands|lakhs|crores)$"),
    lifecycle_status: Optional[str] = None,
    operational_status: Optional[str] = None,
    condition: Optional[str] = None,
    category_id: Optional[uuid.UUID] = None,
    location_id: Optional[uuid.UUID] = None,
    branch_id: Optional[uuid.UUID] = None,
    custodian_id: Optional[uuid.UUID] = None,
    acquisition_id: Optional[uuid.UUID] = None,
):
    ctx = await _load_asset_context(
        db,
        current_user.company_id,
        financial_year_id,
        report_key=report_key,
        lifecycle_status=lifecycle_status,
        operational_status=operational_status,
        condition=condition,
        category_id=category_id,
        location_id=location_id,
        branch_id=branch_id,
        custodian_id=custodian_id,
        acquisition_id=acquisition_id,
    )
    doc = _build_doc_by_key(report_key, ctx, units=unit)

    safe_period = ctx["fy"].label.replace("/", "_").replace(" ", "_")
    if format == "pdf":
        content = render_pdf(doc)
        filename = f"{report_key}_{safe_period}.pdf"
        mime_type = "application/pdf"
    else:
        stream = write_document(doc)
        content = stream.getvalue()
        filename = f"{report_key}_{safe_period}.xlsx"
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    record = await archive_report(
        db=db,
        company_id=current_user.company_id,
        user_id=current_user.id,
        bucket_name="Asset Register Reports",
        filename=filename,
        content=content,
        mime_type=mime_type,
    )
    return {"status": "archived", "document_id": str(record.id), "title": record.title}

