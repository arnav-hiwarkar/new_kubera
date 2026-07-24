"""Deterministic one-to-one planning for engagement ledger mapping imports."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Hashable, Literal


LedgerId = Hashable
GroupId = Hashable
MatchMethod = Literal["exact_identity", "name_without_code"]
IssueReason = Literal[
    "unmatched",
    "source_exhausted",
    "identity_disagreement",
    "ambiguous_source_mapping",
]


@dataclass(frozen=True)
class LedgerForMapping:
    id: LedgerId
    ledger_code: str | None
    ledger_name: str
    mapped_group_id: GroupId | None = None
    order: int = 0


@dataclass(frozen=True)
class MappingAssignment:
    source_id: LedgerId
    target_id: LedgerId
    group_id: GroupId
    match_method: MatchMethod


@dataclass(frozen=True)
class MappingIssue:
    target_id: LedgerId
    reason: IssueReason


@dataclass(frozen=True)
class MappingPlan:
    assignments: list[MappingAssignment]
    issues: list[MappingIssue]
    unused_source_ids: list[LedgerId]


def normalise_ledger_code(value: str | None) -> str | None:
    normalised = unicodedata.normalize("NFKC", value).strip().casefold() if value else ""
    numeric_integer = re.fullmatch(r"([+-]?\d+)\.0+", normalised)
    if numeric_integer:
        normalised = numeric_integer.group(1)
    return normalised or None


def normalise_ledger_name(value: str) -> str:
    normalised = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(normalised.split())


def _ordered(rows: list[LedgerForMapping]) -> list[LedgerForMapping]:
    return sorted(rows, key=lambda row: (row.order, str(row.id)))


def plan_mapping_import(
    sources: list[LedgerForMapping],
    targets: list[LedgerForMapping],
) -> MappingPlan:
    """Build a conservative, deterministic, one-to-one mapping plan.

    A source row is consumed by at most one target. Exact code+name identity is
    resolved first. Name-only matching is allowed only when at least one side has
    no code. Non-empty identifier disagreements are never guessed.
    """
    ordered_sources = _ordered([row for row in sources if row.mapped_group_id is not None])
    ordered_targets = _ordered(targets)

    assignments: list[MappingAssignment] = []
    issue_by_target: dict[LedgerId, MappingIssue] = {}
    consumed_sources: set[LedgerId] = set()
    handled_targets: set[LedgerId] = set()

    source_exact: dict[tuple[str, str], list[LedgerForMapping]] = {}
    target_exact: dict[tuple[str, str], list[LedgerForMapping]] = {}
    for source in ordered_sources:
        code = normalise_ledger_code(source.ledger_code)
        if code:
            source_exact.setdefault((code, normalise_ledger_name(source.ledger_name)), []).append(source)
    for target in ordered_targets:
        code = normalise_ledger_code(target.ledger_code)
        if code:
            target_exact.setdefault((code, normalise_ledger_name(target.ledger_name)), []).append(target)

    # Phase 1: exact code+name identity.
    for key, exact_targets in target_exact.items():
        exact_sources = source_exact.get(key, [])
        if not exact_sources:
            continue
        group_ids = {source.mapped_group_id for source in exact_sources}
        if len(group_ids) != 1:
            for target in exact_targets:
                issue_by_target[target.id] = MappingIssue(target.id, "ambiguous_source_mapping")
                handled_targets.add(target.id)
            continue

        for source, target in zip(exact_sources, exact_targets):
            assignments.append(MappingAssignment(
                source_id=source.id,
                target_id=target.id,
                group_id=source.mapped_group_id,
                match_method="exact_identity",
            ))
            consumed_sources.add(source.id)
            handled_targets.add(target.id)
        for target in exact_targets[len(exact_sources):]:
            issue_by_target[target.id] = MappingIssue(target.id, "source_exhausted")
            handled_targets.add(target.id)

    # Phase 2: same name where at least one side has no code.
    remaining_sources = [
        source for source in ordered_sources if source.id not in consumed_sources
    ]
    remaining_targets = [
        target for target in ordered_targets if target.id not in handled_targets
    ]
    source_by_name: dict[str, list[LedgerForMapping]] = {}
    target_by_name: dict[str, list[LedgerForMapping]] = {}
    for source in remaining_sources:
        source_by_name.setdefault(normalise_ledger_name(source.ledger_name), []).append(source)
    for target in remaining_targets:
        target_by_name.setdefault(normalise_ledger_name(target.ledger_name), []).append(target)

    for name, same_name_targets in target_by_name.items():
        same_name_sources = source_by_name.get(name, [])
        available_sources = list(same_name_sources)
        for target in same_name_targets:
            candidates = [
                source
                for source in available_sources
                if normalise_ledger_code(source.ledger_code) is None
                or normalise_ledger_code(target.ledger_code) is None
            ]
            if not candidates:
                had_eligible_source = any(
                    normalise_ledger_code(source.ledger_code) is None
                    or normalise_ledger_code(target.ledger_code) is None
                    for source in same_name_sources
                )
                if had_eligible_source:
                    issue_by_target[target.id] = MappingIssue(target.id, "source_exhausted")
                    handled_targets.add(target.id)
                continue
            group_ids = {source.mapped_group_id for source in candidates}
            if len(group_ids) != 1:
                issue_by_target[target.id] = MappingIssue(target.id, "ambiguous_source_mapping")
                handled_targets.add(target.id)
                continue

            source = candidates[0]
            assignments.append(MappingAssignment(
                source_id=source.id,
                target_id=target.id,
                group_id=source.mapped_group_id,
                match_method="name_without_code",
            ))
            consumed_sources.add(source.id)
            handled_targets.add(target.id)
            available_sources.remove(source)

    # Classify every remaining target without guessing.
    all_sources_by_code: dict[str, list[LedgerForMapping]] = {}
    all_sources_by_name: dict[str, list[LedgerForMapping]] = {}
    for source in ordered_sources:
        code = normalise_ledger_code(source.ledger_code)
        if code:
            all_sources_by_code.setdefault(code, []).append(source)
        all_sources_by_name.setdefault(normalise_ledger_name(source.ledger_name), []).append(source)

    for target in ordered_targets:
        if target.id in handled_targets:
            continue
        code = normalise_ledger_code(target.ledger_code)
        name = normalise_ledger_name(target.ledger_name)
        same_code = all_sources_by_code.get(code, []) if code else []
        same_name = all_sources_by_name.get(name, [])
        reason: IssueReason = (
            "identity_disagreement" if same_code or same_name else "unmatched"
        )
        issue_by_target[target.id] = MappingIssue(target.id, reason)

    assignments.sort(key=lambda item: next(
        (target.order, str(target.id)) for target in ordered_targets if target.id == item.target_id
    ))
    issues = [
        issue_by_target[target.id]
        for target in ordered_targets
        if target.id in issue_by_target
    ]
    unused_source_ids = [
        source.id for source in ordered_sources if source.id not in consumed_sources
    ]

    # Defensive invariants: a plan must never permit one-to-many application.
    assert len({item.source_id for item in assignments}) == len(assignments)
    assert len({item.target_id for item in assignments}) == len(assignments)
    assert len(assignments) <= len(ordered_sources)

    return MappingPlan(
        assignments=assignments,
        issues=issues,
        unused_source_ids=unused_source_ids,
    )
