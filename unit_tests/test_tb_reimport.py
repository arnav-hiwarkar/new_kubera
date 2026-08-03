import uuid
from dataclasses import dataclass

from app.services.tb_reimport import plan_reimport


@dataclass
class Existing:
    ledger_code: str | None
    ledger_name: str
    mapped_group_id: uuid.UUID | None = None
    id: uuid.UUID = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()


def row(code, name):
    return {"ledger_code": code, "ledger_name": name, "closing_balance": 0}


def test_unique_code_match_preserves_identity_when_name_changes():
    old = Existing("100", "Old name")
    plan = plan_reimport([old], [row(" 100 ", "New name")])
    assert plan.to_update == [(old.id, row(" 100 ", "New name"))]
    assert plan.matched_by_code == 1
    assert not plan.to_insert and not plan.to_delete


def test_conflicting_nonempty_codes_never_fall_back_to_equal_name():
    old = Existing("100", "Cash")
    plan = plan_reimport([old], [row("200", "Cash")])
    assert plan.to_update == []
    assert plan.to_insert == [row("200", "Cash")]
    assert plan.to_delete == [old.id]


def test_name_match_allowed_when_one_side_has_no_code():
    old = Existing(None, "  Trade   Receivable ")
    plan = plan_reimport([old], [row("300", "trade receivable")])
    assert plan.to_update[0][0] == old.id
    assert plan.matched_by_name == 1


def test_duplicate_source_code_is_reported_and_not_guessed():
    old = Existing("DUP", "Duplicate", mapped_group_id=uuid.uuid4())
    parsed = [row("DUP", "Duplicate A"), row("DUP", "Duplicate B")]
    plan = plan_reimport([old], parsed)
    assert plan.to_update == []
    assert plan.to_insert == parsed
    assert plan.to_delete == [old.id]
    assert len(plan.ambiguous_matches) == 2
    assert plan.will_lose_mapping == ["Duplicate"]


def test_missing_referenced_ledger_is_retained():
    old = Existing("100", "Cash", mapped_group_id=uuid.uuid4())
    plan = plan_reimport([old], [], {old.id})
    assert plan.to_retain == [old.id]
    assert plan.retained_referenced == ["Cash"]
    assert not plan.to_delete


def test_missing_unreferenced_ledger_is_deleted_and_mapping_loss_reported():
    old = Existing("100", "Cash", mapped_group_id=uuid.uuid4())
    plan = plan_reimport([old], [])
    assert plan.to_delete == [old.id]
    assert plan.will_lose_mapping == ["Cash"]
