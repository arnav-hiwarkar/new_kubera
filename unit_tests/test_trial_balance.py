"""Unit tests for the pure trial-balance accounting core.

No DB, no fixtures -- this is where the sign model is pinned down. The two most
important assertions in this file are:

  * `present(+250, credit) == -250`  -- a debit balance on a credit-natured group
    must REDUCE that group (accumulated deficit, contra revenue). The old report
    code used abs() here and inflated liabilities/income instead.
  * `summarize(...).difference == sum of net debits` -- the balance check, the
    grid check and the import check are literally the same expression, so they
    cannot drift apart.
"""
import uuid
from decimal import Decimal

import pytest

from app.models.auditease import BalanceNature, TBSignConvention
from app.services import trial_balance as tb


D = Decimal
DEBIT = BalanceNature.debit
CREDIT = BalanceNature.credit


# ---------------------------------------------------------------------------
# parse_amount
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # blanks -> zero, never an error
    (None, D(0)), ("", D(0)), ("   ", D(0)),
    ("-", D(0)), ("–", D(0)), ("—", D(0)), (".", D(0)),
    ("nil", D(0)), ("NIL", D(0)), ("n/a", D(0)), ("NA", D(0)), ("--", D(0)),
    # plain numbers
    ("1234", D(1234)), ("1234.56", D("1234.56")), ("-1234", D(-1234)),
    (1234, D(1234)), (1234.5, D("1234.5")), (Decimal("5.5"), D("5.5")),
    # thousands separators, incl. Indian lakh grouping
    ("1,234.56", D("1234.56")), ("1,23,456.00", D("123456.00")),
    ("1,234,567", D(1234567)), ("1'234", D(1234)), ("1_234", D(1234)),
    # currency
    ("₹ 1,234", D(1234)), ("Rs. 1234", D(1234)), ("Rs 1234", D(1234)),
    ("INR 1234", D(1234)), ("$1,234", D(1234)), ("€1234", D(1234)),
    ("£1234", D(1234)), ("¥1234", D(1234)),
    # accounting parentheses / brackets
    ("(123)", D(-123)), ("(1,234.50)", D("-1234.50")), ("[1234]", D(-1234)),
    # trailing sign
    ("1234-", D(-1234)), ("1234+", D(1234)),
    # unicode minus variants
    ("−1234", D(-1234)), ("－1234", D(-1234)),
    # scientific notation, as Excel sometimes emits
    ("1.2E6", D(1200000)),
])
def test_parse_amount_accepts(raw, expected):
    assert tb.parse_amount(raw).value == expected


@pytest.mark.parametrize("raw", [None, "", "  ", "-", "nil", "n/a"])
def test_parse_amount_blank_flagged(raw):
    """Blank must be zero AND flagged, so callers can tell 'absent' from 'zero'."""
    parsed = tb.parse_amount(raw)
    assert parsed.value == 0
    assert parsed.was_blank is True


def test_parse_amount_real_zero_is_not_blank():
    assert tb.parse_amount("0").was_blank is False
    assert tb.parse_amount(0).was_blank is False


@pytest.mark.parametrize("raw,value,side", [
    ("1,234 Dr", D(1234), DEBIT),
    ("1234Cr", D(1234), CREDIT),
    ("Dr 1234", D(1234), DEBIT),
    ("1234 CR.", D(1234), CREDIT),
    ("1234 (Cr)", D(1234), CREDIT),
    ("1,23,456.00 Dr", D("123456.00"), DEBIT),
    ("500 debit", D(500), DEBIT),
    ("500 credit", D(500), CREDIT),
])
def test_parse_amount_dr_cr_markers(raw, value, side):
    parsed = tb.parse_amount(raw)
    assert parsed.value == value
    assert parsed.side is side


def test_parse_amount_side_only_cell_is_blank_with_side():
    parsed = tb.parse_amount("Cr")
    assert parsed.was_blank is True
    assert parsed.side is CREDIT


@pytest.mark.parametrize("raw,expected", [
    ("12 34", D(1234)),          # NBSP
    ("12 34", D(1234)),         # thin space
    ("12 34", D(1234)),         # narrow no-break space
])
def test_parse_amount_unicode_space_separators(raw, expected):
    assert tb.parse_amount(raw).value == expected


