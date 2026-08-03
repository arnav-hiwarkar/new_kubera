#!/usr/bin/env python3
"""Audit and safely backfill canonical trial-balance signs.

Dry-run is the default. ``--apply`` writes only conventions proven from stored
figures. To resolve an ambiguous legacy engagement, provide both ``--engagement``
and ``--convention signed|magnitude``; that is an explicit operator decision, not a
guess made by this script.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import async_session_factory
from app.models.auditease import AuditEngagement, TBSignConvention, TrialBalanceAccount
from app.services import trial_balance as tb
from app.services import trial_balance_query as tbq


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="persist safe/explicit changes")
    parser.add_argument("--engagement", type=uuid.UUID, help="limit to one engagement")
    parser.add_argument("--convention", choices=("signed", "magnitude"))
    args = parser.parse_args()
    if args.convention and not args.engagement:
        parser.error("--convention requires --engagement")
    if args.convention and not args.apply:
        parser.error("--convention requires --apply")
    return args


async def main() -> None:
    args = arguments()
    async with async_session_factory() as db:
        stmt = select(AuditEngagement).order_by(AuditEngagement.created_at)
        if args.engagement:
            stmt = stmt.where(AuditEngagement.id == args.engagement)
        engagements = list((await db.execute(stmt)).scalars().all())
        candidates = 0
        changed = 0
        for engagement in engagements:
            accounts = list((await db.execute(
                select(TrialBalanceAccount).where(
                    TrialBalanceAccount.engagement_id == engagement.id
                )
            )).scalars().all())
            if not accounts:
                continue
            closings = [tb.ParsedAmount(tb.to_decimal(a.closing_balance)) for a in accounts]
            report = tb.detect_sign_convention(
                closings,
                has_closing_column=True,
                sum_debit=sum((tb.to_decimal(a.debit) for a in accounts), Decimal(0)),
                sum_credit=sum((tb.to_decimal(a.credit) for a in accounts), Decimal(0)),
            )
            chosen = (
                TBSignConvention(args.convention)
                if args.engagement == engagement.id and args.convention
                else report.convention if report.confidence == "proven" else None
            )
            action = "would update" if chosen and not args.apply else "update" if chosen else "review"
            print(
                f"{engagement.id} {engagement.period_label!r}: stored="
                f"{getattr(engagement.tb_sign_convention, 'value', None)} "
                f"detected={report.convention.value}/{report.confidence} action={action}"
            )
            if chosen:
                candidates += 1
            if args.apply and chosen:
                await tbq.apply_sign_convention(db, engagement, chosen)
                changed += 1
        if args.apply:
            await db.commit()
        else:
            await db.rollback()
        count = changed if args.apply else candidates
        print(f"{'Updated' if args.apply else 'Would update'} {count} engagement(s).")


if __name__ == "__main__":
    asyncio.run(main())
