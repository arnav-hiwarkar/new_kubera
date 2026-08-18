"""Canonical trial-balance accounting core.

ONE internal representation: a signed **net debit** per ledger -- debit positive,
credit negative -- normalized at the import boundary. Combined with a persisted
`nature` (debit|credit) on each top-level ledger group, presentation becomes a
single function and every total becomes plain addition::

    present(net_debit, nature) =  net_debit   if nature is debit
                               = -net_debit   if nature is credit

    assets      =  sum nd(Assets)        liabilities = -sum nd(Liabilities)
    expenditure =  sum nd(Expenditure)   income      = -sum nd(Income)
    net_profit  = income - expenditure
    difference  = assets - (liabilities + net_profit) = sum nd(all mapped ledgers)

`difference` collapsing to "does the mapped trial balance sum to zero" is the whole
point: it is the *same expression* used by the import check, the trial-balance grid
and the report, so those three can never disagree. There is no abs() anywhere and
no branching on group names, which is what makes contra balances (an accumulated
deficit in Reserves & Surplus, a sales-returns ledger under Revenue) correctly
*reduce* their credit-natured group instead of inflating it.

This module is deliberately pure and synchronous -- no DB, no I/O -- so it can be
unit-tested exhaustively without fixtures. `import_service` keeps only file/sheet
I/O; `trial_balance_query` is the thin async layer that feeds this module from the
database.

Arithmetic runs in `Decimal` and each line is quantized to 2dp BEFORE anything is
summed, so a section subtotal is always exactly the sum of its displayed lines.
Floats appear only at the Pydantic boundary.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from app.models.auditease import BalanceNature, TBSignConvention

# Numeric(15, 2) tops out at 9_999_999_999_999.99 -- reject earlier so an oversized
# cell is a row error at parse time instead of a 500 at flush.
MAX_MAGNITUDE = Decimal("1e13")
TWO_PLACES = Decimal("0.01")
EPSILON = Decimal("0.01")


class AmountParseError(ValueError):
    """A cell could not be interpreted as a monetary amount."""


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

def to_decimal(v: Any) -> Decimal:
    """Coerce a float/int/Decimal/str to Decimal without float noise."""
    if isinstance(v, Decimal):
        return v
    if isinstance(v, int):
        return Decimal(v)
    return Decimal(str(v))


def q2(v: Any) -> Decimal:
    """Quantize to 2dp, half-up. Applied per line before any summing."""
    return to_decimal(v).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def present(net_debit: Any, nature: BalanceNature | None) -> Decimal:
    """Orient a signed net debit onto its group's natural side.

    Symmetric by construction, which is the fix for the old abs(): a *debit*
    balance on a credit-natured group comes back negative and therefore reduces
    that group, exactly as an accumulated deficit or a contra-revenue ledger should.
    """
    nd = to_decimal(net_debit)
    if nature is BalanceNature.credit:
        return -nd
    return nd


def is_zero(v: Any, eps: Decimal = EPSILON) -> bool:
    return abs(to_decimal(v)) < eps


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------

# Tokens that mean "nothing here" rather than "unparseable".
BLANK_TOKENS = {"", "-", "–", "—", ".", "nil", "n/a", "na", "none", "--"}

_SIDE_TOKEN = r"(?:dr|cr|debit|credit)"
_SIDE_TRAIL_RE = re.compile(rf"\(?\s*({_SIDE_TOKEN})\s*\.?\s*\)?\s*$", re.I)
_SIDE_LEAD_RE = re.compile(rf"^\(?\s*({_SIDE_TOKEN})\s*\.?\s*\)?\s*", re.I)
_CURRENCY_WORDS_RE = re.compile(r"(?i)(?:rs\.|rs|inr)\s*")
_SCI_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?[eE][+-]?\d+$")
# A cell that is *only* a Dr/Cr marker, e.g. "Cr" or "(Cr)" -- a side with no figure.
_ONLY_SIDE_RE = re.compile(rf"^\(?\s*({_SIDE_TOKEN})\s*\.?\s*\)?$", re.I)
_SEPARATORS_RE = re.compile(r"[\s   '_]")

_SIDE_BY_TOKEN = {
    "dr": BalanceNature.debit,
    "debit": BalanceNature.debit,
    "cr": BalanceNature.credit,
    "credit": BalanceNature.credit,
}


@dataclass(frozen=True)
class ParsedAmount:
    """One cell, parsed but with its Dr/Cr marker NOT yet applied to the sign.

    Why the marker is only a tag: in a *Debit* column "Cr" means "this figure
    actually belongs in the credit column", while in a single signed *Closing*
    column it means "negate this". Only the caller knows which column it is
    reading, so applying the sign here would be guessing.
    """
    value: Decimal
    side: BalanceNature | None = None
    was_blank: bool = False

    @property
    def magnitude(self) -> Decimal:
        return abs(self.value)


def _extract_side(s: str) -> tuple[str, BalanceNature | None]:
    """Strip leading/trailing Dr/Cr markers. Two markers in one cell is an error."""
    only = _ONLY_SIDE_RE.match(s)
    if only:
        # A side with no figure -- treat the amount as blank but keep the side.
        return "", _SIDE_BY_TOKEN[only.group(1).lower()]

    found: list[str] = []
    while True:
        m = _SIDE_TRAIL_RE.search(s)
        if not m or m.start() == 0:
            break
        found.append(m.group(1).lower())
        s = s[: m.start()].strip()
    m = _SIDE_LEAD_RE.match(s)
    if m and m.end() < len(s):
        found.append(m.group(1).lower())
        s = s[m.end():].strip()
    if len(found) > 1:
        raise AmountParseError("cell carries more than one Dr/Cr marker")
    return s, _SIDE_BY_TOKEN[found[0]] if found else None


def _resolve_separators(s: str, decimal_style: str) -> str:
    """Decide which of '.' and ',' is the decimal separator, strip the other."""
    has_dot = "." in s
    has_comma = "," in s
    if decimal_style == "dot":
        return s.replace(",", "")
    if decimal_style == "comma":
        return s.replace(".", "").replace(",", ".")
    # auto
    if has_dot and has_comma:
        # Whichever appears last is the decimal point.
        if s.rfind(",") > s.rfind("."):
            return s.replace(".", "").replace(",", ".")
        return s.replace(",", "")
    if has_comma:
        parts = s.split(",")
        # A single comma trailed by 1-2 digits cannot be thousands grouping
        # (the final group would have to be 3 digits), so it is a decimal comma.
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
            return s.replace(",", ".")
        return s.replace(",", "")
    return s


def parse_amount(raw: Any, *, decimal_style: str = "auto") -> ParsedAmount:
    """Parse a spreadsheet cell into a signed Decimal plus an optional Dr/Cr tag.

    Blank is ZERO, never an error -- the old behaviour raised on an empty cell,
    which made the whole row invalid and silently dropped the ledger. A trial
    balance that fills only one of Dr/Cr per row is the normal shape, so that
    single decision is what let most real files import at all.
    """
    if raw is None:
        return ParsedAmount(Decimal(0), None, True)
    if isinstance(raw, bool):
        raise AmountParseError("a boolean is not an amount")
    if isinstance(raw, (datetime, date)):
        raise AmountParseError("a date is not an amount")
    if isinstance(raw, (int, float, Decimal)):
        return ParsedAmount(_checked(to_decimal(raw)), None, False)

    s = str(raw).strip()
    if s.casefold() in BLANK_TOKENS:
        return ParsedAmount(Decimal(0), None, True)
    if "%" in s:
        raise AmountParseError("percentages are not amounts")

    s, side = _extract_side(s)
    if s.casefold() in BLANK_TOKENS:
        # e.g. a lone "Dr" with no figure
        return ParsedAmount(Decimal(0), side, True)

    # Accounting parentheses / brackets.
    paren_neg = False
    if (s.startswith("(") and s.endswith(")")) or (s.startswith("[") and s.endswith("]")):
        paren_neg = True
        s = s[1:-1].strip()

    for ch in "₹$€£¥":
        s = s.replace(ch, "")
    s = _CURRENCY_WORDS_RE.sub("", s)
    s = s.replace("−", "-").replace("－", "-")
    s = _SEPARATORS_RE.sub("", s)
    if s.startswith("–") or s.startswith("—"):
        s = "-" + s[1:]

    # Trailing sign, as emitted by some ERPs: "1234-".
    trailing_neg = False
    if s.endswith("-"):
        trailing_neg = True
        s = s[:-1].strip()
    elif s.endswith("+"):
        s = s[:-1].strip()

    explicit_sign = s.startswith("-") or s.startswith("+")
    if paren_neg and (explicit_sign or trailing_neg):
        # "(-500)" means -(-500) = +500 arithmetically, but no real file means that.
        # Refuse rather than silently pick a sign on a financial figure.
        raise AmountParseError("ambiguous sign: parentheses around an explicit sign")

    if not s or s in {"-", "+"}:
        raise AmountParseError(f"not a number: {raw!r}")

    if _SCI_RE.match(s):
        val = to_decimal(float(s))
    else:
        s = _resolve_separators(s, decimal_style)
        try:
            val = Decimal(s)
        except (InvalidOperation, ArithmeticError, ValueError):
            raise AmountParseError(f"not a number: {raw!r}")

    if paren_neg or trailing_neg:
        val = -abs(val)
    return ParsedAmount(_checked(val), side, False)


def _checked(v: Decimal) -> Decimal:
    if not v.is_finite():
        raise AmountParseError("amount is not finite")
    if abs(v) >= MAX_MAGNITUDE:
        raise AmountParseError("value too large to store (max 13 digits before the decimal)")
    return v


# ---------------------------------------------------------------------------
# The sign decision -- the ONLY place a sign is ever chosen
# ---------------------------------------------------------------------------

def canonical_net_debit(
    *,
    value: Any,
    explicit_side: BalanceNature | None = None,
    convention: TBSignConvention,
    group_nature: BalanceNature | None = None,
) -> tuple[Decimal, bool]:
    """Return (net_debit, sign_unresolved) in strict precedence order.

    1. An explicit Dr/Cr marker always wins -- the source told us the side.
    2. A `signed` or `derived` source is already a net debit; pass it through.
    3. A `magnitude` source needs the group's nature to place the sign.
    4. Otherwise take the magnitude and flag it unresolved, so the UI can ask
       instead of the system silently guessing.
    """
    v = to_decimal(value)
    if explicit_side is not None:
        return (abs(v) if explicit_side is BalanceNature.debit else -abs(v)), False
    if convention in (TBSignConvention.signed, TBSignConvention.derived, TBSignConvention.explicit):
        return v, False
    if group_nature is not None:
        return (abs(v) if group_nature is BalanceNature.debit else -abs(v)), False
    return abs(v), True


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------

NUMERIC_MAP_FIELDS = (
    "opening_balance", "opening_debit", "opening_credit",
    "debit", "credit",
    "closing_balance", "closing_debit", "closing_credit",
)

_ACCEPTABLE_COMBINATIONS = (
    "closing_debit + closing_credit",
    "closing_balance",
    "debit + credit",
    "opening_balance + debit + credit",
)


def validate_column_map(cmap: Mapping[str, Any]) -> list[str]:
    """Return a list of problems; empty means the mapping is sufficient.

    Only `ledger_name` plus ONE balance source is required. The old contract
    demanded all four numeric columns, which rejected the two most common real
    layouts (Dr/Cr only, or a single signed closing column).
    """
    errors: list[str] = []
    if not cmap.get("ledger_name"):
        errors.append("ledger_name must be mapped")

    has = {f: bool(cmap.get(f)) for f in NUMERIC_MAP_FIELDS}
    for label, debit_key, credit_key in (
        ("opening", "opening_debit", "opening_credit"),
        ("closing", "closing_debit", "closing_credit"),
    ):
        if has[debit_key] != has[credit_key]:
            errors.append(
                f"{label} Dr/Cr mapping requires both {debit_key} and {credit_key}"
            )
    sufficient = (
        (has["closing_debit"] and has["closing_credit"])
        or has["closing_balance"]
        or (has["debit"] and has["credit"])
    )
    if not sufficient:
        errors.append(
            "map at least one balance source -- any of: "
            + "; ".join(_ACCEPTABLE_COMBINATIONS)
        )
    return errors


# ---------------------------------------------------------------------------
# Row normalization
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NormalizedAmounts:
    # verbatim source figures (for storage + audit trail)
    opening_balance: Decimal
    debit: Decimal
    credit: Decimal
    closing_balance: Decimal
    # canonical
    opening_net_debit: Decimal
    closing_net_debit: Decimal
    sign_unresolved: bool
    row_consistent: bool | None
    derived: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _pair_net(
    dr: ParsedAmount | None, cr: ParsedAmount | None
) -> tuple[Decimal, bool]:
    """A Dr column + Cr column pair is self-describing: net = |dr| - |cr|."""
    present_any = (dr is not None and not dr.was_blank) or (cr is not None and not cr.was_blank)
    d = dr.magnitude if dr is not None else Decimal(0)
    c = cr.magnitude if cr is not None else Decimal(0)
    return d - c, present_any


def normalize_amounts(
    *,
    opening: ParsedAmount | None = None,
    opening_debit: ParsedAmount | None = None,
    opening_credit: ParsedAmount | None = None,
    debit: ParsedAmount | None = None,
    credit: ParsedAmount | None = None,
    closing: ParsedAmount | None = None,
    closing_debit: ParsedAmount | None = None,
    closing_credit: ParsedAmount | None = None,
    convention: TBSignConvention = TBSignConvention.signed,
    credit_sign: str = "auto",
    group_nature: BalanceNature | None = None,
) -> NormalizedAmounts:
    """Turn one row's parsed cells into source figures plus canonical net debits."""
    derived: list[str] = []
    notes: list[str] = []
    unresolved = False

    # --- opening ---
    if opening_debit is not None or opening_credit is not None:
        opening_nd, _ = _pair_net(opening_debit, opening_credit)
    elif opening is not None:
        opening_nd, u = canonical_net_debit(
            value=opening.value,
            explicit_side=opening.side,
            convention=convention,
            group_nature=group_nature,
        )
        unresolved = unresolved or u
    else:
        opening_nd = Decimal(0)
        derived.append("opening_balance")

    # --- movement ---
    dr_mapped = debit is not None
    cr_mapped = credit is not None
    if dr_mapped and cr_mapped:
        dr_val, cr_val = debit.value, credit.value
        # A Dr/Cr marker inside a movement cell means "belongs in the other column".
        if debit.side is BalanceNature.credit and cr_val == 0:
            dr_val, cr_val = Decimal(0), abs(dr_val)
        if credit.side is BalanceNature.debit and dr_val == 0:
            dr_val, cr_val = abs(cr_val), Decimal(0)
        if dr_val < 0 or cr_val < 0:
            notes.append("negative movement moved to the opposite Dr/Cr column")
        # A negative figure in a side-specific movement column is a reversal, not
        # a positive movement on that same side. Move it across so the stored
        # movement columns remain non-negative without changing the net movement.
        mv_debit = max(dr_val, Decimal(0)) + max(-cr_val, Decimal(0))
        mv_credit = max(cr_val, Decimal(0)) + max(-dr_val, Decimal(0))
    elif dr_mapped or cr_mapped:
        # A single mapped movement column is a *signed* movement.
        only = debit if dr_mapped else credit
        m = only.value if dr_mapped else -only.value
        if only.side is BalanceNature.credit:
            m = -abs(only.value)
        elif only.side is BalanceNature.debit:
            m = abs(only.value)
        mv_debit, mv_credit = max(m, Decimal(0)), max(-m, Decimal(0))
        derived.append("credit" if dr_mapped else "debit")
    else:
        mv_debit = mv_credit = None  # filled in after closing is known

    # --- closing ---
    if closing_debit is not None or closing_credit is not None:
        closing_nd, _ = _pair_net(closing_debit, closing_credit)
    elif closing is not None:
        v = closing.value
        closing_nd, u = canonical_net_debit(
            value=v,
            explicit_side=closing.side,
            convention=convention,
            group_nature=group_nature,
        )
        unresolved = unresolved or u
    else:
        closing_nd = opening_nd + (mv_debit or Decimal(0)) - (mv_credit or Decimal(0))
        derived.append("closing_balance")

    if mv_debit is None:
        movement = closing_nd - opening_nd
        mv_debit, mv_credit = max(movement, Decimal(0)), max(-movement, Decimal(0))
        derived.extend(["debit", "credit"])

    # --- source consistency cross-check ---
    can_check = (
        "opening_balance" not in derived
        and "closing_balance" not in derived
        and "debit" not in derived
        and "credit" not in derived
    )
    row_consistent: bool | None = None
    if can_check:
        expected = opening_nd + mv_debit - mv_credit
        row_consistent = is_zero(expected - closing_nd)
        if not row_consistent:
            # Keep the source's stated closing. An audit tool must not silently
            # repair the auditee's figure -- report the delta instead.
            notes.append(
                f"opening + debit - credit = {q2(expected)} but closing is {q2(closing_nd)}"
            )

    return NormalizedAmounts(
        opening_balance=q2(opening_nd),
        debit=q2(mv_debit),
        credit=q2(mv_credit),
        closing_balance=q2(closing.value if closing is not None else closing_nd),
        opening_net_debit=q2(opening_nd),
        closing_net_debit=q2(closing_nd),
        sign_unresolved=unresolved,
        row_consistent=row_consistent,
        derived=derived,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Sign-convention detection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConventionReport:
    convention: TBSignConvention
    confidence: str  # "proven" | "likely" | "ambiguous"
    negative_count: int
    explicit_marker_count: int
    sum_closing: Decimal
    sum_abs_closing: Decimal
    evidence: list[str] = field(default_factory=list)


def detect_sign_convention(
    closings: Sequence[ParsedAmount],
    *,
    has_closing_column: bool,
    has_closing_pair: bool = False,
    sum_debit: Decimal | None = None,
    sum_credit: Decimal | None = None,
) -> ConventionReport:
    """Infer how the source encoded signs, with an honest confidence level."""
    negatives = sum(1 for c in closings if c.value < 0)
    markers = sum(1 for c in closings if c.side is not None)
    total = sum((c.value for c in closings), Decimal(0))
    total_abs = sum((abs(c.value) for c in closings), Decimal(0))

    def report(conv, conf, *ev):
        return ConventionReport(conv, conf, negatives, markers, q2(total), q2(total_abs), list(ev))

    if has_closing_pair:
        return report(TBSignConvention.explicit, "proven", "closing is a Dr + Cr column pair")
    if markers:
        return report(TBSignConvention.explicit, "proven", f"{markers} cells carry a Dr/Cr marker")
    if not has_closing_column:
        return report(TBSignConvention.derived, "proven", "no closing column; derived from movements")
    if negatives and is_zero(total):
        # A signed column is the only convention under which closings sum to zero.
        return report(TBSignConvention.signed, "proven", "closing balances sum to zero with negatives present")
    if not negatives:
        if sum_debit is not None and sum_credit is not None and is_zero(sum_debit - sum_credit):
            return report(TBSignConvention.magnitude, "likely",
                          "no negatives and debit movements equal credit movements")
        return report(TBSignConvention.magnitude, "ambiguous", "no negative closing balances found")
    return report(TBSignConvention.signed, "ambiguous",
                  f"negatives present but closings sum to {q2(total)}, not zero")


# ---------------------------------------------------------------------------
# Header detection, junk rows, synonyms
# ---------------------------------------------------------------------------

TB_HEADER_SYNONYMS: dict[str, tuple[str, ...]] = {
    "ledger_code": ("ledger code", "code", "account code", "gl code", "a/c code", "acc code"),
    "ledger_name": ("ledger name", "ledger", "particulars", "account name", "account",
                    "description", "name", "head", "gl name"),
    "opening_balance": ("opening balance", "opening", "op bal", "opening bal", "balance b/f",
                        "brought forward"),
    "opening_debit": ("opening debit", "opening balance debit", "opening dr"),
    "opening_credit": ("opening credit", "opening balance credit", "opening cr"),
    "debit": ("debit", "dr", "debit amount", "debit movement", "transactions debit"),
    "credit": ("credit", "cr", "credit amount", "credit movement", "transactions credit"),
    "closing_balance": ("closing balance", "closing", "cl bal", "closing bal", "balance",
                        "net balance", "balance c/f", "carried forward"),
    "closing_debit": ("closing debit", "closing balance debit", "closing dr", "debit balance"),
    "closing_credit": ("closing credit", "closing balance credit", "closing cr", "credit balance"),
}

_ALL_SYNONYMS = {syn for syns in TB_HEADER_SYNONYMS.values() for syn in syns}

_TOTAL_RE = re.compile(
    r"(?ix)^\s*(?:"
    r"(?:grand\s+)?(?:sub[-\s]?)?total\b"
    r"|.*\btotal\s*$"
    r"|c\s*/?\s*f$|b\s*/?\s*f$"
    r"|carried\s+forward|brought\s+forward"
    r"|difference\s+in\s+opening\s+balance"
    r")"
)


class RowKind(str, Enum):
    data = "data"
    blank = "blank"
    total = "total"
    section = "section"
    repeated_header = "repeated_header"


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _looks_numeric(cell: Any) -> bool:
    if cell is None or str(cell).strip() == "":
        return False
    if isinstance(cell, bool):
        return False
    if isinstance(cell, (int, float, Decimal)):
        return True
    try:
        parsed = parse_amount(cell)
    except AmountParseError:
        return False
    return not parsed.was_blank


def detect_header_row(rows: Sequence[Sequence[Any]], max_scan: int = 25) -> int:
    """Pick the real header row, skipping title/period banner rows.

    Scored so that synonym hits pull a row up and numeric cells push it down --
    a banner row ("XYZ Pvt Ltd", "Trial Balance as at 31-03-2025") has few cells
    and no synonyms, while a data row is mostly numbers.
    """
    best_idx, best_score = 0, None
    for i, row in enumerate(rows[:max_scan]):
        text_cells = sum(1 for c in row if str(c or "").strip() and not _looks_numeric(c))
        synonyms = sum(1 for c in row if _norm(c) in _ALL_SYNONYMS)
        numerics = sum(1 for c in row if _looks_numeric(c))
        score = text_cells + 3 * synonyms - 5 * numerics
        if best_score is None or score > best_score:
            best_idx, best_score = i, score
    if best_score is None or best_score <= 0:
        return 0
    return best_idx


def build_headers(
    rows: Sequence[Sequence[Any]], header_row: int
) -> tuple[list[str], int]:
    """Return (headers, first_data_row_index).

    Handles the two things that break a naive `headers.index(name)`: merged header
    cells (openpyxl read_only yields None for the non-anchor cells of a merged
    range, so forward-fill), and two-row headers ("Closing Balance" over
    "Debit"/"Credit", joined into "Closing Balance Debit"). Duplicate labels are
    de-duplicated with a " (2)" suffix so a lookup by name is unambiguous rather
    than silently resolving to the first match.
    """
    if not rows:
        return [], 0
    header_row = max(0, min(header_row, len(rows) - 1))
    primary = list(rows[header_row])

    # forward-fill merged cells
    filled: list[str] = []
    last = ""
    for cell in primary:
        text = str(cell or "").strip()
        if text:
            last = text
        filled.append(text or last)

    first_data = header_row + 1
    # two-row header? next row must be texty and non-numeric
    if first_data < len(rows):
        nxt = list(rows[first_data])
        non_empty = [c for c in nxt if str(c or "").strip()]
        if non_empty and not any(_looks_numeric(c) for c in nxt):
            child_hits = sum(1 for c in nxt if _norm(c) in _ALL_SYNONYMS)
            parent_hits = sum(1 for c in primary if _norm(c) in _ALL_SYNONYMS)
            if child_hits and child_hits >= parent_hits:
                merged: list[str] = []
                for i in range(max(len(filled), len(nxt))):
                    parent = filled[i] if i < len(filled) else ""
                    child = str(nxt[i] or "").strip() if i < len(nxt) else ""
                    merged.append(f"{parent} {child}".strip() if child else parent)
                filled = merged
                first_data = header_row + 2

    # de-duplicate
    seen: dict[str, int] = {}
    headers: list[str] = []
    for h in filled:
        key = h.lower()
        if key in seen:
            seen[key] += 1
            headers.append(f"{h} ({seen[key]})")
        else:
            seen[key] = 1
            headers.append(h)
    return headers, first_data


def suggest_column_map(headers: Sequence[str]) -> dict[str, str]:
    """Best-effort field -> header guess, so the UI and server agree on one synonym list."""
    lowered = {_norm(h): h for h in headers if str(h).strip()}
    out: dict[str, str] = {}
    taken: set[str] = set()
    # Longest synonyms first so "closing balance debit" wins over "debit".
    for field_name, syns in TB_HEADER_SYNONYMS.items():
        for syn in sorted(syns, key=len, reverse=True):
            hit = lowered.get(syn)
            if hit and hit not in taken:
                out[field_name] = hit
                taken.add(hit)
                break
    # Never suggest both a single column and its Dr/Cr pair for the same concept.
    for single, pair in (("closing_balance", ("closing_debit", "closing_credit")),
                        ("opening_balance", ("opening_debit", "opening_credit"))):
        if all(p in out for p in pair):
            out.pop(single, None)
    return out


def classify_row(
    row: Sequence[Any],
    idx: Mapping[str, int],
    headers: Sequence[str],
) -> RowKind:
    """Classify a source row so junk is *dropped with a reason*, not counted as an error."""
    if not any(str(c or "").strip() for c in row):
        return RowKind.blank

    def cell(field_name: str) -> Any:
        i = idx.get(field_name)
        if i is None or i >= len(row):
            return None
        return row[i]

    # Page-break header repeats from PDF -> XLSX exports.
    non_empty = [(_norm(c)) for c in row if str(c or "").strip()]
    header_set = {_norm(h) for h in headers if str(h).strip()}
    if non_empty and header_set and all(c in header_set for c in non_empty):
        return RowKind.repeated_header

    name = str(cell("ledger_name") or "").strip()
    numeric_fields = [f for f in NUMERIC_MAP_FIELDS if f in idx]
    has_numbers = any(str(cell(f) or "").strip() for f in numeric_fields)

    if name and _TOTAL_RE.match(name):
        return RowKind.total
    if not name and has_numbers:
        # The unlabelled total line at the bottom of most exports.
        return RowKind.total
    if name and not has_numbers:
        return RowKind.section
    if not name:
        return RowKind.blank
    return RowKind.data


# ---------------------------------------------------------------------------
# Whole-file validation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RowFigures:
    """A normalized row as the validator sees it (decoupled from ORM/dicts)."""
    row: int
    ledger_name: str
    amounts: NormalizedAmounts


@dataclass(frozen=True)
class TBValidation:
    row_count: int
    sum_net_debit: Decimal
    balanced: bool
    total_debit_movement: Decimal
    total_credit_movement: Decimal
    movement_balanced: bool
    sum_opening_net_debit: Decimal
    opening_balanced: bool
    sign_unresolved_count: int
    inconsistent_rows: list[dict] = field(default_factory=list)
    derived_fields: list[str] = field(default_factory=list)

    @property
    def inconsistent_count(self) -> int:
        return len(self.inconsistent_rows)


def validate_rows(rows: Sequence[RowFigures]) -> TBValidation:
    """Cross-check the file as a whole. NEVER blocking: findings are data."""
    sum_nd = sum((r.amounts.closing_net_debit for r in rows), Decimal(0))
    sum_op = sum((r.amounts.opening_net_debit for r in rows), Decimal(0))
    sum_dr = sum((r.amounts.debit for r in rows), Decimal(0))
    sum_cr = sum((r.amounts.credit for r in rows), Decimal(0))
    inconsistent = [
        {
            "row": r.row,
            "ledger_name": r.ledger_name,
            "expected": float(q2(r.amounts.opening_net_debit + r.amounts.debit - r.amounts.credit)),
            "found": float(r.amounts.closing_net_debit),
        }
        for r in rows
        if r.amounts.row_consistent is False
    ]
    derived: list[str] = []
    for r in rows:
        for d in r.amounts.derived:
            if d not in derived:
                derived.append(d)
    return TBValidation(
        row_count=len(rows),
        sum_net_debit=q2(sum_nd),
        balanced=is_zero(sum_nd),
        total_debit_movement=q2(sum_dr),
        total_credit_movement=q2(sum_cr),
        movement_balanced=is_zero(sum_dr - sum_cr),
        sum_opening_net_debit=q2(sum_op),
        opening_balanced=is_zero(sum_op),
        sign_unresolved_count=sum(1 for r in rows if r.amounts.sign_unresolved),
        inconsistent_rows=inconsistent,
        derived_fields=derived,
    )


# ---------------------------------------------------------------------------
# Figures + totals: the ONE shared summarizer
# ---------------------------------------------------------------------------

TOP_GROUP_ORDER = ("Assets", "Liabilities", "Income", "Expenditure")
UNMAPPED_KEY = "Unmapped"

SYNTHETIC_PROFIT_PATH = ["Liabilities", "Reserves & Surplus"]


@dataclass(frozen=True)
class LedgerFigure:
    ledger_id: uuid.UUID | None
    ledger_name: str
    ledger_code: str | None
    top_group: str | None
    group_path: list[str] | None
    nature: BalanceNature | None
    opening_net_debit: Decimal
    net_debit: Decimal
    adjustment: Decimal
    final_net_debit: Decimal
    presented_closing: Decimal
    presented_final: Decimal
    # As-imported movement magnitudes, carried through for the Dr/Cr movement
    # cross-check only. Never used to compute a statement figure.
    debit_movement: Decimal = Decimal(0)
    credit_movement: Decimal = Decimal(0)
    sign_unresolved: bool = False
    is_synthetic: bool = False

    @property
    def counts_in_statements(self) -> bool:
        """Only a ledger whose nature resolved can be placed on a statement."""
        return self.nature is not None


@dataclass(frozen=True)
class GroupSubtotal:
    key: str
    nature: BalanceNature | None
    opening_net_debit: Decimal
    presented_opening: Decimal
    debit_movement: Decimal
    credit_movement: Decimal
    closing_net_debit: Decimal
    presented_closing: Decimal
    adjustment_net_debit: Decimal
    presented_adjustment: Decimal
    final_net_debit: Decimal
    presented_final: Decimal
    # Transitional aliases for the original subtotal response contract.
    net_debit: Decimal
    presented: Decimal
    ledger_count: int


@dataclass
class GroupNode:
    """A hierarchical tree node for multi-level ledger reporting."""
    group_id: uuid.UUID | None
    group_name: str
    nature: BalanceNature | None
    code: str | None
    display_order: int
    parent_id: uuid.UUID | None
    depth: int
    direct_figures: list[LedgerFigure]
    children: list["GroupNode"]
    subtotal: GroupSubtotal  # rolled-up sum of self + all descendants


@dataclass(frozen=True)
class TBSummary:
    groups: list[GroupSubtotal]
    assets: Decimal
    liabilities: Decimal
    income: Decimal
    expenditure: Decimal
    equity: Decimal
    net_profit: Decimal
    liabilities_plus_equity: Decimal
    difference: Decimal
    difference_including_unmapped: Decimal
    balanced: bool
    unmapped_net_debit: Decimal
    unmapped_count: int
    unresolved_nature_count: int
    sign_unresolved_count: int
    ledger_count: int
    mapped_count: int
    statement_ready: bool
    total_debit_movement: Decimal
    total_credit_movement: Decimal


# Sub-groups of Liabilities that are presented as shareholders' funds. Kept as a
# render-time grouping so no existing mapped_group_id has to be re-pointed at a
# new top-level Equity head (the balance identity A = L + E + P/L holds either way).
EQUITY_SUBGROUPS = {"share capital", "reserves & surplus", "reserves and surplus",
                    "money received against share warrants",
                    "share application money pending allotment"}


def build_figures(
    accounts: Iterable[Any],
    path_map: Mapping[uuid.UUID, list[str]],
    nature_map: Mapping[uuid.UUID, BalanceNature | None],
    adjustments: Mapping[uuid.UUID, Any] | None = None,
) -> list[LedgerFigure]:
    """Project TB accounts into canonical, pre-rounded figures.

    Duck-typed on the account object so this stays testable without the ORM.
    Every value is quantized here, before `summarize` adds anything -- that is
    what makes a section subtotal equal the sum of its displayed lines.
    """
    adj_map = adjustments or {}
    figures: list[LedgerFigure] = []
    for acc in accounts:
        gid = getattr(acc, "mapped_group_id", None)
        path = list(path_map.get(gid) or []) if gid else None
        nature = nature_map.get(gid) if gid else None
        top = path[0] if path else None
        nd = q2(getattr(acc, "closing_net_debit", 0) or 0)
        adj = q2(adj_map.get(getattr(acc, "id", None), 0) or 0)
        final = nd + adj
        figures.append(LedgerFigure(
            ledger_id=getattr(acc, "id", None),
            ledger_name=getattr(acc, "ledger_name", ""),
            ledger_code=getattr(acc, "ledger_code", None),
            top_group=top,
            group_path=path or None,
            nature=nature,
            opening_net_debit=q2(getattr(acc, "opening_net_debit", 0) or 0),
            net_debit=nd,
            adjustment=adj,
            final_net_debit=final,
            presented_closing=present(nd, nature),
            presented_final=present(final, nature),
            debit_movement=q2(getattr(acc, "debit", 0) or 0),
            credit_movement=q2(getattr(acc, "credit", 0) or 0),
            sign_unresolved=bool(getattr(acc, "sign_unresolved", False)),
        ))
    return figures


def make_profit_figure(net_profit: Any) -> LedgerFigure:
    """The Balance Sheet's balancing figure, as a real renderable line.

    Without this the Liabilities section total is just `liabilities` while the
    footer shows `liabilities + net_profit`, so the rendered Balance Sheet visibly
    does not balance. Excluded from `difference` -- it *is* the balancing figure,
    not a ledger.
    """
    np_ = q2(net_profit)
    label = "Profit for the period" if np_ >= 0 else "Loss for the period"
    return LedgerFigure(
        ledger_id=None,
        ledger_name=f"{label} (transferred to Reserves & Surplus)",
        ledger_code=None,
        top_group="Liabilities",
        group_path=list(SYNTHETIC_PROFIT_PATH),
        nature=BalanceNature.credit,
        opening_net_debit=Decimal(0),
        net_debit=Decimal(0),
        adjustment=Decimal(0),
        final_net_debit=-np_,
        presented_closing=Decimal(0),
        presented_final=np_,
        is_synthetic=True,
    )


def summarize(figures: Iterable[LedgerFigure]) -> TBSummary:
    """Aggregate figures into statement totals. Pure addition, no abs()."""
    figs = [f for f in figures if not f.is_synthetic]

    by_key: dict[str, list[LedgerFigure]] = {}
    for f in figs:
        by_key.setdefault(f.top_group if f.counts_in_statements else UNMAPPED_KEY, []).append(f)

    def presented_sum(key: str) -> Decimal:
        return sum((f.presented_final for f in by_key.get(key, [])), Decimal(0))

    assets = presented_sum("Assets")
    liabilities = presented_sum("Liabilities")
    income = presented_sum("Income")
    expenditure = presented_sum("Expenditure")
    net_profit = income - expenditure
    liab_plus_equity = liabilities + net_profit

    equity = sum(
        (f.presented_final for f in by_key.get("Liabilities", [])
         if f.group_path and len(f.group_path) > 1 and _norm(f.group_path[1]) in EQUITY_SUBGROUPS),
        Decimal(0),
    ) + net_profit

    statement_figs = [f for f in figs if f.counts_in_statements]
    difference = sum((f.final_net_debit for f in statement_figs), Decimal(0))
    difference_all = sum((f.final_net_debit for f in figs), Decimal(0))
    unmapped = [f for f in figs if not f.counts_in_statements]

    groups: list[GroupSubtotal] = []
    for key in (*TOP_GROUP_ORDER, UNMAPPED_KEY):
        members = by_key.get(key)
        if not members:
            continue
        nature = members[0].nature if key != UNMAPPED_KEY else None
        groups.append(GroupSubtotal(
            key=key,
            nature=nature,
            opening_net_debit=sum((f.opening_net_debit for f in members), Decimal(0)),
            presented_opening=sum((present(f.opening_net_debit, f.nature) for f in members), Decimal(0)),
            debit_movement=sum((f.debit_movement for f in members), Decimal(0)),
            credit_movement=sum((f.credit_movement for f in members), Decimal(0)),
            closing_net_debit=sum((f.net_debit for f in members), Decimal(0)),
            presented_closing=sum((f.presented_closing for f in members), Decimal(0)),
            adjustment_net_debit=sum((f.adjustment for f in members), Decimal(0)),
            presented_adjustment=sum((present(f.adjustment, f.nature) for f in members), Decimal(0)),
            final_net_debit=sum((f.final_net_debit for f in members), Decimal(0)),
            presented_final=sum((f.presented_final for f in members), Decimal(0)),
            net_debit=sum((f.final_net_debit for f in members), Decimal(0)),
            presented=sum((f.presented_final for f in members), Decimal(0)),
            ledger_count=len(members),
        ))

    unmapped_count = sum(1 for f in figs if f.top_group is None)
    unresolved_nature_count = sum(
        1 for f in figs if f.top_group is not None and f.nature is None
    )
    sign_unresolved_count = sum(1 for f in figs if f.sign_unresolved)
    mapped_count = sum(1 for f in figs if f.top_group is not None)

    return TBSummary(
        groups=groups,
        assets=assets,
        liabilities=liabilities,
        income=income,
        expenditure=expenditure,
        equity=equity,
        net_profit=net_profit,
        liabilities_plus_equity=liab_plus_equity,
        difference=difference,
        difference_including_unmapped=difference_all,
        balanced=is_zero(difference),
        unmapped_net_debit=sum((f.final_net_debit for f in unmapped), Decimal(0)),
        unmapped_count=unmapped_count,
        unresolved_nature_count=unresolved_nature_count,
        sign_unresolved_count=sign_unresolved_count,
        ledger_count=len(figs),
        mapped_count=mapped_count,
        statement_ready=bool(figs) and unmapped_count == 0
        and unresolved_nature_count == 0 and sign_unresolved_count == 0,
        total_debit_movement=sum((f.debit_movement for f in figs), Decimal(0)),
        total_credit_movement=sum((f.credit_movement for f in figs), Decimal(0)),
    )


class _TreeNodeBuilder:
    def __init__(
        self,
        name: str,
        depth: int,
        nature: BalanceNature | None,
        group_id: uuid.UUID | None = None,
        parent_id: uuid.UUID | None = None,
        display_order: int = 0,
    ):
        self.name = name
        self.depth = depth
        self.nature = nature
        self.group_id = group_id
        self.parent_id = parent_id
        self.display_order = display_order
        self.direct_figures: list[LedgerFigure] = []
        self.children: dict[str, _TreeNodeBuilder] = {}

    def to_group_node(self) -> GroupNode:
        child_nodes = [c.to_group_node() for c in self.children.values()]
        child_nodes.sort(key=lambda x: (x.display_order, x.group_name))

        op_nd = sum((f.opening_net_debit for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.opening_net_debit for c in child_nodes), Decimal(0))
        deb_mov = sum((f.debit_movement for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.debit_movement for c in child_nodes), Decimal(0))
        cred_mov = sum((f.credit_movement for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.credit_movement for c in child_nodes), Decimal(0))
        cl_nd = sum((f.net_debit for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.closing_net_debit for c in child_nodes), Decimal(0))
        adj_nd = sum((f.adjustment for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.adjustment_net_debit for c in child_nodes), Decimal(0))
        fin_nd = sum((f.final_net_debit for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.final_net_debit for c in child_nodes), Decimal(0))
        cnt = len(self.direct_figures) + sum((c.subtotal.ledger_count for c in child_nodes), 0)

        effective_nature = self.nature
        if effective_nature is None and child_nodes:
            child_natures = {c.nature for c in child_nodes if c.nature is not None}
            if len(child_natures) == 1:
                effective_nature = next(iter(child_natures))

        subtot = GroupSubtotal(
            key=self.name,
            nature=effective_nature,
            opening_net_debit=op_nd,
            presented_opening=sum((present(f.opening_net_debit, f.nature or effective_nature) for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.presented_opening for c in child_nodes), Decimal(0)),
            debit_movement=deb_mov,
            credit_movement=cred_mov,
            closing_net_debit=cl_nd,
            presented_closing=sum((f.presented_closing for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.presented_closing for c in child_nodes), Decimal(0)),
            adjustment_net_debit=adj_nd,
            presented_adjustment=sum((present(f.adjustment, f.nature or effective_nature) for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.presented_adjustment for c in child_nodes), Decimal(0)),
            final_net_debit=fin_nd,
            presented_final=sum((f.presented_final for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.presented_final for c in child_nodes), Decimal(0)),
            net_debit=fin_nd,
            presented=sum((f.presented_final for f in self.direct_figures), Decimal(0)) + sum((c.subtotal.presented_final for c in child_nodes), Decimal(0)),
            ledger_count=cnt,
        )

        return GroupNode(
            group_id=self.group_id,
            group_name=self.name,
            nature=effective_nature,
            code=None,
            display_order=self.display_order,
            parent_id=self.parent_id,
            depth=self.depth,
            direct_figures=list(self.direct_figures),
            children=child_nodes,
            subtotal=subtot,
        )


def build_group_tree(figures: Iterable[LedgerFigure]) -> list[GroupNode]:
    """Build a hierarchical tree of GroupNodes with rolled up subtotals at every level."""
    from app.services.ledger_groups import SCHEDULE_III_SEED, TOP_GROUP_NATURES

    root_builders: dict[str, _TreeNodeBuilder] = {}

    for fig in figures:
        path = fig.group_path
        if not path:
            root_name = UNMAPPED_KEY
            if root_name not in root_builders:
                root_builders[root_name] = _TreeNodeBuilder(
                    name=root_name,
                    depth=0,
                    nature=None,
                    display_order=999,
                )
            root_builders[root_name].direct_figures.append(fig)
            continue

        # Navigate / build path
        top_name = path[0]
        if top_name not in root_builders:
            top_order = TOP_GROUP_ORDER.index(top_name) if top_name in TOP_GROUP_ORDER else 100
            root_builders[top_name] = _TreeNodeBuilder(
                name=top_name,
                depth=0,
                nature=TOP_GROUP_NATURES.get(top_name, fig.nature),
                display_order=top_order,
            )

        curr = root_builders[top_name]
        for depth_idx, seg in enumerate(path[1:], start=1):
            if seg not in curr.children:
                sub_order = 100
                if top_name in SCHEDULE_III_SEED and seg in SCHEDULE_III_SEED[top_name]:
                    sub_order = SCHEDULE_III_SEED[top_name].index(seg)
                curr.children[seg] = _TreeNodeBuilder(
                    name=seg,
                    depth=depth_idx,
                    nature=curr.nature,
                    display_order=sub_order,
                )
            curr = curr.children[seg]

        curr.direct_figures.append(fig)

    root_nodes = [b.to_group_node() for b in root_builders.values()]
    root_nodes.sort(key=lambda x: (x.display_order, x.group_name))
    return root_nodes

