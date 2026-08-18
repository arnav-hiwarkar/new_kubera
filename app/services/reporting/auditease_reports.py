"""AuditEase report document builders.

Produces neutral ReportDocument instances for statutory reporting:
1. Balance Sheet (Schedule III format)
2. Statement of Profit and Loss (Schedule III format)
3. Notes to Accounts (detailed breakdown of financial statement heads)
4. Trial Balance Detailed (ledger-wise listing with Dr/Cr movements)
5. Trial Balance Summary (group-level rolled-up TB)
6. Extended Trial Balance (10-column worksheet: Unadjusted, Adjustments, Adjusted, P&L, BS)
7. Adjusting Entries Register
8. Ledger Mapping & Verification Audit
9. Exceptions & Audit Diagnostics
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Sequence

from app.models.auditease import BalanceNature, EntryLineSide
from app.services.reporting.document import (
    ColumnKind,
    ColumnSpec,
    ReportDocument,
    ReportRow,
    ReportSection,
    ReportTotal,
)
from app.services.reporting.format import scale_for_units
from app.services.trial_balance import (
    EQUITY_SUBGROUPS,
    GroupNode,
    GroupSubtotal,
    LedgerFigure,
    TBSummary,
    build_group_tree,
    make_profit_figure,
    present,
)


def _get_group_node_amount(tree: list[GroupNode], top_group_name: str, sub_group_name: str | None = None) -> Decimal:
    """Find the presented final amount for a given group/sub-group in the group tree."""
    for root in tree:
        if root.group_name.lower() == top_group_name.lower():
            if sub_group_name is None:
                return root.subtotal.presented_final
            for child in root.children:
                if child.group_name.lower() == sub_group_name.lower():
                    return child.subtotal.presented_final
    return Decimal("0.00")


def build_balance_sheet(
    figures: Sequence[LedgerFigure],
    summary: TBSummary,
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> ReportDocument:
    """Build Schedule III Division I Balance Sheet."""
    # Ensure balancing figure is included
    all_figs = [*figures, make_profit_figure(summary.net_profit)]
    tree = build_group_tree(all_figs)

    cols = (
        ColumnSpec(header="Particulars", key="particulars", kind=ColumnKind.text, width=42),
        ColumnSpec(header="Note", key="note_ref", kind=ColumnKind.text, width=8, align="center"),
        ColumnSpec(header="Figures as at end of current period", key="amount", kind=ColumnKind.money, width=24),
    )

    # -------------------------------------------------------------
    # Section I: EQUITY AND LIABILITIES
    # -------------------------------------------------------------
    # 1. Shareholders' Funds
    # Find Share Capital & Reserves & Surplus under Liabilities tree
    share_cap_amt = Decimal("0.00")
    reserves_amt = Decimal("0.00")
    warrants_amt = Decimal("0.00")
    app_money_amt = Decimal("0.00")

    for root in tree:
        if root.group_name == "Liabilities":
            for child in root.children:
                c_name = child.group_name.lower()
                if c_name == "share capital":
                    share_cap_amt = child.subtotal.presented_final
                elif c_name in ("reserves & surplus", "reserves and surplus"):
                    reserves_amt = child.subtotal.presented_final
                elif "warrants" in c_name:
                    warrants_amt = child.subtotal.presented_final
                elif "share application" in c_name:
                    app_money_amt = child.subtotal.presented_final

    sec_shareholders_funds = ReportSection(
        title="1. Shareholders' Funds",
        columns=cols,
        rows=(
            ReportRow(cells={"particulars": "Share Capital", "note_ref": "1", "amount": share_cap_amt}, indent=1),
            ReportRow(cells={"particulars": "Reserves & Surplus", "note_ref": "2", "amount": reserves_amt}, indent=1),
            ReportRow(cells={"particulars": "Money received against share warrants", "note_ref": "", "amount": warrants_amt}, indent=1),
        ),
        total=ReportTotal(
            label="Total Shareholders' Funds",
            cells={"amount": share_cap_amt + reserves_amt + warrants_amt},
            level=2,
        ),
    )

    sec_share_app = ReportSection(
        title="2. Share application money pending allotment",
        columns=cols,
        rows=(
            ReportRow(cells={"particulars": "Share application money pending allotment", "note_ref": "", "amount": app_money_amt}, indent=1),
        ),
    )

    # 3. Non-Current Liabilities
    lt_borrowings = _get_group_node_amount(tree, "Liabilities", "Long-term Borrowings")
    dtl = _get_group_node_amount(tree, "Liabilities", "Deferred Tax Liabilities (Net)")
    other_lt_liab = _get_group_node_amount(tree, "Liabilities", "Other Long-term Liabilities")
    lt_provisions = _get_group_node_amount(tree, "Liabilities", "Long-term Provisions")
    total_non_curr_liab = lt_borrowings + dtl + other_lt_liab + lt_provisions

    sec_non_curr_liab = ReportSection(
        title="3. Non-Current Liabilities",
        columns=cols,
        rows=(
            ReportRow(cells={"particulars": "Long-term borrowings", "note_ref": "3", "amount": lt_borrowings}, indent=1),
            ReportRow(cells={"particulars": "Deferred tax liabilities (Net)", "note_ref": "", "amount": dtl}, indent=1),
            ReportRow(cells={"particulars": "Other Long-term liabilities", "note_ref": "", "amount": other_lt_liab}, indent=1),
            ReportRow(cells={"particulars": "Long-term provisions", "note_ref": "", "amount": lt_provisions}, indent=1),
        ),
        total=ReportTotal(label="Total Non-Current Liabilities", cells={"amount": total_non_curr_liab}, level=2),
    )

    # 4. Current Liabilities
    st_borrowings = _get_group_node_amount(tree, "Liabilities", "Short-term Borrowings")
    trade_payables = _get_group_node_amount(tree, "Liabilities", "Trade Payables")
    other_curr_liab = _get_group_node_amount(tree, "Liabilities", "Other Current Liabilities")
    st_provisions = _get_group_node_amount(tree, "Liabilities", "Short-term Provisions")
    total_curr_liab = st_borrowings + trade_payables + other_curr_liab + st_provisions

    rows_curr_liab = [
        ReportRow(cells={"particulars": "Short-term borrowings", "note_ref": "", "amount": st_borrowings}, indent=1),
        ReportRow(cells={"particulars": "Trade payables", "note_ref": "4", "amount": trade_payables}, indent=1),
        ReportRow(cells={"particulars": "Other current liabilities", "note_ref": "", "amount": other_curr_liab}, indent=1),
        ReportRow(cells={"particulars": "Short-term provisions", "note_ref": "", "amount": st_provisions}, indent=1),
    ]
    total_liab_calc = (share_cap_amt + reserves_amt + warrants_amt) + app_money_amt + total_non_curr_liab + total_curr_liab
    diff_liab = summary.liabilities_plus_equity - total_liab_calc
    if diff_liab != Decimal("0.00"):
        rows_curr_liab.append(
            ReportRow(cells={"particulars": "Other / unallocated liabilities and equity", "note_ref": "", "amount": diff_liab}, indent=1)
        )
        total_curr_liab += diff_liab

    sec_curr_liab = ReportSection(
        title="4. Current Liabilities",
        columns=cols,
        rows=tuple(rows_curr_liab),
        total=ReportTotal(label="Total Current Liabilities", cells={"amount": total_curr_liab}, level=2),
    )

    sec_equity_and_liabilities = ReportSection(
        title="I. EQUITY AND LIABILITIES",
        columns=cols,
        children=(sec_shareholders_funds, sec_share_app, sec_non_curr_liab, sec_curr_liab),
        total=ReportTotal(label="TOTAL EQUITY AND LIABILITIES", cells={"amount": summary.liabilities_plus_equity}, level=0),
    )

    # -------------------------------------------------------------
    # Section II: ASSETS
    # -------------------------------------------------------------
    # 1. Non-Current Assets
    ppe = _get_group_node_amount(tree, "Assets", "Property, Plant and Equipment")
    cwip = _get_group_node_amount(tree, "Assets", "Capital Work-in-Progress")
    inv_prop = _get_group_node_amount(tree, "Assets", "Investment Property")
    goodwill = _get_group_node_amount(tree, "Assets", "Goodwill")
    intangibles = _get_group_node_amount(tree, "Assets", "Other Intangible Assets")
    non_curr_inv = _get_group_node_amount(tree, "Assets", "Non-current Investments")
    lt_loans = _get_group_node_amount(tree, "Assets", "Long-term Loans and Advances")
    other_nc_assets = _get_group_node_amount(tree, "Assets", "Other Non-current Assets")
    total_non_curr_assets = ppe + cwip + inv_prop + goodwill + intangibles + non_curr_inv + lt_loans + other_nc_assets

    # 2. Current Assets
    curr_inv = _get_group_node_amount(tree, "Assets", "Current Investments")
    inventories = _get_group_node_amount(tree, "Assets", "Inventories")
    trade_rec = _get_group_node_amount(tree, "Assets", "Trade Receivables")
    cash_equiv = _get_group_node_amount(tree, "Assets", "Cash and Cash Equivalents")
    st_loans = _get_group_node_amount(tree, "Assets", "Short-term Loans and Advances")
    other_curr_assets = _get_group_node_amount(tree, "Assets", "Other Current Assets")
    total_curr_assets = curr_inv + inventories + trade_rec + cash_equiv + st_loans + other_curr_assets

    rows_nc_assets = [
        ReportRow(cells={"particulars": "Property, Plant and Equipment", "note_ref": "5", "amount": ppe}, indent=1),
        ReportRow(cells={"particulars": "Capital work-in-progress", "note_ref": "", "amount": cwip}, indent=1),
        ReportRow(cells={"particulars": "Investment Property", "note_ref": "", "amount": inv_prop}, indent=1),
        ReportRow(cells={"particulars": "Goodwill / Intangible assets", "note_ref": "", "amount": goodwill + intangibles}, indent=1),
        ReportRow(cells={"particulars": "Non-current investments", "note_ref": "", "amount": non_curr_inv}, indent=1),
        ReportRow(cells={"particulars": "Long-term loans and advances", "note_ref": "", "amount": lt_loans}, indent=1),
        ReportRow(cells={"particulars": "Other non-current assets", "note_ref": "", "amount": other_nc_assets}, indent=1),
    ]

    total_assets_calc = total_non_curr_assets + total_curr_assets
    diff_assets = summary.assets - total_assets_calc
    if diff_assets != Decimal("0.00"):
        rows_nc_assets.append(
            ReportRow(cells={"particulars": "Other / unallocated assets", "note_ref": "", "amount": diff_assets}, indent=1)
        )
        total_non_curr_assets += diff_assets

    sec_non_curr_assets = ReportSection(
        title="1. Non-Current Assets",
        columns=cols,
        rows=tuple(rows_nc_assets),
        total=ReportTotal(label="Total Non-Current Assets", cells={"amount": total_non_curr_assets}, level=2),
    )

    sec_curr_assets = ReportSection(
        title="2. Current Assets",
        columns=cols,
        rows=(
            ReportRow(cells={"particulars": "Current investments", "note_ref": "", "amount": curr_inv}, indent=1),
            ReportRow(cells={"particulars": "Inventories", "note_ref": "6", "amount": inventories}, indent=1),
            ReportRow(cells={"particulars": "Trade receivables", "note_ref": "7", "amount": trade_rec}, indent=1),
            ReportRow(cells={"particulars": "Cash and cash equivalents", "note_ref": "8", "amount": cash_equiv}, indent=1),
            ReportRow(cells={"particulars": "Short-term loans and advances", "note_ref": "", "amount": st_loans}, indent=1),
            ReportRow(cells={"particulars": "Other current assets", "note_ref": "", "amount": other_curr_assets}, indent=1),
        ),
        total=ReportTotal(label="Total Current Assets", cells={"amount": total_curr_assets}, level=2),
    )

    sec_assets = ReportSection(
        title="II. ASSETS",
        columns=cols,
        children=(sec_non_curr_assets, sec_curr_assets),
        total=ReportTotal(label="TOTAL ASSETS", cells={"amount": summary.assets}, level=0),
    )

    return ReportDocument(
        title="Balance Sheet",
        subtitle="Schedule III Division I (Companies Act, 2013)",
        company_name=company_name,
        period_label=period_label,
        units=units,
        sections=(sec_equity_and_liabilities, sec_assets),
        meta={"basis": "Indian GAAP (AS)"},
        warnings=tuple(warnings),
    )


def build_profit_and_loss(
    figures: Sequence[LedgerFigure],
    summary: TBSummary,
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> ReportDocument:
    """Build Schedule III Division I Statement of Profit and Loss."""
    tree = build_group_tree(figures)

    cols = (
        ColumnSpec(header="Particulars", key="particulars", kind=ColumnKind.text, width=42),
        ColumnSpec(header="Note", key="note_ref", kind=ColumnKind.text, width=8, align="center"),
        ColumnSpec(header="Figures for current period", key="amount", kind=ColumnKind.money, width=24),
    )

    # Income
    rev_ops = _get_group_node_amount(tree, "Income", "Revenue from Operations")
    other_inc = _get_group_node_amount(tree, "Income", "Other Income")
    total_income = summary.income

    sec_income = ReportSection(
        title="INCOME",
        columns=cols,
        rows=(
            ReportRow(cells={"particulars": "I. Revenue from operations", "note_ref": "9", "amount": rev_ops}),
            ReportRow(cells={"particulars": "II. Other income", "note_ref": "10", "amount": other_inc}),
        ),
        total=ReportTotal(label="III. TOTAL REVENUE (I + II)", cells={"amount": total_income}, level=1),
    )

    # Expenses
    mat_consumed = _get_group_node_amount(tree, "Expenditure", "Cost of Materials Consumed")
    purchases = _get_group_node_amount(tree, "Expenditure", "Purchases of Stock-in-Trade")
    inventory_change = _get_group_node_amount(tree, "Expenditure", "Changes in Inventories")
    emp_benefits = _get_group_node_amount(tree, "Expenditure", "Employee Benefits Expense")
    fin_costs = _get_group_node_amount(tree, "Expenditure", "Finance Costs")
    dep_amort = _get_group_node_amount(tree, "Expenditure", "Depreciation and Amortization Expense")
    other_exp = _get_group_node_amount(tree, "Expenditure", "Other Expenses")
    total_expenses = summary.expenditure

    sec_expenses = ReportSection(
        title="IV. EXPENSES",
        columns=cols,
        rows=(
            ReportRow(cells={"particulars": "Cost of materials consumed", "note_ref": "", "amount": mat_consumed}, indent=1),
            ReportRow(cells={"particulars": "Purchases of Stock-in-Trade", "note_ref": "", "amount": purchases}, indent=1),
            ReportRow(cells={"particulars": "Changes in inventories of finished goods and WIP", "note_ref": "", "amount": inventory_change}, indent=1),
            ReportRow(cells={"particulars": "Employee benefits expense", "note_ref": "11", "amount": emp_benefits}, indent=1),
            ReportRow(cells={"particulars": "Finance costs", "note_ref": "12", "amount": fin_costs}, indent=1),
            ReportRow(cells={"particulars": "Depreciation and amortization expense", "note_ref": "13", "amount": dep_amort}, indent=1),
            ReportRow(cells={"particulars": "Other expenses", "note_ref": "14", "amount": other_exp}, indent=1),
        ),
        total=ReportTotal(label="TOTAL EXPENSES", cells={"amount": total_expenses}, level=1),
    )

    # Profit for period
    sec_profit = ReportSection(
        title="V. PROFIT / (LOSS) FOR THE PERIOD",
        columns=cols,
        total=ReportTotal(label="PROFIT / (LOSS) FOR THE PERIOD (III - IV)", cells={"amount": summary.net_profit}, level=0),
    )

    return ReportDocument(
        title="Statement of Profit and Loss",
        subtitle="Schedule III Division I (Companies Act, 2013)",
        company_name=company_name,
        period_label=period_label,
        units=units,
        sections=(sec_income, sec_expenses, sec_profit),
        meta={"basis": "Indian GAAP (AS)"},
        warnings=tuple(warnings),
    )


def build_notes_to_accounts(
    figures: Sequence[LedgerFigure],
    summary: TBSummary,
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> ReportDocument:
    """Build Notes to Financial Statements with sub-schedules of all ledger figures."""
    tree = build_group_tree(figures)

    cols = (
        ColumnSpec(header="Particulars", key="particulars", kind=ColumnKind.text, width=34),
        ColumnSpec(header="Opening Balance", key="opening", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Debit Movement", key="debit_mov", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Credit Movement", key="credit_mov", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Closing Balance", key="closing", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Adjustments", key="adj", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Final Balance", key="final", kind=ColumnKind.money, width=18),
    )

    sections: list[ReportSection] = []
    note_counter = 1

    def _process_node(node: GroupNode, prefix: str = ""):
        nonlocal note_counter
        # If node has direct figures or children, make a note section
        if node.direct_figures:
            rows = [
                ReportRow(
                    cells={
                        "particulars": f.ledger_name,
                        "opening": f.opening_net_debit if f.nature == BalanceNature.debit else -f.opening_net_debit,
                        "debit_mov": f.debit_movement,
                        "credit_mov": f.credit_movement,
                        "closing": f.presented_closing,
                        "adj": present(f.adjustment, f.nature),
                        "final": f.presented_final,
                    }
                )
                for f in node.direct_figures
            ]
            sec = ReportSection(
                title=f"Note {note_counter}: {prefix}{node.group_name}",
                columns=cols,
                rows=tuple(rows),
                total=ReportTotal(
                    label=f"Total {node.group_name}",
                    cells={
                        "opening": node.subtotal.presented_opening,
                        "debit_mov": node.subtotal.debit_movement,
                        "credit_mov": node.subtotal.credit_movement,
                        "closing": node.subtotal.presented_closing,
                        "adj": node.subtotal.presented_adjustment,
                        "final": node.subtotal.presented_final,
                    },
                    level=1,
                ),
                note_ref=str(note_counter),
            )
            sections.append(sec)
            note_counter += 1

        for child in node.children:
            _process_node(child, prefix=f"{node.group_name} — ")

    for root in tree:
        _process_node(root)

    return ReportDocument(
        title="Notes to Accounts",
        subtitle="Schedules forming part of Balance Sheet and Profit & Loss Statement",
        company_name=company_name,
        period_label=period_label,
        units=units,
        sections=tuple(sections),
        meta={"basis": "Indian GAAP (AS)"},
        warnings=tuple(warnings),
    )


def build_trial_balance_detailed(
    figures: Sequence[LedgerFigure],
    summary: TBSummary,
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> ReportDocument:
    """Build Detailed Trial Balance with full Dr/Cr movement breakdown."""
    cols = (
        ColumnSpec(header="Ledger Code", key="code", kind=ColumnKind.text, width=12),
        ColumnSpec(header="Ledger Name", key="name", kind=ColumnKind.text, width=30),
        ColumnSpec(header="Mapped Head", key="group", kind=ColumnKind.text, width=25),
        ColumnSpec(header="Nature", key="nature", kind=ColumnKind.text, width=10),
        ColumnSpec(header="Opening Balance", key="opening", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Debit Movement", key="debit_mov", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Credit Movement", key="credit_mov", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Closing Net Debit", key="closing", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Adjustments", key="adj", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Final Net Debit", key="final", kind=ColumnKind.money, width=18),
    )

    rows = [
        ReportRow(
            cells={
                "code": f.ledger_code or "—",
                "name": f.ledger_name,
                "group": " / ".join(f.group_path) if f.group_path else "Unmapped",
                "nature": f.nature.value if f.nature else "—",
                "opening": f.opening_net_debit,
                "debit_mov": f.debit_movement,
                "credit_mov": f.credit_movement,
                "closing": f.net_debit,
                "adj": f.adjustment,
                "final": f.final_net_debit,
            }
        )
        for f in figures
    ]

    total_row = ReportTotal(
        label="GRAND TOTAL",
        cells={
            "opening": sum((f.opening_net_debit for f in figures), Decimal(0)),
            "debit_mov": sum((f.debit_movement for f in figures), Decimal(0)),
            "credit_mov": sum((f.credit_movement for f in figures), Decimal(0)),
            "closing": sum((f.net_debit for f in figures), Decimal(0)),
            "adj": sum((f.adjustment for f in figures), Decimal(0)),
            "final": sum((f.final_net_debit for f in figures), Decimal(0)),
        },
        level=0,
    )

    section = ReportSection(
        title=None,
        columns=cols,
        rows=tuple(rows),
        total=total_row,
    )

    return ReportDocument(
        title="Trial Balance (Detailed)",
        subtitle="Canonical Ledger-wise Trial Balance",
        company_name=company_name,
        period_label=period_label,
        units=units,
        sections=(section,),
        warnings=tuple(warnings),
    )


def build_trial_balance_summary(
    figures: Sequence[LedgerFigure],
    summary: TBSummary,
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> ReportDocument:
    """Build Group-level Summary Trial Balance."""
    cols = (
        ColumnSpec(header="Schedule III Head", key="group", kind=ColumnKind.text, width=32),
        ColumnSpec(header="Nature", key="nature", kind=ColumnKind.text, width=10),
        ColumnSpec(header="Ledgers", key="count", kind=ColumnKind.number, width=10),
        ColumnSpec(header="Opening Balance", key="opening", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Debit Movement", key="debit_mov", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Credit Movement", key="credit_mov", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Closing Balance", key="closing", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Adjustments", key="adj", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Final Net Debit", key="final", kind=ColumnKind.money, width=18),
    )

    rows = [
        ReportRow(
            cells={
                "group": g.key,
                "nature": g.nature.value if g.nature else "—",
                "count": g.ledger_count,
                "opening": g.opening_net_debit,
                "debit_mov": g.debit_movement,
                "credit_mov": g.credit_movement,
                "closing": g.closing_net_debit,
                "adj": g.adjustment_net_debit,
                "final": g.final_net_debit,
            }
        )
        for g in summary.groups
    ]

    total_row = ReportTotal(
        label="TOTAL",
        cells={
            "count": summary.ledger_count,
            "opening": sum((g.opening_net_debit for g in summary.groups), Decimal(0)),
            "debit_mov": summary.total_debit_movement,
            "credit_mov": summary.total_credit_movement,
            "closing": sum((g.closing_net_debit for g in summary.groups), Decimal(0)),
            "adj": sum((g.adjustment_net_debit for g in summary.groups), Decimal(0)),
            "final": sum((g.final_net_debit for g in summary.groups), Decimal(0)),
        },
        level=0,
    )

    section = ReportSection(
        title=None,
        columns=cols,
        rows=tuple(rows),
        total=total_row,
    )

    return ReportDocument(
        title="Trial Balance (Summary)",
        subtitle="Group-wise Summary Schedule",
        company_name=company_name,
        period_label=period_label,
        units=units,
        sections=(section,),
        warnings=tuple(warnings),
    )


def build_extended_trial_balance(
    figures: Sequence[LedgerFigure],
    summary: TBSummary,
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> ReportDocument:
    """Build 10-column Extended Trial Balance worksheet."""
    cols = (
        ColumnSpec(header="Particulars", key="name", kind=ColumnKind.text, width=28),
        ColumnSpec(header="Unadj Dr", key="unadj_dr", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Unadj Cr", key="unadj_cr", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Adj Dr", key="adj_dr", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Adj Cr", key="adj_cr", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Adj TB Dr", key="adj_tb_dr", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Adj TB Cr", key="adj_tb_cr", kind=ColumnKind.money, width=14),
        ColumnSpec(header="P&L Dr", key="pl_dr", kind=ColumnKind.money, width=14),
        ColumnSpec(header="P&L Cr", key="pl_cr", kind=ColumnKind.money, width=14),
        ColumnSpec(header="BS Dr", key="bs_dr", kind=ColumnKind.money, width=14),
        ColumnSpec(header="BS Cr", key="bs_cr", kind=ColumnKind.money, width=14),
    )

    rows: list[ReportRow] = []
    tot_unadj_dr = Decimal(0)
    tot_unadj_cr = Decimal(0)
    tot_adj_dr = Decimal(0)
    tot_adj_cr = Decimal(0)
    tot_adj_tb_dr = Decimal(0)
    tot_adj_tb_cr = Decimal(0)
    tot_pl_dr = Decimal(0)
    tot_pl_cr = Decimal(0)
    tot_bs_dr = Decimal(0)
    tot_bs_cr = Decimal(0)

    warnings_list = list(warnings)
    unmapped_ledgers = [f for f in figures if not f.top_group]
    if unmapped_ledgers:
        warnings_list.append(
            f"{len(unmapped_ledgers)} ledger(s) are unmapped to Schedule III groups and require mapping before final statutory presentation."
        )

    for f in figures:
        # Unadjusted
        u_dr = f.net_debit if f.net_debit > 0 else Decimal(0)
        u_cr = -f.net_debit if f.net_debit < 0 else Decimal(0)

        # Adjustments
        a_dr = f.adjustment if f.adjustment > 0 else Decimal(0)
        a_cr = -f.adjustment if f.adjustment < 0 else Decimal(0)

        # Adjusted TB
        fin_dr = f.final_net_debit if f.final_net_debit > 0 else Decimal(0)
        fin_cr = -f.final_net_debit if f.final_net_debit < 0 else Decimal(0)

        # P&L or BS allocation based on top group
        pl_dr = Decimal(0)
        pl_cr = Decimal(0)
        bs_dr = Decimal(0)
        bs_cr = Decimal(0)

        top = f.top_group or ""
        if top in ("Income", "Expenditure"):
            pl_dr = fin_dr
            pl_cr = fin_cr
        else:
            bs_dr = fin_dr
            bs_cr = fin_cr

        tot_unadj_dr += u_dr
        tot_unadj_cr += u_cr
        tot_adj_dr += a_dr
        tot_adj_cr += a_cr
        tot_adj_tb_dr += fin_dr
        tot_adj_tb_cr += fin_cr
        tot_pl_dr += pl_dr
        tot_pl_cr += pl_cr
        tot_bs_dr += bs_dr
        tot_bs_cr += bs_cr

        rows.append(
            ReportRow(
                cells={
                    "name": f.ledger_name if f.top_group else f"{f.ledger_name} (Unmapped)",
                    "unadj_dr": u_dr,
                    "unadj_cr": u_cr,
                    "adj_dr": a_dr,
                    "adj_cr": a_cr,
                    "adj_tb_dr": fin_dr,
                    "adj_tb_cr": fin_cr,
                    "pl_dr": pl_dr,
                    "pl_cr": pl_cr,
                    "bs_dr": bs_dr,
                    "bs_cr": bs_cr,
                }
            )
        )

    total_row = ReportTotal(
        label="TOTAL",
        cells={
            "unadj_dr": tot_unadj_dr,
            "unadj_cr": tot_unadj_cr,
            "adj_dr": tot_adj_dr,
            "adj_cr": tot_adj_cr,
            "adj_tb_dr": tot_adj_tb_dr,
            "adj_tb_cr": tot_adj_tb_cr,
            "pl_dr": tot_pl_dr,
            "pl_cr": tot_pl_cr,
            "bs_dr": tot_bs_dr,
            "bs_cr": tot_bs_cr,
        },
        level=0,
    )

    section = ReportSection(
        title=None,
        columns=cols,
        rows=tuple(rows),
        total=total_row,
    )

    return ReportDocument(
        title="Extended Trial Balance",
        subtitle="10-Column Accounting Worksheet",
        company_name=company_name,
        period_label=period_label,
        units=units,
        sections=(section,),
        warnings=tuple(warnings_list),
        landscape=True,
    )


def build_adjusting_entries(
    entries: Sequence[Any],
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> ReportDocument:
    """Build Journal Register of adjusting entries."""
    cols = (
        ColumnSpec(header="Entry Code", key="code", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Description", key="desc", kind=ColumnKind.text, width=28),
        ColumnSpec(header="Ledger Name", key="ledger", kind=ColumnKind.text, width=26),
        ColumnSpec(header="Debit Amount", key="debit", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Credit Amount", key="credit", kind=ColumnKind.money, width=18),
    )

    rows: list[ReportRow] = []
    total_debit = Decimal(0)
    total_credit = Decimal(0)

    for e in entries:
        e_code = getattr(e, "code", "") or "ADJ"
        e_desc = getattr(e, "description", "") or ""
        lines = getattr(e, "lines", [])
        for line in lines:
            amt = Decimal(str(getattr(line, "amount", 0)))
            side = getattr(line, "side", None)
            dr = amt if side == EntryLineSide.debit else Decimal(0)
            cr = amt if side == EntryLineSide.credit else Decimal(0)
            total_debit += dr
            total_credit += cr

            rows.append(
                ReportRow(
                    cells={
                        "code": e_code,
                        "desc": e_desc,
                        "ledger": line.ledger.ledger_name,
                        "debit": dr,
                        "credit": cr,
                    }
                )
            )

    total_row = ReportTotal(
        label="TOTAL ADJUSTING ENTRIES",
        cells={"debit": total_debit, "credit": total_credit},
        level=0,
    )

    section = ReportSection(
        title=None,
        columns=cols,
        rows=tuple(rows),
        total=total_row,
    )

    return ReportDocument(
        title="Adjusting Journal Entries",
        subtitle="Audit Adjustments & Reclassifications Register",
        company_name=company_name,
        period_label=period_label,
        units=units,
        sections=(section,),
        warnings=tuple(warnings),
    )


def build_ledger_mapping(
    figures: Sequence[LedgerFigure],
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> ReportDocument:
    """Build Ledger Mapping & Chart-of-Accounts Verification Audit report."""
    cols = (
        ColumnSpec(header="Ledger Code", key="code", kind=ColumnKind.text, width=12),
        ColumnSpec(header="Ledger Name", key="name", kind=ColumnKind.text, width=30),
        ColumnSpec(header="Top Group", key="top_group", kind=ColumnKind.text, width=16),
        ColumnSpec(header="Full Classification Path", key="path", kind=ColumnKind.text, width=32),
        ColumnSpec(header="Nature", key="nature", kind=ColumnKind.text, width=10),
        ColumnSpec(header="Final Amount", key="amount", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Audit Status", key="status", kind=ColumnKind.text, width=14),
    )

    rows: list[ReportRow] = []
    for f in figures:
        status = "Mapped"
        if not f.group_path:
            status = "Unmapped"
        elif f.sign_unresolved:
            status = "Sign Flagged"

        rows.append(
            ReportRow(
                cells={
                    "code": f.ledger_code or "—",
                    "name": f.ledger_name,
                    "top_group": f.top_group or "—",
                    "path": " / ".join(f.group_path) if f.group_path else "—",
                    "nature": f.nature.value if f.nature else "—",
                    "amount": f.presented_final,
                    "status": status,
                },
                style="muted" if not f.group_path else None,
            )
        )

    section = ReportSection(
        title=None,
        columns=cols,
        rows=tuple(rows),
    )

    return ReportDocument(
        title="Ledger Mapping Register",
        subtitle="Chart-of-Accounts Mapping & Statutory Placement Audit",
        company_name=company_name,
        period_label=period_label,
        units=units,
        sections=(section,),
        warnings=tuple(warnings),
    )


def build_exceptions(
    summary: TBSummary,
    figures: Sequence[LedgerFigure],
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> ReportDocument:
    """Build Exceptions & Diagnostics report."""
    cols = (
        ColumnSpec(header="Category", key="cat", kind=ColumnKind.text, width=18),
        ColumnSpec(header="Ledger / Item", key="item", kind=ColumnKind.text, width=28),
        ColumnSpec(header="Mapped Path", key="path", kind=ColumnKind.text, width=26),
        ColumnSpec(header="Amount", key="amount", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Diagnostic Details", key="details", kind=ColumnKind.text, width=36),
    )

    rows: list[ReportRow] = []

    # 1. Unmapped Ledgers
    for f in figures:
        if not f.group_path:
            rows.append(
                ReportRow(
                    cells={
                        "cat": "Unmapped Ledger",
                        "item": f.ledger_name,
                        "path": "—",
                        "amount": f.final_net_debit,
                        "details": "Excluded from statutory statements until mapped to a Schedule III group.",
                    }
                )
            )

    # 2. Sign Flagged Ledgers
    for f in figures:
        if f.sign_unresolved:
            rows.append(
                ReportRow(
                    cells={
                        "cat": "Sign Anomaly",
                        "item": f.ledger_name,
                        "path": " / ".join(f.group_path) if f.group_path else "—",
                        "amount": f.net_debit,
                        "details": "Balance direction does not match typical head nature.",
                    }
                )
            )

    # 3. Imbalance check if any
    if not summary.balanced:
        rows.append(
            ReportRow(
                cells={
                    "cat": "TB Imbalance",
                    "item": "Total Trial Balance Difference",
                    "path": "—",
                    "amount": summary.difference,
                    "details": f"Assets do not equal Liabilities + Equity (out by {summary.difference}).",
                }
            )
        )

    section = ReportSection(
        title=None,
        columns=cols,
        rows=tuple(rows),
    )

    return ReportDocument(
        title="Audit Exceptions & Diagnostics",
        subtitle="Audit Readiness, Anomalies, and Mapping Verification",
        company_name=company_name,
        period_label=period_label,
        units=units,
        sections=(section,),
        warnings=tuple(warnings),
    )


AUDITEASE_BUILDERS: dict[str, Callable[..., ReportDocument]] = {
    "balance_sheet": build_balance_sheet,
    "profit_and_loss": build_profit_and_loss,
    "notes_to_accounts": build_notes_to_accounts,
    "trial_balance_detailed": build_trial_balance_detailed,
    "trial_balance_summary": build_trial_balance_summary,
    "extended_trial_balance": build_extended_trial_balance,
    "adjusting_entries": build_adjusting_entries,
    "ledger_mapping": build_ledger_mapping,
    "exceptions": build_exceptions,
}


def get_auditease_report_builder(report_key: str) -> Callable[..., ReportDocument]:
    """Retrieve the builder function for an AuditEase report key."""
    builder = AUDITEASE_BUILDERS.get(report_key)
    if not builder:
        raise KeyError(f"Unknown AuditEase report key '{report_key}'. Available: {list(AUDITEASE_BUILDERS)}")
    return builder


def build_all_auditease_reports(
    figures: Sequence[LedgerFigure],
    summary: TBSummary,
    approved_entries: Sequence[Any],
    company_name: str,
    period_label: str,
    units: str = "absolute",
    warnings: Sequence[str] = (),
) -> list[tuple[str, ReportDocument]]:
    """Build all standard AuditEase reports for the multi-sheet statutory pack."""
    return [
        ("Balance Sheet", build_balance_sheet(figures, summary, company_name, period_label, units, warnings)),
        ("Profit and Loss", build_profit_and_loss(figures, summary, company_name, period_label, units, warnings)),
        ("Notes to Accounts", build_notes_to_accounts(figures, summary, company_name, period_label, units, warnings)),
        ("TB Detailed", build_trial_balance_detailed(figures, summary, company_name, period_label, units, warnings)),
        ("TB Summary", build_trial_balance_summary(figures, summary, company_name, period_label, units, warnings)),
        ("Extended TB", build_extended_trial_balance(figures, summary, company_name, period_label, units, warnings)),
        ("Adjusting Entries", build_adjusting_entries(approved_entries, company_name, period_label, units, warnings)),
        ("Ledger Mapping", build_ledger_mapping(figures, company_name, period_label, units, warnings)),
        ("Exceptions", build_exceptions(summary, figures, company_name, period_label, units, warnings)),
    ]