@pytest.mark.parametrize("raw", [
    "notanumber", "Total", "see note", "12%", "1,2,3.4.5",
    "5 Dr Cr",           # two markers in one cell
    True, False,         # bool is not an amount
    "abc123",
])
def test_parse_amount_hard_errors(raw):
    with pytest.raises(tb.AmountParseError):
        tb.parse_amount(raw)


def test_parse_amount_rejects_ambiguous_parenthesised_sign():
    """`(-500)` is -(-500)=+500 arithmetically, but no real file means that.
    Refuse rather than silently choose a sign on a financial figure."""
    with pytest.raises(tb.AmountParseError, match="ambiguous sign"):
        tb.parse_amount("(-500)")


def test_parse_amount_rejects_oversized_value():
    """Numeric(15,2) overflows above 13 integer digits. Catch it at parse time as a
    row error instead of a 500 at DB flush, which is what happened before."""
    with pytest.raises(tb.AmountParseError, match="too large"):
        tb.parse_amount("99999999999999")
    # just under the limit is fine
    assert tb.parse_amount("9999999999999.99").value == D("9999999999999.99")


def test_parse_amount_rejects_date():
    from datetime import date
    with pytest.raises(tb.AmountParseError):
        tb.parse_amount(date(2026, 3, 31))


# --- decimal separator resolution ---

@pytest.mark.parametrize("raw,style,expected", [
    ("1.234,56", "auto", D("1234.56")),    # last separator wins -> comma decimal
    ("1,234.56", "auto", D("1234.56")),    # last separator wins -> dot decimal
    ("1.234,56", "comma", D("1234.56")),
    ("1,234.56", "dot", D("1234.56")),
    ("1,234", "auto", D(1234)),            # 3 trailing digits -> grouping
    ("1,23", "auto", D("1.23")),           # 1-2 trailing digits -> decimal comma
    ("1,234,567", "auto", D(1234567)),     # multiple commas -> grouping
    ("1,23,456", "auto", D(123456)),       # Indian grouping
    ("1,234", "comma", D("1.234")),
])
def test_parse_amount_decimal_styles(raw, style, expected):
    assert tb.parse_amount(raw, decimal_style=style).value == expected


# ---------------------------------------------------------------------------
# canonical_net_debit -- the only place a sign is chosen
# ---------------------------------------------------------------------------

def test_canonical_explicit_side_wins_over_everything():
    """Rung 1: the source told us the side; nothing may override it."""
    nd, unresolved = tb.canonical_net_debit(
        value=D(-500), explicit_side=DEBIT,
        convention=TBSignConvention.magnitude, group_nature=CREDIT,
    )
    assert (nd, unresolved) == (D(500), False)

    nd, unresolved = tb.canonical_net_debit(
        value=D(500), explicit_side=CREDIT,
        convention=TBSignConvention.magnitude, group_nature=DEBIT,
    )
    assert (nd, unresolved) == (D(-500), False)


@pytest.mark.parametrize("convention", [
    TBSignConvention.signed, TBSignConvention.derived, TBSignConvention.explicit,
])
def test_canonical_signed_source_passes_through(convention):
    """Rung 2: a signed source is already a net debit -- do not touch it.
    This is what preserves a contra balance."""
    for v in (D(500), D(-500), D(0)):
        assert tb.canonical_net_debit(
            value=v, convention=convention, group_nature=CREDIT,
        ) == (v, False)


def test_canonical_magnitude_uses_group_nature():
    """Rung 3: an all-positive source needs the mapping to place the sign."""
    assert tb.canonical_net_debit(
        value=D(500), convention=TBSignConvention.magnitude, group_nature=DEBIT,
    ) == (D(500), False)
    assert tb.canonical_net_debit(
        value=D(500), convention=TBSignConvention.magnitude, group_nature=CREDIT,
    ) == (D(-500), False)


def test_canonical_unmapped_magnitude_is_flagged_not_guessed():
    """Rung 4: no marker and no nature -> flag it, never silently guess."""
    nd, unresolved = tb.canonical_net_debit(
        value=D(-500), convention=TBSignConvention.magnitude, group_nature=None,
    )
    assert (nd, unresolved) == (D(500), True)


