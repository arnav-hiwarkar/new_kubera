"""Unit tests for hierarchical group tree subtotal computation."""
from decimal import Decimal
import pytest

from app.models.auditease import BalanceNature
from app.services.trial_balance import (
    GroupNode,
    LedgerFigure,
    build_group_tree,
)


def _make_figure(
    name: str,
    path: list[str] | None,
    nature: BalanceNature | None,
    net_debit: Decimal,
    adjustment: Decimal = Decimal(0),
    opening_net_debit: Decimal = Decimal(0),
) -> LedgerFigure:
    final = net_debit + adjustment
    return LedgerFigure(
        ledger_id=None,
        ledger_name=name,
        ledger_code=None,
        top_group=path[0] if path else None,
        group_path=path,
        nature=nature,
        opening_net_debit=opening_net_debit,
        net_debit=net_debit,
        adjustment=adjustment,
        final_net_debit=final,
        presented_closing=net_debit if nature == BalanceNature.debit else -net_debit,
        presented_final=final if nature == BalanceNature.debit else -final,
    )


def test_three_level_tree_rollup():
    # Assets -> Current Assets -> Bank Accounts -> HDFC Bank (500)
    # Assets -> Current Assets -> Cash on Hand -> Petty Cash (100)
    f1 = _make_figure("HDFC Bank", ["Assets", "Current Assets", "Bank Accounts"], BalanceNature.debit, Decimal("500.00"))
    f2 = _make_figure("Petty Cash", ["Assets", "Current Assets", "Cash on Hand"], BalanceNature.debit, Decimal("100.00"))

    tree = build_group_tree([f1, f2])
    assert len(tree) == 1
    root = tree[0]
    assert root.group_name == "Assets"
    assert root.subtotal.final_net_debit == Decimal("600.00")
    assert root.subtotal.presented_final == Decimal("600.00")
    assert len(root.children) == 1

    current_assets = root.children[0]
    assert current_assets.group_name == "Current Assets"
    assert current_assets.subtotal.final_net_debit == Decimal("600.00")
    assert len(current_assets.children) == 2

    # Check leaves
    bank_acc = next(c for c in current_assets.children if c.group_name == "Bank Accounts")
    cash_hand = next(c for c in current_assets.children if c.group_name == "Cash on Hand")
    assert bank_acc.subtotal.final_net_debit == Decimal("500.00")
    assert cash_hand.subtotal.final_net_debit == Decimal("100.00")


def test_unclassified_figures():
    f_unmapped = _make_figure("Suspense Account", None, None, Decimal("250.00"))
    f_asset = _make_figure("Plant Machinery", ["Assets", "Property, Plant and Equipment"], BalanceNature.debit, Decimal("1000.00"))

    tree = build_group_tree([f_unmapped, f_asset])
    names = [node.group_name for node in tree]
    assert "Assets" in names
    assert "Unmapped" in names or "Unclassified" in names

    unmapped_node = next(node for node in tree if node.group_name in ("Unmapped", "Unclassified"))
    assert unmapped_node.subtotal.final_net_debit == Decimal("250.00")
    assert len(unmapped_node.direct_figures) == 1


def test_negative_canonical_balance_rolls_up_correctly():
    # Bank Overdraft (credit balance under Assets -> Cash and Cash Equivalents)
    # Net debit = -500.00. Presented debit = -500.00
    f_od = _make_figure("Bank Overdraft", ["Assets", "Cash and Cash Equivalents"], BalanceNature.debit, Decimal("-500.00"))
    f_cash = _make_figure("Cash in Vault", ["Assets", "Cash and Cash Equivalents"], BalanceNature.debit, Decimal("200.00"))

    tree = build_group_tree([f_od, f_cash])
    root = tree[0]
    assert root.subtotal.final_net_debit == Decimal("-300.00")
    assert root.subtotal.presented_final == Decimal("-300.00")


def test_root_sum_invariant():
    figures = [
        _make_figure("Sales", ["Income", "Revenue from Operations"], BalanceNature.credit, Decimal("-10000.00")),
        _make_figure("Interest Income", ["Income", "Other Income"], BalanceNature.credit, Decimal("-500.00")),
        _make_figure("Rent Expense", ["Expenditure", "Other Expenses"], BalanceNature.debit, Decimal("2000.00")),
        _make_figure("Trade Receivables", ["Assets", "Trade Receivables"], BalanceNature.debit, Decimal("4000.00")),
        _make_figure("Trade Payables", ["Liabilities", "Trade Payables"], BalanceNature.credit, Decimal("-3000.00")),
        _make_figure("Suspense", None, None, Decimal("100.00")),
    ]

    tree = build_group_tree(figures)
    total_tree_final = sum(node.subtotal.final_net_debit for node in tree)
    total_figures_final = sum(f.final_net_debit for f in figures)

    assert total_tree_final == total_figures_final
