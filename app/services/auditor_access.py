"""Per-area permission helpers for auditor engagement grants.

Pure functions — no DB. The router layer owns queries and HTTP errors.
"""
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditease import AUDITOR_AREAS, SenderType


def normalize_area_permissions(payload: dict | None) -> dict[str, bool]:
    """None => every area enabled (invite default). An explicit payload sets the
    listed areas and DENIES everything omitted, so {"entries": true} means
    entries-only."""
    if payload is None:
        return {a: True for a in AUDITOR_AREAS}
    unknown = set(payload) - set(AUDITOR_AREAS)
    if unknown:
        raise ValueError(f"Unknown areas: {sorted(unknown)}")
    return {a: bool(payload.get(a, False)) for a in AUDITOR_AREAS}


def area_enabled(perms: dict | None, area: str) -> bool:
    return bool((perms or {}).get(area, False))


async def attach_actor_names(db: AsyncSession, objs: Sequence[Any], id_attr: str, name_attr: str) -> None:
    """Resolve Auditor names for `id_attr` on each obj and set `name_attr`."""
    from app.models.auditor import Auditor

    ids = {getattr(o, id_attr, None) for o in objs}
    ids.discard(None)
    if not ids:
        return
    res = await db.execute(select(Auditor.name, Auditor.id).where(Auditor.id.in_(ids)))
    names = {aid: nm for nm, aid in res.all()}
    for o in objs:
        setattr(o, name_attr, names.get(getattr(o, id_attr, None)))


async def attach_sender_names(db: AsyncSession, msgs: Sequence[Any]) -> None:
    from app.models.auditor import Auditor
    from app.models.company import CompanyUser

    aud_ids = {m.sender_id for m in msgs if m.sender_type == SenderType.auditor}
    usr_ids = {m.sender_id for m in msgs if m.sender_type == SenderType.company_user}
    names: dict = {}
    if aud_ids:
        res = await db.execute(select(Auditor.name, Auditor.id).where(Auditor.id.in_(aud_ids)))
        names.update({aid: nm for nm, aid in res.all()})
    if usr_ids:
        res = await db.execute(select(CompanyUser.full_name, CompanyUser.id).where(CompanyUser.id.in_(usr_ids)))
        names.update({uid: fn for fn, uid in res.all()})
    for m in msgs:
        m.sender_name = names.get(m.sender_id)