# ---------------------------------------------------------------------------
# present() -- the symmetry that replaced abs()
# ---------------------------------------------------------------------------

def test_present_orients_onto_natural_side():
    assert tb.present(D(1000), DEBIT) == D(1000)       # asset debit balance
    assert tb.present(D(-600), CREDIT) == D(600)       # liability credit balance


def test_present_is_symmetric_so_contra_balances_reduce_their_group():
    """THE regression the old abs() caused.

    A credit-natured group holding a DEBIT balance -- Reserves & Surplus with an
    accumulated deficit, or a sales-returns ledger under Revenue -- must come back
    NEGATIVE so it subtracts. abs() returned +250 and inflated the group instead.
    """
    assert tb.present(D(250), CREDIT) == D(-250)
    assert tb.present(D(-250), DEBIT) == D(-250)


def test_present_unknown_nature_passes_through():
    assert tb.present(D(-250), None) == D(-250)


# ---------------------------------------------------------------------------
# validate_column_map
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmap,ok", [
    ({"ledger_name": "Ledger"}, False),                                    # no balance source
    ({"ledger_name": "Ledger", "closing_balance": "Closing"}, True),
    ({"ledger_name": "Ledger", "debit": "Dr", "credit": "Cr"}, True),
    ({"ledger_name": "Ledger", "debit": "Dr"}, False),                     # only one movement col
    ({"ledger_name": "Ledger", "closing_debit": "ClDr"}, False),
    ({"ledger_name": "Ledger", "closing_debit": "ClDr", "closing_credit": "ClCr"}, True),
    ({"closing_balance": "Closing"}, False),                               # no ledger_name
    ({"ledger_name": "L", "opening_balance": "Op", "debit": "D", "credit": "C"}, True),
])
def test_validate_column_map(cmap, ok):
    assert (tb.validate_column_map(cmap) == []) is ok


def test_validate_column_map_lists_acceptable_combinations():
    errors = tb.validate_column_map({"ledger_name": "L"})
    assert any("closing_balance" in e for e in errors)


# ---------------------------------------------------------------------------
# normalize_amounts
# ---------------------------------------------------------------------------

def P(raw):
    return tb.parse_amount(raw)


def test_normalize_signed_closing_column_only():
    """A single signed closing column: the minimum viable trial balance."""
    n = tb.normalize_amounts(closing=P("-600"), convention=TBSignConvention.signed)
    assert n.closing_net_debit == D(-600)
    assert n.opening_net_debit == D(0)
    assert n.credit == D(600) and n.debit == D(0)      # movement derived
    assert "closing_balance" not in n.derived
    assert "debit" in n.derived and "credit" in n.derived
    assert n.row_consistent is None                     # nothing to check against


def test_normalize_derives_closing_from_movements():
    n = tb.normalize_amounts(
        opening=P("100"), debit=P("50"), credit=P("20"),
        convention=TBSignConvention.derived,
    )
    assert n.closing_net_debit == D(130)
    assert "closing_balance" in n.derived
    assert n.row_consistent is None                     # closing was derived, not checked


def test_normalize_blank_movement_cell_is_zero_not_an_error():
    """The headline import fix: a trial balance fills only ONE of Dr/Cr per row."""
    n = tb.normalize_amounts(
        opening=P("100"), debit=P("50"), credit=P(""), closing=P("150"),
        convention=TBSignConvention.signed,
    )
    assert (n.debit, n.credit, n.closing_net_debit) == (D(50), D(0), D(150))
    assert n.row_consistent is True


def test_normalize_closing_dr_cr_pair_is_self_describing():
    n = tb.normalize_amounts(
        closing_debit=P(""), closing_credit=P("600"),
        convention=TBSignConvention.magnitude,      # convention is irrelevant here
    )
    assert n.closing_net_debit == D(-600)
    assert n.sign_unresolved is False


def test_normalize_opening_dr_cr_pair():
    n = tb.normalize_amounts(
        opening_debit=P("100"), opening_credit=P(""),
        closing=P("150"), convention=TBSignConvention.signed,
    )
    assert n.opening_net_debit == D(100)


