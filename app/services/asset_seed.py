"""Seeded global reference data for the fixed-asset register.

Installs Income Tax Act Appendix I blocks and a Companies Act Schedule II Part C
category tree as global rows (company_id IS NULL), shared by every tenant. Called
from the Alembic migration in production and from tests directly.

Idempotent: matches on (company_id IS NULL, code/name) and updates in place, so
re-running after a statutory rate change corrects the existing rows rather than
duplicating them.

Statutory caveat for maintainers: these figures are the defaults a company starts
from, not advice. Schedule II permits a different useful life if justified, and
the register requires a reason when an asset overrides its category default.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_masters import (
    AssetCategory,
    DepreciationMethod,
    ItAssetBlock,
    ItBlockClass,
    ItcTreatment,
)

# --- Income Tax Act, Appendix I (rates capped at 40% since AY 2018-19) ---
# (code, name, rate %, class, display order)
IT_BLOCKS = [
    ("BLD-5", "Buildings — residential (other than hotels and boarding houses)", 5, ItBlockClass.building, 10),
    ("BLD-10", "Buildings — other than residential (office, factory)", 10, ItBlockClass.building, 20),
    ("BLD-40", "Buildings — temporary erections (wooden structures)", 40, ItBlockClass.building, 30),
    ("FF-10", "Furniture and fittings", 10, ItBlockClass.furniture, 40),
    ("PM-15", "Plant and machinery — general", 15, ItBlockClass.plant_machinery, 50),
    ("PM-15-MV", "Motor vehicles other than those used in a business of running them on hire", 15, ItBlockClass.plant_machinery, 60),
    ("PM-30-MV", "Motor buses, lorries and taxis used in a business of running them on hire", 30, ItBlockClass.plant_machinery, 70),
    ("PM-40-COMP", "Computers including computer software", 40, ItBlockClass.plant_machinery, 80),
    ("PM-40-ESD", "Energy saving and pollution control devices", 40, ItBlockClass.plant_machinery, 90),
    ("PM-20-SHIP", "Ships", 20, ItBlockClass.plant_machinery, 100),
    ("INT-25", "Intangible assets — know-how, patents, copyrights, trademarks, licences, franchises", 25, ItBlockClass.intangible, 110),
]

# --- Companies Act Schedule II Part C ---
# Parent groups, then leaves carrying the defaults.
# leaf: (name, useful_life_years, it_block_code, itc_treatment, field_groups, schedule_ii_reference)
_SLM = DepreciationMethod.slm
_DEFAULT_RESIDUAL_PCT = 5

CATEGORY_TREE = [
    {
        "name": "Buildings",
        "tag_prefix": "BLD",
        "children": [
            ("RCC frame structure buildings", 60, "BLD-10", None, ["insurance"], "Part C 1(a) — Buildings other than factory buildings, RCC frame structure"),
            ("Buildings other than RCC frame structure", 30, "BLD-10", None, ["insurance"], "Part C 1(b) — Buildings other than factory buildings, other than RCC frame structure"),
            ("Factory buildings", 30, "BLD-10", None, ["insurance"], "Part C 1 — Factory buildings"),
            ("Temporary erections (wooden structures)", 3, "BLD-40", None, [], "Part C 1 — Temporary erections"),
        ],
    },
    {
        "name": "Plant and machinery",
        "tag_prefix": "PM",
        "children": [
            ("General plant and machinery", 15, "PM-15", None, ["test_certificate", "warranty", "amc"], "Part C 4(i) — General rate applicable to plant and machinery"),
            ("Plant used in generation and transmission of power", 40, "PM-15", None, ["test_certificate", "amc"], "Part C 4(ii) — Plant and machinery used in generation, transmission and distribution of power"),
        ],
    },
    {
        "name": "Furniture and fittings",
        "tag_prefix": "FF",
        "children": [
            ("General furniture and fittings", 10, "FF-10", None, [], "Part C 6(a) — General furniture and fittings"),
            ("Furniture used in hotels, restaurants and boarding houses", 8, "FF-10", None, [], "Part C 6(b) — Furniture used in hotels, restaurants, boarding houses, schools and similar"),
        ],
    },
    {
        "name": "Office equipment",
        "tag_prefix": "OE",
        "children": [
            ("Office equipment", 5, "PM-15", None, ["warranty", "amc"], "Part C 7 — Office equipment"),
        ],
    },
    {
        "name": "Computers and data processing units",
        "tag_prefix": "COMP",
        "children": [
            ("Servers and networks", 6, "PM-40-COMP", None, ["network_ids", "warranty", "amc"], "Part C 5(a) — Servers and networks"),
            ("End user devices (desktops, laptops, printers)", 3, "PM-40-COMP", None, ["network_ids", "warranty", "amc"], "Part C 5(b) — End user devices such as desktops, laptops"),
        ],
    },
    {
        "name": "Motor vehicles",
        "tag_prefix": "MV",
        "children": [
            # ITC on motor cars is blocked by Sec 17(5) of the CGST Act, so the GST
            # is capitalized into cost rather than recovered.
            ("Motor cars (other than those used in a hire business)", 8, "PM-15-MV", ItcTreatment.blocked, ["registration", "insurance", "amc"], "Part C 8(ii) — Motor buses, motor lorries, motor cars other than those used in a business of running them on hire"),
            ("Motor cycles, scooters and other mopeds", 10, "PM-15-MV", ItcTreatment.blocked, ["registration", "insurance", "amc"], "Part C 8(iii) — Motor cycles, scooters and other mopeds"),
            ("Motor buses, lorries and taxis used in a hire business", 6, "PM-30-MV", ItcTreatment.eligible, ["registration", "insurance", "amc"], "Part C 8(i) — Motor buses, motor lorries and motor cars used in a business of running them on hire"),
            ("Electrically operated vehicles", 8, "PM-15-MV", ItcTreatment.blocked, ["registration", "insurance", "amc"], "Part C 8(iv) — Electrically operated vehicles"),
        ],
    },
    {
        "name": "Electrical installations and equipment",
        "tag_prefix": "EI",
        "children": [
            ("Electrical installations and equipment", 10, "PM-15", None, ["test_certificate", "warranty"], "Part C 2 — Electrical installations and equipment"),
        ],
    },
    {
        "name": "Laboratory equipment",
        "tag_prefix": "LAB",
        "children": [
            ("General laboratory equipment", 10, "PM-15", None, ["test_certificate", "amc"], "Part C 10(a) — Laboratory equipment, general"),
            ("Laboratory equipment used in educational institutions", 5, "PM-15", None, ["test_certificate"], "Part C 10(b) — Laboratory equipment used in educational institutions"),
        ],
    },
    {
        "name": "Intangible assets",
        "tag_prefix": "INT",
        "children": [
            ("Computer software", 5, "INT-25", None, ["manual"], "Part C — Intangible assets (AS 26 / Ind AS 38)"),
            ("Other intangible assets", 10, "INT-25", None, ["manual"], "Part C — Intangible assets (AS 26 / Ind AS 38)"),
        ],
    },
]


def seed_global_asset_reference_data_sync(connection) -> dict:
    """Same seed, over a plain (sync) Connection, for use from an Alembic migration.

    Kept beside the async version so both read the IT_BLOCKS / CATEGORY_TREE
    constants above — the data is defined once. Idempotent, so re-running an
    upgrade after a statutory rate change corrects the rows in place.
    """
    import uuid as _uuid

    from sqlalchemy import insert, update

    blocks_table = ItAssetBlock.__table__
    cats_table = AssetCategory.__table__

    existing = connection.execute(
        select(blocks_table.c.id, blocks_table.c.code).where(blocks_table.c.company_id.is_(None))
    ).all()
    block_ids = {code: bid for bid, code in existing}

    for code, name, rate, klass, order in IT_BLOCKS:
        values = {
            "name": name,
            "dep_rate": rate,
            "block_class": klass.value,
            "display_order": order,
            "is_active": True,
        }
        if code in block_ids:
            connection.execute(
                update(blocks_table).where(blocks_table.c.id == block_ids[code]).values(**values)
            )
        else:
            new_id = _uuid.uuid4()
            connection.execute(
                insert(blocks_table).values(id=new_id, company_id=None, code=code, **values)
            )
            block_ids[code] = new_id

    rows = connection.execute(
        select(cats_table.c.id, cats_table.c.name, cats_table.c.parent_id).where(
            cats_table.c.company_id.is_(None)
        )
    ).all()
    by_id = {r.id: r for r in rows}

    def key_of(row):
        parent = by_id.get(row.parent_id) if row.parent_id else None
        return (parent.name if parent else None, row.name)

    cat_ids = {key_of(r): r.id for r in rows}

    parent_order = 0
    for group in CATEGORY_TREE:
        parent_order += 10
        pkey = (None, group["name"])
        pvalues = {
            "tag_prefix": group["tag_prefix"],
            "display_order": parent_order,
            "is_active": True,
            "applicable_field_groups": [],
        }
        if pkey in cat_ids:
            connection.execute(
                update(cats_table).where(cats_table.c.id == cat_ids[pkey]).values(**pvalues)
            )
        else:
            pid = _uuid.uuid4()
            connection.execute(
                insert(cats_table).values(
                    id=pid, company_id=None, parent_id=None, name=group["name"], **pvalues
                )
            )
            cat_ids[pkey] = pid
        parent_id = cat_ids[pkey]

        child_order = 0
        for name, life_years, block_code, itc, groups, ref in group["children"]:
            child_order += 10
            ckey = (group["name"], name)
            cvalues = {
                "parent_id": parent_id,
                "default_useful_life_months": life_years * 12,
                "default_dep_method": _SLM.value,
                "default_residual_pct": _DEFAULT_RESIDUAL_PCT,
                "default_it_block_id": block_ids[block_code],
                "default_itc_treatment": itc.value if itc else None,
                "tag_prefix": group["tag_prefix"],
                "applicable_field_groups": list(groups),
                "schedule_ii_reference": ref,
                "display_order": parent_order + child_order,
                "is_active": True,
            }
            if ckey in cat_ids:
                connection.execute(
                    update(cats_table).where(cats_table.c.id == cat_ids[ckey]).values(**cvalues)
                )
            else:
                connection.execute(
                    insert(cats_table).values(
                        id=_uuid.uuid4(), company_id=None, name=name, **cvalues
                    )
                )

    return {
        "it_blocks": len(IT_BLOCKS),
        "categories": sum(1 + len(g["children"]) for g in CATEGORY_TREE),
    }


async def seed_global_asset_reference_data(db: AsyncSession) -> dict:
    """Create or update the global IT blocks and Schedule II category tree.

    Caller commits. Returns a small summary for logging/verification.
    """
    # --- IT blocks ---
    existing_blocks = (
        await db.execute(select(ItAssetBlock).where(ItAssetBlock.company_id.is_(None)))
    ).scalars().all()
    blocks_by_code = {b.code: b for b in existing_blocks}

    for code, name, rate, klass, order in IT_BLOCKS:
        block = blocks_by_code.get(code)
        if block is None:
            block = ItAssetBlock(code=code, company_id=None)
            db.add(block)
            blocks_by_code[code] = block
        block.name = name
        block.dep_rate = rate
        block.block_class = klass
        block.display_order = order
        block.is_active = True

    # Blocks must exist before categories can point at them.
    await db.flush()

    # --- Category tree ---
    existing_cats = (
        await db.execute(select(AssetCategory).where(AssetCategory.company_id.is_(None)))
    ).scalars().all()
    # Global names are unique within a parent; key on (parent name or None, name).
    cats_by_id = {c.id: c for c in existing_cats}

    def key_of(cat: AssetCategory) -> tuple:
        parent = cats_by_id.get(cat.parent_id) if cat.parent_id else None
        return (parent.name if parent else None, cat.name)

    cats_by_key = {key_of(c): c for c in existing_cats}

    parent_order = 0
    for group in CATEGORY_TREE:
        parent_order += 10
        parent = cats_by_key.get((None, group["name"]))
        if parent is None:
            parent = AssetCategory(company_id=None, name=group["name"])
            db.add(parent)
            cats_by_key[(None, group["name"])] = parent
        parent.tag_prefix = group["tag_prefix"]
        parent.display_order = parent_order
        parent.is_active = True
        parent.applicable_field_groups = []
        await db.flush()  # need parent.id for children

        child_order = 0
        for name, life_years, block_code, itc, groups, ref in group["children"]:
            child_order += 10
            child = cats_by_key.get((group["name"], name))
            if child is None:
                child = AssetCategory(company_id=None, name=name, parent_id=parent.id)
                db.add(child)
                cats_by_key[(group["name"], name)] = child
            child.parent_id = parent.id
            child.default_useful_life_months = life_years * 12
            child.default_dep_method = _SLM
            child.default_residual_pct = _DEFAULT_RESIDUAL_PCT
            child.default_it_block_id = blocks_by_code[block_code].id
            child.default_itc_treatment = itc
            child.tag_prefix = group["tag_prefix"]
            child.applicable_field_groups = list(groups)
            child.schedule_ii_reference = ref
            child.display_order = parent_order + child_order
            child.is_active = True

    await db.flush()
    return {
        "it_blocks": len(IT_BLOCKS),
        "categories": sum(1 + len(g["children"]) for g in CATEGORY_TREE),
    }
