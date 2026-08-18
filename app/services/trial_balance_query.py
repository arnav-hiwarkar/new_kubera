"""Thin async layer between the database and the pure `trial_balance` core.

`load_engagement_figures` is the SINGLE implementation behind every place that
needs trial-balance totals: the company TB endpoint, the auditor TB endpoint, the
report preview, the report generator, the import result and the sign-convention
repair endpoint. Nothing in the frontend computes a subtotal, and no second
implementation exists to drift from this one.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auditease import (
    AuditEngagement, AuditEntry, AuditEntryLine, AuditEntryStatus,
    BalanceNature, EntryLineSide, TBSignConvention, TrialBalanceAccount,
)
from app.schemas.auditease import TBGroupSubtotalResponse, TBTotalsResponse
from app.services import ledger_groups as lg
from app.services import trial_balance as tb


@dataclass
class EngagementFigures:
    accounts: list[TrialBalanceAccount]
    figures: list[tb.LedgerFigure]
    summary: tb.TBSummary
    adjustments: dict[uuid.UUID, Decimal]
    index: lg.GroupIndex
    approved_entries: list[AuditEntry]
    proposed_count: int


async def load_adjustments(
    db: AsyncSession, engagement_id: uuid.UUID
) -> tuple[dict[uuid.UUID, Decimal], list[AuditEntry], int]:
    """Net-debit adjustment per ledger from APPROVED entries only."""
    res = await db.execute(
        select(AuditEntry)
        .options(selectinload(AuditEntry.lines).selectinload(AuditEntryLine.ledger))
        .where(and_(AuditEntry.engagement_id == engagement_id,
                    AuditEntry.status == AuditEntryStatus.approved))
        .order_by(AuditEntry.created_at.asc())
    )
    approved = list(res.scalars().all())

    proposed_res = await db.execute(
        select(AuditEntry.id).where(and_(
            AuditEntry.engagement_id == engagement_id,
            AuditEntry.status == AuditEntryStatus.proposed,
        ))
    )
    proposed_count = len(proposed_res.scalars().all())

    adjustments: dict[uuid.UUID, Decimal] = {}
    for entry in approved:
        for line in entry.lines:
            amount = tb.to_decimal(line.amount)
            delta = amount if line.side == EntryLineSide.debit else -amount
            adjustments[line.ledger_id] = adjustments.get(line.ledger_id, Decimal(0)) + delta
    return adjustments, approved, proposed_count


async def load_engagement_figures(
    db: AsyncSession,
    company_id: uuid.UUID,
    engagement_id: uuid.UUID,
    *,
    include_adjustments: bool = True,
) -> EngagementFigures:
    res = await db.execute(
        select(TrialBalanceAccount)
        .where(TrialBalanceAccount.engagement_id == engagement_id)
        .order_by(TrialBalanceAccount.ledger_name)
    )
    accounts = list(res.scalars().all())
    index = await lg.resolve_group_index(db, company_id)

    if include_adjustments:
        adjustments, approved, proposed_count = await load_adjustments(db, engagement_id)
    else:
        adjustments, approved, proposed_count = {}, [], 0

    figures = tb.build_figures(accounts, index.paths, index.natures, adjustments)
    summary = tb.summarize(figures)
    attach_view_fields(accounts, index)
    attach_figure_fields(accounts, figures)
    return EngagementFigures(
        accounts=accounts,
        figures=figures,
        summary=summary,
        adjustments=adjustments,
        index=index,
        approved_entries=approved,
        proposed_count=proposed_count,
    )


def attach_view_fields(
    accounts: Iterable[TrialBalanceAccount], index: lg.GroupIndex
) -> None:
    """Set the transient fields the response schema reads off the ORM instance."""
    for acc in accounts:
        gid = acc.mapped_group_id
        acc.mapped_group_path = index.paths.get(gid) if gid else None  # type: ignore[attr-defined]
        acc.nature = index.natures.get(gid) if gid else None  # type: ignore[attr-defined]


def attach_figure_fields(
    accounts: Iterable[TrialBalanceAccount], figures: Sequence[tb.LedgerFigure]
) -> None:
    """Attach the exact adjusted/presented values used by the shared summary."""
    by_id = {f.ledger_id: f for f in figures if f.ledger_id is not None}
    for acc in accounts:
        figure = by_id.get(acc.id)
        if figure is None:
            continue
        acc.adjustment_net_debit = figure.adjustment  # type: ignore[attr-defined]
        acc.final_net_debit = figure.final_net_debit  # type: ignore[attr-defined]
        acc.presented_opening = tb.present(  # type: ignore[attr-defined]
            figure.opening_net_debit, figure.nature
        )
        acc.presented_closing = figure.presented_closing  # type: ignore[attr-defined]
        acc.presented_adjustment = tb.present(  # type: ignore[attr-defined]
            figure.adjustment, figure.nature
        )
        acc.presented_final = figure.presented_final  # type: ignore[attr-defined]


def totals_response(summary: tb.TBSummary) -> TBTotalsResponse:
    return TBTotalsResponse(
        groups=[
            TBGroupSubtotalResponse(
                key=g.key, nature=g.nature,
                opening_net_debit=float(g.opening_net_debit),
                presented_opening=float(g.presented_opening),
                debit=float(g.debit_movement),
                credit=float(g.credit_movement),
                closing_net_debit=float(g.closing_net_debit),
                presented_closing=float(g.presented_closing),
                adjustment_net_debit=float(g.adjustment_net_debit),
                presented_adjustment=float(g.presented_adjustment),
                final_net_debit=float(g.final_net_debit),
                presented_final=float(g.presented_final),
                net_debit=float(g.net_debit), presented=float(g.presented),
                ledger_count=g.ledger_count,
            )
            for g in summary.groups
        ],
        assets=float(summary.assets),
        liabilities=float(summary.liabilities),
        income=float(summary.income),
        expenditure=float(summary.expenditure),
        equity=float(summary.equity),
        net_profit=float(summary.net_profit),
        liabilities_plus_equity=float(summary.liabilities_plus_equity),
        difference=float(summary.difference),
        difference_including_unmapped=float(summary.difference_including_unmapped),
        balanced=summary.balanced,
        unmapped_net_debit=float(summary.unmapped_net_debit),
        unmapped_count=summary.unmapped_count,
        unresolved_nature_count=summary.unresolved_nature_count,
        sign_unresolved_count=summary.sign_unresolved_count,
        ledger_count=summary.ledger_count,
        mapped_count=summary.mapped_count,
        statement_ready=summary.statement_ready,
        total_debit=float(summary.total_debit_movement),
        total_credit=float(summary.total_credit_movement),
        movement_balanced=tb.is_zero(
            summary.total_debit_movement - summary.total_credit_movement
        ),
    )


def view_warnings(
    figures: Sequence[tb.LedgerFigure],
    summary: tb.TBSummary,
    convention: TBSignConvention | None,
) -> list[str]:
    warnings: list[str] = []
    if convention is None and summary.ledger_count:
        warnings.append(
            "The sign convention for this trial balance has not been confirmed. "
            "Statement figures may be wrong until it is."
        )
    if summary.sign_unresolved_count:
        warnings.append(
            f"{summary.sign_unresolved_count} ledger(s) have an unresolved Dr/Cr sign. "
            "Map them, or confirm the sign convention."
        )
    if summary.unmapped_count:
        from app.services.reporting.format import format_money
        warnings.append(
            f"{summary.unmapped_count} ledger(s) are unmapped and excluded from the "
            f"statements (net {format_money(summary.unmapped_net_debit)})."
        )
    if summary.unresolved_nature_count:
        warnings.append(
            f"{summary.unresolved_nature_count} ledger(s) are mapped under a group with "
            "no accounting nature and cannot be placed on a statement."
        )
    if not summary.balanced and summary.ledger_count:
        from app.services.reporting.format import format_money
        warnings.append(
            f"The mapped trial balance does not sum to zero (out by "
            f"{format_money(summary.difference)})."
        )
    return warnings


async def recanonicalize(
    db: AsyncSession,
    engagement_id: uuid.UUID,
    company_id: uuid.UUID,
    *,
    convention: TBSignConvention | None = None,
    ledger_ids: Sequence[uuid.UUID] | None = None,
) -> int:
    """Re-derive `closing_net_debit` from the source figures and current mappings.

    Only meaningful under the `magnitude` convention, where an all-positive source
    means the sign comes from the mapped group's nature -- so changing a mapping
    changes the canonical value. A no-op for signed/explicit/derived sources, which
    is why it is cheap enough to call from every mapping write path. Any path that
    mutates `mapped_group_id` without calling this leaves totals stale.
    """
    if convention is None:
        eng = await db.get(AuditEngagement, engagement_id)
        convention = eng.tb_sign_convention if eng else None
    if convention is not TBSignConvention.magnitude:
        return 0

    stmt = select(TrialBalanceAccount).where(
        TrialBalanceAccount.engagement_id == engagement_id
    )
    if ledger_ids:
        stmt = stmt.where(TrialBalanceAccount.id.in_(list(ledger_ids)))
    accounts = list((await db.execute(stmt)).scalars().all())
    if not accounts:
        return 0

    index = await lg.resolve_group_index(db, company_id)
    changed = 0
    for acc in accounts:
        nature = index.natures.get(acc.mapped_group_id) if acc.mapped_group_id else None
        closing, unresolved = tb.canonical_net_debit(
            value=acc.closing_balance,
            convention=TBSignConvention.magnitude,
            group_nature=nature,
        )
        opening, _ = tb.canonical_net_debit(
            value=acc.opening_balance,
            convention=TBSignConvention.magnitude,
            group_nature=nature,
        )
        new_closing, new_opening = tb.q2(closing), tb.q2(opening)
        if (tb.q2(acc.closing_net_debit) != new_closing
                or tb.q2(acc.opening_net_debit) != new_opening
                or bool(acc.sign_unresolved) != unresolved):
            acc.closing_net_debit = new_closing
            acc.opening_net_debit = new_opening
            acc.sign_unresolved = unresolved
            changed += 1
        if acc.source_row_consistent is not None:
            expected = new_opening + tb.q2(acc.debit) - tb.q2(acc.credit)
            acc.source_row_consistent = tb.is_zero(expected - new_closing)
    return changed


async def apply_sign_convention(
    db: AsyncSession,
    engagement: AuditEngagement,
    convention: TBSignConvention,
) -> int:
    """Set an engagement's convention and re-derive every canonical figure.

    The escape hatch for a mis-detected convention: it touches no row identity, so
    audit-entry lines stay valid and it is safe even when the trial balance is
    otherwise locked against re-import.
    """
    res = await db.execute(
        select(TrialBalanceAccount).where(
            TrialBalanceAccount.engagement_id == engagement.id
        )
    )
    accounts = list(res.scalars().all())
    index = await lg.resolve_group_index(db, engagement.company_id)

    for acc in accounts:
        nature = index.natures.get(acc.mapped_group_id) if acc.mapped_group_id else None
        closing, unresolved = tb.canonical_net_debit(
            value=acc.closing_balance, convention=convention, group_nature=nature,
        )
        opening, _ = tb.canonical_net_debit(
            value=acc.opening_balance, convention=convention, group_nature=nature,
        )
        acc.closing_net_debit = tb.q2(closing)
        acc.opening_net_debit = tb.q2(opening)
        acc.sign_unresolved = unresolved

    engagement.tb_sign_convention = convention
    return len(accounts)