def test_normalize_single_movement_column_is_signed():
    n = tb.normalize_amounts(
        opening=P("100"), debit=P("-30"), closing=P("70"),
        convention=TBSignConvention.signed,
    )
    assert (n.debit, n.credit) == (D(0), D(30))


def test_normalize_side_marker_moves_amount_to_other_column():
    n = tb.normalize_amounts(
        debit=P("500 Cr"), credit=P(""), convention=TBSignConvention.signed,
    )
    assert (n.debit, n.credit) == (D(0), D(500))


def test_normalize_keeps_source_closing_on_conflict_and_reports_it():
    """An audit tool must not silently repair the auditee's stated figure."""
    n = tb.normalize_amounts(
        opening=P("100"), debit=P("50"), credit=P("0"), closing=P("999"),
        convention=TBSignConvention.signed,
    )
    assert n.closing_net_debit == D(999)          # source wins
    assert n.row_consistent is False
    assert any("150" in note for note in n.notes)  # the expected figure is reported


def test_normalize_magnitude_without_nature_is_unresolved():
    n = tb.normalize_amounts(closing=P("600"), convention=TBSignConvention.magnitude)
    assert n.sign_unresolved is True


def test_normalize_magnitude_with_nature_resolves():
    n = tb.normalize_amounts(
        closing=P("600"), convention=TBSignConvention.magnitude, group_nature=CREDIT,
    )
    assert n.closing_net_debit == D(-600)
    assert n.sign_unresolved is False


def test_normalize_explicit_convention_beats_legacy_credit_sign_option():
    n = tb.normalize_amounts(
        closing=P("600"), convention=TBSignConvention.signed,
        credit_sign="positive", group_nature=CREDIT,
    )
    assert n.closing_net_debit == D(600)


def test_normalize_negative_pair_movements_move_to_opposite_side():
    n = tb.normalize_amounts(
        debit=P("-100"), credit=P("-25"),
        convention=TBSignConvention.derived,
    )
    assert n.debit == D(25)
    assert n.credit == D(100)
    assert n.closing_net_debit == D(-75)
    assert any("opposite" in note for note in n.notes)


# ---------------------------------------------------------------------------
# detect_sign_convention
# ---------------------------------------------------------------------------

def test_detect_signed_is_proven_when_closings_sum_to_zero():
    closings = [P("1000"), P("-600"), P("-500"), P("100")]
    r = tb.detect_sign_convention(closings, has_closing_column=True)
    assert r.convention is TBSignConvention.signed
    assert r.confidence == "proven"


def test_detect_magnitude_when_no_negatives_and_movements_agree():
    closings = [P("1000"), P("600")]
    r = tb.detect_sign_convention(
        closings, has_closing_column=True, sum_debit=D(50), sum_credit=D(50),
    )
    assert r.convention is TBSignConvention.magnitude
    assert r.confidence == "likely"


def test_detect_magnitude_ambiguous_without_movement_evidence():
    r = tb.detect_sign_convention([P("1000"), P("600")], has_closing_column=True)
    assert r.convention is TBSignConvention.magnitude
    assert r.confidence == "ambiguous"


def test_detect_signed_ambiguous_when_negatives_but_nonzero_sum():
    """Usually a partially hand-edited file -- flag it rather than trust it."""
    r = tb.detect_sign_convention([P("1000"), P("-600")], has_closing_column=True)
    assert r.convention is TBSignConvention.signed
    assert r.confidence == "ambiguous"
    assert r.sum_closing == D(400)


def test_detect_explicit_from_markers():
    r = tb.detect_sign_convention([P("1000 Dr"), P("600 Cr")], has_closing_column=True)
    assert r.convention is TBSignConvention.explicit
    assert r.confidence == "proven"
    assert r.explicit_marker_count == 2


def test_detect_explicit_from_closing_pair():
    r = tb.detect_sign_convention([], has_closing_column=True, has_closing_pair=True)
    assert r.convention is TBSignConvention.explicit


def test_detect_derived_when_no_closing_column():
    r = tb.detect_sign_convention([], has_closing_column=False)
    assert r.convention is TBSignConvention.derived
    assert r.confidence == "proven"


# ---------------------------------------------------------------------------
# header detection / junk rows
# ---------------------------------------------------------------------------

