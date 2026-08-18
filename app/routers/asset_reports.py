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
from app.models.asset_masters import AssetLookup, ItAssetBlock
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
    db: AsyncSession, company_id: uuid.UUID, financial_year_id: uuid.UUID
):
    fy = await db.get(FinancialYear, financial_year_id)
    if not fy or fy.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")

    company = await db.get(Company, company_id)
    company_name = company.name if company else "Company"

    # Query all company assets with full relations
    stmt = (
        select(Asset)
        .where(Asset.company_id == company_id)
        .options(
            selectinload(Asset.category),
            selectinload(Asset.acquisition),
            selectinload(Asset.it_block),
        )
    )
    res = await db.execute(stmt)
    assets = list(res.scalars().all())
    assets_by_id = {str(a.id): a for a in assets}

    # Query lookups (locations, departments, etc.)
    lookup_stmt = select(AssetLookup).where(AssetLookup.company_id == company_id)
    lookup_res = await db.execute(lookup_stmt)
    lookups_by_id = {str(l.id): l.name for l in lookup_res.scalars().all()}

    # Query latest depreciation run for this FY
    run_stmt = (
        select(DepreciationRun)
        .where(
            and_(
                DepreciationRun.company_id == company_id,
                DepreciationRun.financial_year_id == financial_year_id,
            )
        )
        .options(
            selectinload(DepreciationRun.lines),
            selectinload(DepreciationRun.it_lines),
        )
        .order_by(DepreciationRun.run_date.desc())
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

    return {
        "fy": fy,
        "company_name": company_name,
        "assets": assets,
        "assets_by_id": assets_by_id,
        "lookups_by_id": lookups_by_id,
        "run": run,
        "dep_lines_by_asset_id": dep_lines_by_asset_id,
        "blocks_by_id": blocks_by_id,
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

    if report_key == REPORT_FIXED_ASSET_REGISTER:
        return build_fixed_asset_register_report(assets, dep_lines, co_name, fy.label, units, lookups_by_id=lookups_by_id)

    elif report_key == REPORT_COMPANIES_ACT_DEPRECIATION:
        if not run:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A depreciation run must be executed before generating the Companies Act Schedule II report.",
            )
        return build_companies_act_schedule_ii_report(run, assets_by_id, co_name, fy.label, units)

    elif report_key == REPORT_INCOME_TAX_DEPRECIATION:
        if not run:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A depreciation run must be executed before generating the Income Tax Section 32 report.",
            )
        return build_income_tax_appendix_i_report(run, co_name, fy.label, units)

    elif report_key == REPORT_IT_ASSET_ANNEXURE:
        return build_it_asset_annexure_report(assets, blocks_by_id, co_name, fy.label, fy.end_date, units)

    elif report_key == REPORT_ADDITIONS_REGISTER:
        return build_additions_register_report(assets, co_name, fy.label, fy.start_date, fy.end_date, units)

    elif report_key == REPORT_DISPOSALS_REGISTER:
        return build_disposals_register_report(assets, dep_lines, co_name, fy.label, fy.start_date, fy.end_date, units)

    elif report_key == REPORT_CWIP_REGISTER:
        return build_cwip_register_report(assets, co_name, fy.label, units)

    elif report_key == REPORT_DIMENSION_SUMMARY:
        return build_dimension_summary_report(assets, dep_lines, co_name, fy.label, units, lookups_by_id=lookups_by_id)

    elif report_key == REPORT_PHYSICAL_VERIFICATION:
        return build_physical_verification_report(assets, co_name, fy.label, lookups_by_id=lookups_by_id)

    elif report_key == REPORT_GST_ITC_SUMMARY:
        return build_gst_itc_summary_report(assets, co_name, fy.label, units)

    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown asset report key '{report_key}'",
        )


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
):
    ctx = await _load_asset_context(db, current_user.company_id, financial_year_id)
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
):
    ctx = await _load_asset_context(db, current_user.company_id, financial_year_id)
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
    for key, _, _ in ALL_ASSET_REPORTS:
        try:
            docs.append(_build_doc_by_key(key, ctx, units=unit))
        except HTTPException:
            # If a report (like Companies Act without a run) cannot be computed, skip gracefully in pack
            continue

    if not docs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No reports available for this pack")

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
):
    ctx = await _load_asset_context(db, current_user.company_id, financial_year_id)
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
