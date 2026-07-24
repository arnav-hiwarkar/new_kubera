from app.services.mapping_import import (
    LedgerForMapping,
    plan_mapping_import,
)


def ledger(
    ledger_id: str,
    code: str | None,
    name: str,
    group: str | None = None,
    order: int = 0,
) -> LedgerForMapping:
    return LedgerForMapping(
        id=ledger_id,
        ledger_code=code,
        ledger_name=name,
        mapped_group_id=group,
        order=order,
    )


def test_one_source_is_never_reused_for_duplicate_targets():
    plan = plan_mapping_import(
        [ledger("s1", "100", "Cash", "g1")],
        [
            ledger("t1", "100", "Cash", order=1),
            ledger("t2", "100", "Cash", order=2),
            ledger("t3", "100", "Cash", order=3),
        ],
    )

    assert [(a.source_id, a.target_id) for a in plan.assignments] == [("s1", "t1")]
    assert [(i.target_id, i.reason) for i in plan.issues] == [
        ("t2", "source_exhausted"),
        ("t3", "source_exhausted"),
    ]
    assert len({a.source_id for a in plan.assignments}) == len(plan.assignments)
    assert len({a.target_id for a in plan.assignments}) == len(plan.assignments)


def test_duplicate_buckets_pair_only_up_to_available_source_rows():
    plan = plan_mapping_import(
        [
            ledger("s1", "100", "Cash", "g1", 1),
            ledger("s2", "100", "Cash", "g1", 2),
        ],
        [
            ledger("t1", "100", "Cash", order=1),
            ledger("t2", "100", "Cash", order=2),
            ledger("t3", "100", "Cash", order=3),
        ],
    )

    assert [(a.source_id, a.target_id) for a in plan.assignments] == [
        ("s1", "t1"),
        ("s2", "t2"),
    ]
    assert [(i.target_id, i.reason) for i in plan.issues] == [
        ("t3", "source_exhausted"),
    ]


def test_duplicate_source_identity_with_different_groups_is_ambiguous():
    plan = plan_mapping_import(
        [
            ledger("s1", "100", "Cash", "g1", 1),
            ledger("s2", "100", "Cash", "g2", 2),
        ],
        [ledger("t1", "100", "Cash")],
    )

    assert plan.assignments == []
    assert [(i.target_id, i.reason) for i in plan.issues] == [
        ("t1", "ambiguous_source_mapping"),
    ]


def test_same_code_with_different_name_is_an_identity_disagreement():
    plan = plan_mapping_import(
        [ledger("s1", "100", "Cash", "g1")],
        [ledger("t1", "100", "Bank")],
    )

    assert plan.assignments == []
    assert [(i.target_id, i.reason) for i in plan.issues] == [
        ("t1", "identity_disagreement"),
    ]


def test_same_name_with_different_non_empty_code_is_an_identity_disagreement():
    plan = plan_mapping_import(
        [ledger("s1", "100", "Cash", "g1")],
        [ledger("t1", "200", "Cash")],
    )

    assert plan.assignments == []
    assert [(i.target_id, i.reason) for i in plan.issues] == [
        ("t1", "identity_disagreement"),
    ]


def test_unique_name_matches_when_one_side_has_no_code():
    plan = plan_mapping_import(
        [ledger("s1", None, "  Trade Receivable  ", "g1")],
        [ledger("t1", "200", "trade   receivable")],
    )

    assert [(a.source_id, a.target_id, a.match_method) for a in plan.assignments] == [
        ("s1", "t1", "name_without_code"),
    ]
    assert plan.issues == []


def test_name_fallback_never_pairs_two_disagreeing_non_empty_codes():
    plan = plan_mapping_import(
        [
            ledger("coded-source", "100", "Cash", "g1", 1),
            ledger("blank-source", None, "Cash", "g1", 2),
        ],
        [
            ledger("different-code-target", "200", "Cash", order=1),
            ledger("blank-target", None, "Cash", order=2),
        ],
    )

    assert [(a.source_id, a.target_id) for a in plan.assignments] == [
        ("blank-source", "different-code-target"),
        ("coded-source", "blank-target"),
    ]


def test_code_normalisation_handles_spreadsheet_integer_suffix_only():
    plan = plan_mapping_import(
        [
            ledger("s1", "1001.0", "Cash", "g1"),
            ledger("s2", "001", "Bank", "g2"),
        ],
        [
            ledger("t1", "1001", "cash"),
            ledger("t2", "1", "Bank"),
        ],
    )

    assert [(a.source_id, a.target_id) for a in plan.assignments] == [("s1", "t1")]
    assert [(i.target_id, i.reason) for i in plan.issues] == [
        ("t2", "identity_disagreement"),
    ]


def test_planning_is_deterministic_and_reports_unused_sources():
    sources = [
        ledger("s2", "100", "Cash", "g1", 2),
        ledger("s1", "100", "Cash", "g1", 1),
        ledger("unused", "300", "Loan", "g2", 3),
    ]
    targets = [
        ledger("t2", "100", "Cash", order=2),
        ledger("t1", "100", "Cash", order=1),
    ]

    first = plan_mapping_import(sources, targets)
    second = plan_mapping_import(list(reversed(sources)), list(reversed(targets)))

    expected = [("s1", "t1"), ("s2", "t2")]
    assert [(a.source_id, a.target_id) for a in first.assignments] == expected
    assert [(a.source_id, a.target_id) for a in second.assignments] == expected
    assert first.unused_source_ids == ["unused"]
    assert second.unused_source_ids == ["unused"]