def test_detect_header_row_skips_title_preamble():
    rows = [
        ["XYZ Private Limited", None, None, None],
        ["Trial Balance as at 31-03-2026", None, None, None],
        [None, None, None, None],
        ["Ledger Code", "Ledger Name", "Debit", "Credit"],
        ["1001", "Cash", 500, 0],
    ]
    assert tb.detect_header_row(rows) == 3


def test_detect_header_row_returns_zero_when_header_is_first():
    """Regression: the common case must not be 'improved' into something else."""
    rows = [
        ["Ledger Code", "Ledger Name", "Debit", "Credit"],
        ["1001", "Cash", 500, 0],
        ["1002", "Sales", 0, 500],
    ]
    assert tb.detect_header_row(rows) == 0


def test_detect_header_row_falls_back_to_zero_with_no_recognisable_header():
    rows = [[1, 2, 3], [4, 5, 6]]
    assert tb.detect_header_row(rows) == 0


def test_build_headers_forward_fills_merged_cells():
    rows = [
        ["Ledger", "Closing Balance", None],
        ["", "Debit", "Credit"],
        ["Cash", 500, 0],
    ]
    headers, first_data = tb.build_headers(rows, 0)
    assert headers == ["Ledger", "Closing Balance Debit", "Closing Balance Credit"]
    assert first_data == 2


def test_build_headers_dedupes_collisions():
    rows = [["Ledger", "Amount", "Amount"], ["Cash", 1, 2]]
    headers, first_data = tb.build_headers(rows, 0)
    assert headers == ["Ledger", "Amount", "Amount (2)"]
    assert first_data == 1


def test_build_headers_single_row_header_untouched():
    rows = [["Ledger Name", "Debit", "Credit"], ["Cash", 500, 0]]
    headers, first_data = tb.build_headers(rows, 0)
    assert headers == ["Ledger Name", "Debit", "Credit"]
    assert first_data == 1


def test_suggest_column_map_prefers_longest_synonym():
    headers = ["Ledger Code", "Ledger Name", "Opening Balance",
               "Debit", "Credit", "Closing Balance"]
    suggested = tb.suggest_column_map(headers)
    assert suggested["ledger_name"] == "Ledger Name"
    assert suggested["ledger_code"] == "Ledger Code"
    assert suggested["closing_balance"] == "Closing Balance"
    assert suggested["debit"] == "Debit"


def test_suggest_column_map_drops_single_column_when_pair_present():
    headers = ["Ledger Name", "Closing Balance Debit", "Closing Balance Credit"]
    suggested = tb.suggest_column_map(headers)
    assert "closing_debit" in suggested and "closing_credit" in suggested
    assert "closing_balance" not in suggested


HEADERS = ["Ledger Name", "Debit", "Credit"]
IDX = {"ledger_name": 0, "debit": 1, "credit": 2}


@pytest.mark.parametrize("row,kind", [
    (["Cash", 500, 0], tb.RowKind.data),
    ([None, None, None], tb.RowKind.blank),
    (["", "", ""], tb.RowKind.blank),
    (["Total", 500, 500], tb.RowKind.total),
    (["Grand Total", 500, 500], tb.RowKind.total),
    (["Sub-total", 500, 500], tb.RowKind.total),
    (["Subtotal", 500, 500], tb.RowKind.total),
    (["C/F", 500, 500], tb.RowKind.total),
    (["B/F", 500, 500], tb.RowKind.total),
    (["Carried Forward", 500, 500], tb.RowKind.total),
    (["Closing Total", 500, 500], tb.RowKind.total),
    ([None, 500, 500], tb.RowKind.total),          # the unlabelled bottom line
    (["Current Assets", None, None], tb.RowKind.section),
    (["Ledger Name", "Debit", "Credit"], tb.RowKind.repeated_header),
])
def test_classify_row(row, kind):
    assert tb.classify_row(row, IDX, HEADERS) is kind


# ---------------------------------------------------------------------------
# validate_rows
# ---------------------------------------------------------------------------

def _row(i, name, **kw):
    return tb.RowFigures(row=i, ledger_name=name, amounts=tb.normalize_amounts(**kw))


