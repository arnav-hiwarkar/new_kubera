"""Asset code (tag) generation.

Codes look like ``COMP-HO-000137``: a category-derived prefix, an optional branch
code, and a zero-padded running number. The number comes from an explicit
per-prefix counter row locked FOR UPDATE — not ``MAX(asset_code) + 1``, because
exploding a 50-unit acquisition allocates fifty codes at once and two concurrent
explodes reading the same MAX would hand out the same tags.

The generated string is deliberately plain ASCII so it can be QR-encoded later
without a schema change.
"""
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import Asset, AssetCodeSequence

DEFAULT_PREFIX = "AST"
NUMBER_WIDTH = 6


def normalize_prefix(prefix: Optional[str]) -> str:
    """Upper-case, strip anything that would make an ugly tag, fall back to AST."""
    if not prefix:
        return DEFAULT_PREFIX
    cleaned = "".join(ch for ch in prefix.strip().upper() if ch.isalnum())
    return cleaned[:12] or DEFAULT_PREFIX


def format_code(prefix: str, number: int, branch_code: Optional[str] = None) -> str:
    parts = [prefix]
    if branch_code:
        bc = "".join(ch for ch in branch_code.strip().upper() if ch.isalnum())
        if bc:
            parts.append(bc[:8])
    parts.append(str(number).zfill(NUMBER_WIDTH))
    return "-".join(parts)


async def _get_or_create_sequence(
    db: AsyncSession, company_id: uuid.UUID, prefix: str
) -> AssetCodeSequence:
    stmt = (
        select(AssetCodeSequence)
        .where(
            AssetCodeSequence.company_id == company_id,
            func.upper(AssetCodeSequence.prefix) == prefix,
        )
        .with_for_update()
    )
    seq = (await db.execute(stmt)).scalar_one_or_none()
    if seq is not None:
        return seq

    seq = AssetCodeSequence(company_id=company_id, prefix=prefix, next_number=1)
    db.add(seq)
    try:
        await db.flush()
    except IntegrityError:
        # Another transaction created it between our SELECT and INSERT.
        await db.rollback()
        seq = (await db.execute(stmt)).scalar_one()
    return seq


async def allocate_asset_codes(
    db: AsyncSession,
    company_id: uuid.UUID,
    prefix: Optional[str],
    count: int,
    branch_code: Optional[str] = None,
) -> list[str]:
    """Reserve `count` consecutive codes and return them. Caller commits."""
    if count < 1:
        return []
    normalized = normalize_prefix(prefix)
    seq = await _get_or_create_sequence(db, company_id, normalized)
    start = seq.next_number
    seq.next_number = start + count
    await db.flush()
    return [format_code(normalized, start + i, branch_code) for i in range(count)]


async def code_is_taken(
    db: AsyncSession, company_id: uuid.UUID, code: str, exclude_asset_id: Optional[uuid.UUID] = None
) -> bool:
    """Case-insensitive check against the partial unique index."""
    stmt = select(Asset.id).where(
        Asset.company_id == company_id, func.lower(Asset.asset_code) == code.strip().lower()
    )
    if exclude_asset_id is not None:
        stmt = stmt.where(Asset.id != exclude_asset_id)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None
