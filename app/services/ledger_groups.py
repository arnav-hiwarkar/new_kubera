"""Chart-of-accounts helpers: seeding the fixed top groups and resolving the
root→leaf name path for a group (used to display mappings on the TB)."""
import uuid
from typing import Dict, List

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditease import LedgerGroup

# The four fixed, read-only top-level groups (company_id = NULL, level 0).
DEFAULT_TOP_GROUPS = ["Assets", "Liabilities", "Income", "Expenditure"]

SCHEDULE_III_SEED = {
    "Assets": [
        "Property, Plant and Equipment", "Capital Work-in-Progress", "Investment Property",
        "Goodwill", "Other Intangible Assets", "Non-current Investments",
        "Long-term Loans and Advances", "Other Non-current Assets", "Current Investments",
        "Inventories", "Trade Receivables", "Cash and Cash Equivalents",
        "Short-term Loans and Advances", "Other Current Assets",
    ],
    "Liabilities": [
        "Share Capital", "Reserves & Surplus", "Money received against share warrants",
        "Share application money pending allotment", "Long-term Borrowings",
        "Deferred Tax Liabilities (Net)", "Other Long-term Liabilities", "Long-term Provisions",
        "Short-term Borrowings", "Trade Payables", "Other Current Liabilities",
        "Short-term Provisions",
    ],
    "Income": [
        "Revenue from Operations", "Other Income",
    ],
    "Expenditure": [
        "Cost of Materials Consumed", "Purchases of Stock-in-Trade", "Changes in Inventories",
        "Employee Benefits Expense", "Finance Costs", "Depreciation and Amortization Expense",
        "Other Expenses",
    ]
}

async def ensure_default_ledger_groups(db: AsyncSession) -> None:
    """Idempotently create the four seeded top groups and Schedule III sub-groups."""
    # 1. Top groups
    res = await db.execute(
        select(LedgerGroup).where(
            LedgerGroup.company_id.is_(None), LedgerGroup.level == 0
        )
    )
    existing_tops = {g.name: g for g in res.scalars().all()}
    
    for name in DEFAULT_TOP_GROUPS:
        if name not in existing_tops:
            group = LedgerGroup(company_id=None, parent_id=None, name=name, level=0, has_children=True)
            db.add(group)
            existing_tops[name] = group
            
    await db.flush()
    
    # 2. Sub-groups
    res_sub = await db.execute(
        select(LedgerGroup).where(
            LedgerGroup.company_id.is_(None), LedgerGroup.level == 1
        )
    )
    existing_subs = {(g.parent_id, g.name): g for g in res_sub.scalars().all()}
    
    for top_name, sub_names in SCHEDULE_III_SEED.items():
        top_group = existing_tops.get(top_name)
        if not top_group: continue
        
        # Ensure has_children is True for top group
        if not top_group.has_children:
            top_group.has_children = True
            
        for sub_name in sub_names:
            if (top_group.id, sub_name) not in existing_subs:
                db.add(LedgerGroup(
                    company_id=None, 
                    parent_id=top_group.id, 
                    name=sub_name, 
                    level=1, 
                    has_children=False
                ))
    await db.flush()



async def load_visible_groups(db: AsyncSession, company_id: uuid.UUID) -> List[LedgerGroup]:
    """Seeded (NULL) groups + this company's own groups."""
    res = await db.execute(
        select(LedgerGroup).where(or_(LedgerGroup.company_id.is_(None), LedgerGroup.company_id == company_id))
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