def test_validate_rows_detects_balanced_file():
    rows = [
        _row(1, "Cash", closing=P("1000"), convention=TBSignConvention.signed),
        _row(2, "Sales", closing=P("-1000"), convention=TBSignConvention.signed),
    ]
    v = tb.validate_rows(rows)
    assert v.sum_net_debit == D(0)
    assert v.balanced is True
    assert v.row_count == 2


def test_validate_rows_reports_out_of_balance_without_blocking():
    rows = [
        _row(1, "Cash", closing=P("1000"), convention=TBSignConvention.signed),
        _row(2, "Sales", closing=P("-600"), convention=TBSignConvention.signed),
    ]
    v = tb.validate_rows(rows)
    assert v.balanced is False
    assert v.sum_net_debit == D(400)


def test_validate_rows_collects_row_level_inconsistencies():
    rows = [
        _row(1, "Cash", opening=P("100"), debit=P("50"), credit=P("0"),
             closing=P("999"), convention=TBSignConvention.signed),
    ]
    v = tb.validate_rows(rows)
    assert v.inconsistent_count == 1
    assert v.inconsistent_rows[0]["expected"] == 150.0
    assert v.inconsistent_rows[0]["found"] == 999.0
    assert v.inconsistent_rows[0]["ledger_name"] == "Cash"


def test_validate_rows_counts_unresolved_signs():
    rows = [_row(1, "Cash", closing=P("100"), convention=TBSignConvention.magnitude)]
    assert tb.validate_rows(rows).sign_unresolved_count == 1


# ---------------------------------------------------------------------------
# build_figures + summarize
# ---------------------------------------------------------------------------

class FakeAccount:
    """Duck-typed stand-in for TrialBalanceAccount, so these tests need no ORM."""
    def __init__(self, name, closing_net_debit, group_id=None, code=None,
                 opening=0, debit=0, credit=0, sign_unresolved=False):
        self.id = uuid.uuid4()
        self.ledger_name = name
        self.ledger_code = code
        self.mapped_group_id = group_id
        self.closing_net_debit = Decimal(str(closing_net_debit))
        self.opening_net_debit = Decimal(str(opening))
        self.debit = Decimal(str(debit))
        self.credit = Decimal(str(credit))
        self.sign_unresolved = sign_unresolved


G_ASSET = uuid.uuid4()
G_LIAB = uuid.uuid4()
G_RESERVES = uuid.uuid4()
G_INCOME = uuid.uuid4()
G_EXPENSE = uuid.uuid4()

PATHS = {
    G_ASSET: ["Assets", "Cash and Cash Equivalents"],
    G_LIAB: ["Liabilities", "Trade Payables"],
    G_RESERVES: ["Liabilities", "Reserves & Surplus"],
    G_INCOME: ["Income", "Revenue from Operations"],
    G_EXPENSE: ["Expenditure", "Other Expenses"],
}
NATURES = {
    G_ASSET: DEBIT, G_LIAB: CREDIT, G_RESERVES: CREDIT,
    G_INCOME: CREDIT, G_EXPENSE: DEBIT,
}


def _summary(accounts, adjustments=None):
    figures = tb.build_figures(accounts, PATHS, NATURES, adjustments)
    return figures, tb.summarize(figures)


def test_summarize_signed_trial_balance():
    accounts = [
        FakeAccount("Cash", 1000, G_ASSET),
        FakeAccount("Trade Payables", -600, G_LIAB),
        FakeAccount("Sales", -500, G_INCOME),
        FakeAccount("Rent", 100, G_EXPENSE),
    ]
    _, s = _summary(accounts)
    assert s.assets == D(1000)
    assert s.liabilities == D(600)
    assert s.income == D(500)
    assert s.expenditure == D(100)
    assert s.net_profit == D(400)
    assert s.liabilities_plus_equity == D(1000)
    assert s.difference == D(0)
    assert s.balanced is True


def test_summarize_net_loss():
    accounts = [
        FakeAccount("Cash", 200, G_ASSET),
        FakeAccount("Trade Payables", -600, G_LIAB),
        FakeAccount("Sales", -100, G_INCOME),
        FakeAccount("Rent", 500, G_EXPENSE),
    ]
    _, s = _summary(accounts)
    assert s.net_profit == D(-400)
    assert s.liabilities_plus_equity == D(200)
    assert s.balanced is True


