"""Live 'what does editing this master row affect?' analysis.

Finalized depreciation runs store snapshot lines, so a master edit can never
retroactively change history — effects classify exhaustively as `none`
(cosmetic, or defaults copied onto future assets only) or `future_only` (feeds
future run math). When finalized years were computed at values that differ from
the row's current state, the message says to reopen those years rather than
pretending nothing happened.
"""
import uuid
from typing import List, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import Asset, AssetAcquisition, AssetLifecycleStatus
from app.models.depreciation import (
    AssetDepreciationLine,
    DepreciationRun,
    DepreciationRunStatus,
    ItBlockDepreciationLine,
)
from app.schemas.asset_masters import ImpactPreviewResponse

Kind = Literal["category", "it_block", "supplier", "lookup"]

_NO_EFFECT_BY_KIND = {
    "category": (
        "No effect on existing assets — category defaults are copied onto new "
        "assets at creation only. Renames update register labels."
    ),
    "supplier": "Register labels update; GST snapshots on acquisitions stay as captured.",
    "lookup": "Register labels update for assets assigned to this value.",
}
_FUTURE_ONLY_MESSAGE = (
    "Future depreciation runs will use the new values. Finalized years keep "
    "their stored figures."
)
# The it_block branch below always assigns its own message, but the default
# lookup runs before branching — register the key so it can never KeyError.
_NO_EFFECT_BY_KIND["it_block"] = _FUTURE_ONLY_MESSAGE


async def compute_master_impact(
    db: AsyncSession, company_id: uuid.UUID, kind: Kind, row_id: uuid.UUID
) -> ImpactPreviewResponse:
    assets_referencing = await _count_referencing_assets(db, company_id, kind, row_id)
    draft_fys, final_fys = await _run_fys(db, company_id, kind, row_id)

    classification = "none"
    message = _NO_EFFECT_BY_KIND[kind]

    if kind == "it_block":
        classification = "future_only"
        message = _FUTURE_ONLY_MESSAGE
        if final_fys:
            rates = (
                await db.execute(
                    select(ItBlockDepreciationLine.prescribed_rate)
                    .join(DepreciationRun, DepreciationRun.id == ItBlockDepreciationLine.run_id)
                    .where(
                        DepreciationRun.company_id == company_id,
                        ItBlockDepreciationLine.it_block_id == row_id,
                        DepreciationRun.status == DepreciationRunStatus.finalized.value,
                    )
                )
            ).scalars().all()
            rates_txt = ", ".join(f"{float(r):g}%" for r in sorted(set(rates)))
            message = (
                f"Finalized years ({', '.join(sorted(final_fys))}) were computed at "
                f"{rates_txt}. Future runs will use the new value — if the old rate "
                f"was wrong, reopen those years after saving."
            )
    elif kind == "lookup" and assets_referencing:
        classification = "future_only"
        message = _FUTURE_ONLY_MESSAGE

    return ImpactPreviewResponse(
        kind=kind,
        id=row_id,
        assets_referencing=assets_referencing,
        draft_run_fy_labels=sorted(draft_fys),
        finalized_run_fy_labels=sorted(final_fys),
        classification=classification,
        message=message,
    )


async def _count_referencing_assets(db: AsyncSession, company_id, kind, row_id) -> int:
    if kind == "category":
        cond = Asset.category_id == row_id
        base = Asset
    elif kind == "it_block":
        cond = Asset.it_block_id == row_id
        base = Asset
    elif kind == "supplier":
        return (await db.execute(
            select(func.count()).select_from(AssetAcquisition).where(
                AssetAcquisition.company_id == company_id,
                AssetAcquisition.supplier_id == row_id,
            )
        )).scalar_one()
    else:  # lookup: any dimension FK
        return (await db.execute(
            select(func.count()).select_from(Asset).where(
                Asset.company_id == company_id,
                or_(Asset.branch_id == row_id, Asset.location_id == row_id,
                    Asset.department_id == row_id, Asset.cost_centre_id == row_id),
            )
        )).scalar_one()

    return (await db.execute(
        select(func.count()).select_from(base).where(
            Asset.company_id == company_id, cond,
            Asset.lifecycle_status != AssetLifecycleStatus.draft,
        )
    )).scalar_one()


async def _run_fys(db: AsyncSession, company_id, kind, row_id):
    """(draft labels, finalized labels) of runs whose lines reference this row.

    Category lines are per-asset, so they join through Asset; block lines carry
    it_block_id directly.
    """
    if kind not in ("category", "it_block"):
        return [], []

    if kind == "category":
        run_ids = (await db.execute(
            select(AssetDepreciationLine.run_id)
            .join(Asset, Asset.id == AssetDepreciationLine.asset_id)
            .where(Asset.company_id == company_id, Asset.category_id == row_id)
            .distinct()
        )).scalars().all()
    else:
        run_ids = (await db.execute(
            select(ItBlockDepreciationLine.run_id)
            .join(DepreciationRun, DepreciationRun.id == ItBlockDepreciationLine.run_id)
            .where(DepreciationRun.company_id == company_id,
                   ItBlockDepreciationLine.it_block_id == row_id)
            .distinct()
        )).scalars().all()

    if not run_ids:
        return [], []

    from app.models.financial_year import FinancialYear

    rows = (await db.execute(
        select(DepreciationRun.status, FinancialYear.label)
        .join(FinancialYear, FinancialYear.id == DepreciationRun.financial_year_id)
        .where(DepreciationRun.id.in_(run_ids))
    )).all()

    drafts = [label for status, label in rows if status == DepreciationRunStatus.draft.value]
    finals = [label for status, label in rows if status == DepreciationRunStatus.finalized.value]
    return drafts, finals
