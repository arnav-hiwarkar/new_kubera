"""Chart-of-accounts helpers: seeding the fixed top groups and resolving the
root→leaf name path for a group (used to display mappings on the TB)."""
import uuid
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditease import LedgerGroup

# The four fixed, read-only top-level groups (company_id = NULL, level 0).
DEFAULT_TOP_GROUPS = ["Assets", "Liabilities", "Income", "Expenditure"]


async def ensure_default_ledger_groups(db: AsyncSession) -> None:
    """Idempotently create the four seeded top groups if missing."""
    res = await db.execute(
        select(LedgerGroup.name).where(
            LedgerGroup.company_id.is_(None), LedgerGroup.level == 0
        )
    )
    existing = set(res.scalars().all())
    missing = [n for n in DEFAULT_TOP_GROUPS if n not in existing]
    if missing:
        for name in missing:
            db.add(LedgerGroup(company_id=None, parent_id=None, name=name, level=0, has_children=False))
        await db.flush()


async def load_visible_groups(db: AsyncSession, company_id: uuid.UUID) -> List[LedgerGroup]:
    """Seeded (NULL) groups + this company's own groups."""
    res = await db.execute(
        select(LedgerGroup).where(LedgerGroup.company_id.in_([None, company_id]))
    )
    return list(res.scalars().all())


def build_path_map(groups: List[LedgerGroup]) -> Dict[uuid.UUID, List[str]]:
    """Map each group id to its root→leaf list of names."""
    by_id = {g.id: g for g in groups}
    cache: Dict[uuid.UUID, List[str]] = {}

    def path(gid: uuid.UUID) -> List[str]:
        if gid in cache:
            return cache[gid]
        g = by_id.get(gid)
        if g is None:
            return []
        result = (path(g.parent_id) if g.parent_id else []) + [g.name]
        cache[gid] = result
        return result

    return {g.id: path(g.id) for g in groups}


async def resolve_group_paths(db: AsyncSession, company_id: uuid.UUID) -> Dict[uuid.UUID, List[str]]:
    return build_path_map(await load_visible_groups(db, company_id))


def attach_group_paths(accounts, path_map: Dict[uuid.UUID, List[str]]) -> list:
    """Set `.mapped_group_path` on each TB account instance for serialization."""
    for acc in accounts:
        acc.mapped_group_path = path_map.get(acc.mapped_group_id) if acc.mapped_group_id else None
    return accounts