def test_summarize_contra_credit_group_reduces_liabilities():
    """The bug the old abs() caused, at the summarizer level.

    Reserves & Surplus carrying an accumulated DEFICIT (a debit balance of 250)
    must bring Liabilities down to 350, not up to 850.
    """
    accounts = [
        FakeAccount("Trade Payables", -600, G_LIAB),
        FakeAccount("Accumulated Deficit", 250, G_RESERVES),
    ]
    _, s = _summary(accounts)
    assert s.liabilities == D(350)


def test_summarize_sales_returns_reduces_income():
    accounts = [
        FakeAccount("Sales", -500, G_INCOME),
        FakeAccount("Sales Returns", 100, G_INCOME),
    ]
    _, s = _summary(accounts)
    assert s.income == D(400)


def test_summarize_difference_equals_sum_of_net_debits():
    """The algebraic identity that makes one `balanced` definition possible:

        assets - (liabilities + net_profit) == sum of every mapped net debit

    so the import check, the grid check and the report check are the same number.
    """
    accounts = [
        FakeAccount("Cash", 1000, G_ASSET),
        FakeAccount("Trade Payables", -600, G_LIAB),
        FakeAccount("Sales", -500, G_INCOME),
        FakeAccount("Rent", 250, G_EXPENSE),
    ]
    figures, s = _summary(accounts)
    expected = sum(f.final_net_debit for f in figures)
    assert s.difference == expected
    assert s.difference == s.assets - s.liabilities_plus_equity


def test_summarize_applies_adjustments_with_correct_polarity():
    """An adjustment is a net DEBIT, so it adds to Assets and subtracts from Income."""
    cash = FakeAccount("Cash", 1000, G_ASSET)
    sales = FakeAccount("Sales", -500, G_INCOME)
    adjustments = {cash.id: Decimal(50), sales.id: Decimal(-50)}
    _, s = _summary([cash, sales], adjustments)
    assert s.assets == D(1050)
    assert s.income == D(550)


def test_summarize_excludes_unmapped_from_statement_totals_but_reports_it():
    accounts = [
        FakeAccount("Cash", 1000, G_ASSET),
        FakeAccount("Suspense", 999, None),
    ]
    _, s = _summary(accounts)
    assert s.assets == D(1000)
    assert s.unmapped_count == 1
    assert s.unmapped_net_debit == D(999)
    assert s.difference == D(1000)
    assert s.difference_including_unmapped == D(1999)
    assert s.statement_ready is False


def test_summarize_statement_ready_requires_complete_resolved_mapping():
    _, ready = _summary([
        FakeAccount("Cash", 1000, G_ASSET),
        FakeAccount("Loan", -1000, G_LIAB),
    ])
    assert ready.statement_ready is True


def test_unmapped_ledger_keeps_its_adjustment():
    """Regression: the old code set `final = closing` for unmapped ledgers, so the
    row violated `closing + adjustment == final` in the rendered preview."""
    suspense = FakeAccount("Suspense", 100, None)
    figures, _ = _summary([suspense], {suspense.id: Decimal(25)})
    f = figures[0]
    assert f.final_net_debit == D(125)
    assert f.net_debit + f.adjustment == f.final_net_debit


def test_summarize_counts_unresolved_nature_separately_from_unmapped():
    """A ledger mapped under a company-created top group has no nature. It must not
    silently vanish into the statement totals -- it gets counted and reported."""
    custom = uuid.uuid4()
    paths = {**PATHS, custom: ["Suspense Group", "Something"]}
    natures = {**NATURES, custom: None}
    accounts = [FakeAccount("Cash", 1000, G_ASSET), FakeAccount("Odd", 50, custom)]
    figures = tb.build_figures(accounts, paths, natures, None)
    s = tb.summarize(figures)
    assert s.unresolved_nature_count == 1
    assert s.unmapped_count == 0
    assert s.assets == D(1000)
    assert s.difference == D(1000)
    assert s.difference_including_unmapped == D(1050)


