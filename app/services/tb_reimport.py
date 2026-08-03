"""Re-import planning: match a freshly parsed trial balance against the stored one.

Why this exists: the old import did `DELETE FROM trial_balance_accounts WHERE
engagement_id = ...` then re-inserted. Because `audit_entry_lines.ledger_id` is
`ON DELETE CASCADE`, that would silently destroy approved audit-entry lines -- the
blanket 409 guard was the only thing preventing it. It also discarded every
`mapped_group_id`, so a re-import threw away all the user's mapping work.

Updating in place preserves `id`, which preserves both the mapping and every
foreign key pointing at the ledger. A ledger that has vanished from the new file but
is still referenced by an entry line is RETAINED rather than deleted, because
deleting it would cascade away an adjustment.

Pure and synchronous so it can be unit-tested without a database.
"""
from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence


def normalize_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


@dataclass
class ReimportPlan:
    to_update: list[tuple[uuid.UUID, dict]] = field(default_factory=list)
    to_insert: list[dict] = field(default_factory=list)
    to_delete: list[uuid.UUID] = field(default_factory=list)
    # Gone from the new file BUT referenced by an audit entry line -- left untouched.
    to_retain: list[uuid.UUID] = field(default_factory=list)
    matched_by_code: int = 0
    matched_by_name: int = 0
    # Existing ledgers that were mapped and whose mapping will not survive.
    will_lose_mapping: list[str] = field(default_factory=list)
    retained_referenced: list[str] = field(default_factory=list)
    ambiguous_matches: list[str] = field(default_factory=list)


def plan_reimport(
    existing: Sequence[Any],
    parsed: Sequence[dict],
    referenced_ledger_ids: set[uuid.UUID] | None = None,
) -> ReimportPlan:
    """Match parsed rows to existing accounts by ledger_code, else by ledger_name."""
    referenced = referenced_ledger_ids or set()
    plan = ReimportPlan()

    by_code: dict[str, list[Any]] = {}
    by_name: dict[str, list[Any]] = {}
    for acc in existing:
        code = normalize_key(getattr(acc, "ledger_code", None))
        if code:
            by_code.setdefault(code, []).append(acc)
        name = normalize_key(getattr(acc, "ledger_name", None))
        if name:
            by_name.setdefault(name, []).append(acc)

    parsed_codes = Counter(
        normalize_key(rec.get("ledger_code")) for rec in parsed
        if normalize_key(rec.get("ledger_code"))
    )
    parsed_names = Counter(
        normalize_key(rec.get("ledger_name")) for rec in parsed
        if normalize_key(rec.get("ledger_name"))
    )

    consumed: set[uuid.UUID] = set()
    for rec in parsed:
        code = normalize_key(rec.get("ledger_code"))
        name = normalize_key(rec.get("ledger_name"))

        match = None
        matched_on = ""
        if code:
            code_candidates = [a for a in by_code.get(code, []) if a.id not in consumed]
            if parsed_codes[code] > 1 or len(by_code.get(code, [])) > 1:
                plan.ambiguous_matches.append(
                    f"duplicate ledger code {rec.get('ledger_code')!r} ({rec.get('ledger_name')})"
                )
            elif len(code_candidates) == 1:
                match, matched_on = code_candidates[0], "code"

        # Name matching is allowed only if at least one side has no code. Never let
        # an equal name hide two conflicting non-empty ledger codes.
        if match is None and name and not (
            code and (code in by_code or any(
                normalize_key(getattr(a, "ledger_code", None))
                for a in by_name.get(name, [])
            ))
        ):
            name_candidates = [
                a for a in by_name.get(name, [])
                if a.id not in consumed
                and (not code or not normalize_key(getattr(a, "ledger_code", None)))
            ]
            if parsed_names[name] > 1 or len(by_name.get(name, [])) > 1:
                plan.ambiguous_matches.append(
                    f"duplicate ledger name {rec.get('ledger_name')!r}"
                )
            elif len(name_candidates) == 1:
                match, matched_on = name_candidates[0], "name"

        if match is None:
            plan.to_insert.append(rec)
            continue

        consumed.add(match.id)
        if matched_on == "code":
            plan.matched_by_code += 1
        else:
            plan.matched_by_name += 1
        plan.to_update.append((match.id, rec))

    for acc in existing:
        if acc.id in consumed:
            continue
        label = getattr(acc, "ledger_name", str(acc.id))
        if acc.id in referenced:
            plan.to_retain.append(acc.id)
            plan.retained_referenced.append(label)
        else:
            plan.to_delete.append(acc.id)
            if getattr(acc, "mapped_group_id", None):
                plan.will_lose_mapping.append(label)

    return plan