def test_summarize_group_subtotals_are_ordered_and_nature_tagged():
    accounts = [
        FakeAccount("Rent", 100, G_EXPENSE),
        FakeAccount("Cash", 1000, G_ASSET),
        FakeAccount("Suspense", 5, None),
        FakeAccount("Sales", -500, G_INCOME),
    ]
    _, s = _summary(accounts)
    assert [g.key for g in s.groups] == ["Assets", "Income", "Expenditure", "Unmapped"]
    by_key = {g.key: g for g in s.groups}
    assert by_key["Income"].nature is CREDIT
    assert by_key["Income"].presented == D(500)
    assert by_key["Unmapped"].nature is None


def test_summarize_equity_includes_net_profit_and_reserve_subgroups():
    accounts = [
        FakeAccount("Cash", 1400, G_ASSET),
        FakeAccount("Share Capital", -1000, G_RESERVES),   # mapped under Reserves path
        FakeAccount("Sales", -500, G_INCOME),
        FakeAccount("Rent", 100, G_EXPENSE),
    ]
    _, s = _summary(accounts)
    assert s.net_profit == D(400)
    assert s.equity == D(1400)          # 1000 reserves + 400 profit


# --- rounding ---

def test_line_rounding_happens_before_summing():
    """Each line is quantized to 2dp before anything is added, so a section
    subtotal is exactly the sum of the values the user can see. The old code
    rounded lines but accumulated totals unrounded, drifting by cents."""
    accounts = [FakeAccount(f"L{i}", "10.005", G_ASSET) for i in range(3)]
    figures, s = _summary(accounts)
    assert [f.presented_final for f in figures] == [D("10.01")] * 3
    assert s.assets == D("30.03")
    assert s.assets == sum(f.presented_final for f in figures)


def test_group_subtotal_equals_sum_of_its_displayed_lines():
    accounts = [
        FakeAccount("A", "33.333", G_ASSET),
        FakeAccount("B", "33.333", G_ASSET),
        FakeAccount("C", "33.334", G_ASSET),
    ]
    figures, s = _summary(accounts)
    subtotal = next(g for g in s.groups if g.key == "Assets").presented
    assert subtotal == sum(f.presented_final for f in figures)


# --- the synthetic balancing figure ---

def test_make_profit_figure_presents_as_a_credit_under_reserves():
    f = tb.make_profit_figure(D(400))
    assert f.top_group == "Liabilities"
    assert f.group_path == ["Liabilities", "Reserves & Surplus"]
    assert f.nature is CREDIT
    assert f.presented_final == D(400)
    assert f.final_net_debit == D(-400)
    assert f.is_synthetic is True
    assert f.ledger_id is None
    assert "Profit" in f.ledger_name


def test_make_profit_figure_labels_a_loss():
    assert "Loss" in tb.make_profit_figure(D(-400)).ledger_name


def test_synthetic_figure_is_excluded_from_difference():
    """It IS the balancing figure, so counting it would double-count."""
    accounts = [
        FakeAccount("Cash", 1000, G_ASSET),
        FakeAccount("Trade Payables", -600, G_LIAB),
        FakeAccount("Sales", -500, G_INCOME),
        FakeAccount("Rent", 100, G_EXPENSE),
    ]
    figures, s = _summary(accounts)
    with_profit = [*figures, tb.make_profit_figure(s.net_profit)]
    s2 = tb.summarize(with_profit)
    assert s2.difference == s.difference == D(0)
    assert s2.liabilities == s.liabilities


def test_balance_sheet_renders_balanced_with_the_synthetic_line():
    """Total Liabilities and Equity (as rendered, including the profit row) must
    equal Total Assets -- otherwise the statement visibly does not balance."""
    accounts = [
        FakeAccount("Cash", 1000, G_ASSET),
        FakeAccount("Trade Payables", -600, G_LIAB),
        FakeAccount("Sales", -500, G_INCOME),
        FakeAccount("Rent", 100, G_EXPENSE),
    ]
    figures, s = _summary(accounts)
    rendered = [*figures, tb.make_profit_figure(s.net_profit)]
    liab_rows = sum(f.presented_final for f in rendered if f.top_group == "Liabilities")
    asset_rows = sum(f.presented_final for f in rendered if f.top_group == "Assets")
    assert liab_rows == asset_rows == D(1000)
    assert liab_rows == s.liabilities_plus_equity
