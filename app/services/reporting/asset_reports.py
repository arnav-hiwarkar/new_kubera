"""Asset Register and Depreciation Report Document Builders.

Produces neutral ReportDocument instances for fixed-asset reporting:
1. Fixed Asset Register (full multi-column list with category subtotals)
2. Companies Act / Schedule II Depreciation Schedule (PPE note)
3. Income Tax Act / Appendix I Block-wise Depreciation Schedule
4. Income Tax — Asset-wise Block Annexure
5. Additions Register
6. Disposals & Retirals Register
7. Capital Work-in-Progress (CWIP) & Uncapitalized Assets
8. Dimension Summary (Location / Department / Custodian)
9. Physical Verification Sheet (Printable checklist)
10. GST & ITC Summary on Asset Acquisitions
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from app.models.assets import Asset, AssetLifecycleStatus
from app.models.asset_masters import ItAssetBlock
from app.models.depreciation import (
    AssetDepreciationLine,
    DepreciationRun,
    ItBlockDepreciationLine,
)
from app.models.financial_year import FinancialYear
from app.services.reporting.document import (
    ColumnKind,
    ColumnSpec,
    ReportDocument,
    ReportRow,
    ReportSection,
    ReportTotal,
)
from app.services.reporting.format import scale_for_units


# --- Report Keys ---
REPORT_FIXED_ASSET_REGISTER = "fixed_asset_register"
REPORT_COMPANIES_ACT_DEPRECIATION = "companies_act_depreciation"
REPORT_INCOME_TAX_DEPRECIATION = "income_tax_depreciation"
REPORT_IT_ASSET_ANNEXURE = "it_asset_annexure"
REPORT_ADDITIONS_REGISTER = "additions_register"
REPORT_DISPOSALS_REGISTER = "disposals_register"
REPORT_CWIP_REGISTER = "cwip_register"
REPORT_DIMENSION_SUMMARY = "dimension_summary"
REPORT_PHYSICAL_VERIFICATION = "physical_verification"
REPORT_GST_ITC_SUMMARY = "gst_itc_summary"

ALL_ASSET_REPORTS = [
    (REPORT_FIXED_ASSET_REGISTER, "Fixed Asset Register", "Comprehensive register of all capital assets with category subtotals"),
    (REPORT_COMPANIES_ACT_DEPRECIATION, "Companies Act / Schedule II Schedule", "PPE note with Gross Block, Depreciation, and Net Block"),
    (REPORT_INCOME_TAX_DEPRECIATION, "Income Tax Section 32 Schedule", "Appendix I block-wise depreciation and STCG/STCL analysis"),
    (REPORT_IT_ASSET_ANNEXURE, "Income Tax Asset Annexure", "Asset-wise supporting detail behind each tax block"),
    (REPORT_ADDITIONS_REGISTER, "Additions Register", "Assets capitalized during the FY with supplier & cost breakdown"),
    (REPORT_DISPOSALS_REGISTER, "Disposals Register", "Assets sold, scrapped or written off during the FY with gain/loss"),
    (REPORT_CWIP_REGISTER, "CWIP / Uncapitalized Assets", "Draft and ready assets with purchase date and ageing"),
    (REPORT_DIMENSION_SUMMARY, "Dimension Summary", "Asset count, gross block and NBV by Location, Department, Custodian"),
    (REPORT_PHYSICAL_VERIFICATION, "Physical Verification Sheet", "Verification checklist formatted for audit and inventory counts"),
    (REPORT_GST_ITC_SUMMARY, "GST & ITC Summary", "Taxable value, CGST/SGST/IGST, and ITC eligibility on acquisitions"),
]


# ============================================================================
# 1. Fixed Asset Register
# ============================================================================
def build_fixed_asset_register_report(
    assets: Sequence[Asset],
    dep_lines_by_asset_id: Dict[str, AssetDepreciationLine],
    company_name: str,
    fy_label: str,
    units: str = "absolute",
    lookups_by_id: Optional[Dict[str, str]] = None,
) -> ReportDocument:
    lookups = lookups_by_id or {}
    scale = lambda v: scale_for_units(v, units)

    cols = (
        ColumnSpec(header="Asset Code", key="asset_code", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Asset Name", key="asset_name", kind=ColumnKind.text, width=28),
        ColumnSpec(header="Category", key="category", kind=ColumnKind.text, width=18),
        ColumnSpec(header="Cap. Date", key="capitalization_date", kind=ColumnKind.text, width=12),
        ColumnSpec(header="Location", key="location", kind=ColumnKind.text, width=16),
        ColumnSpec(header="Department", key="department", kind=ColumnKind.text, width=16),
        ColumnSpec(header="Original Cost", key="original_cost", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Method", key="method", kind=ColumnKind.text, width=8),
        ColumnSpec(header="Opening Acc Dep", key="opening_acc_dep", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Dep (FY)", key="dep_for_year", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Closing Acc Dep", key="closing_acc_dep", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Net Book Value", key="net_book_value", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Status", key="status", kind=ColumnKind.text, width=12),
    )

    by_category: Dict[str, List[Asset]] = {}
    for a in assets:
        cat_name = a.category.name if a.category else "Uncategorized"
        by_category.setdefault(cat_name, []).append(a)

    sub_sections: List[ReportSection] = []
    total_cost = Decimal("0.00")
    total_opening_dep = Decimal("0.00")
    total_dep = Decimal("0.00")
    total_closing_dep = Decimal("0.00")
    total_nbv = Decimal("0.00")

    for cat_name in sorted(by_category.keys()):
        cat_assets = by_category[cat_name]
        cat_rows: List[ReportRow] = []
        cat_cost = Decimal("0.00")
        cat_open_dep = Decimal("0.00")
        cat_fy_dep = Decimal("0.00")
        cat_close_dep = Decimal("0.00")
        cat_nbv = Decimal("0.00")

        for a in cat_assets:
            line = dep_lines_by_asset_id.get(str(a.id))
            cost = a.original_cost or Decimal("0.00")
            open_dep = line.opening_accumulated_depreciation if line else (a.opening_accumulated_depreciation or Decimal("0.00"))
            fy_dep = line.depreciation_for_year if line else Decimal("0.00")
            close_dep = line.closing_accumulated_depreciation if line else (open_dep + fy_dep)
            nbv = line.closing_carrying_amount if line else max(Decimal("0.00"), cost - close_dep)
            loc = lookups.get(str(a.location_id), "")
            dept = lookups.get(str(a.department_id), "")

            cat_cost += cost
            cat_open_dep += open_dep
            cat_fy_dep += fy_dep
            cat_close_dep += close_dep
            cat_nbv += nbv

            cat_rows.append(
                ReportRow(
                    cells={
                        "asset_code": a.asset_code or "",
                        "asset_name": a.asset_name,
                        "category": cat_name,
                        "capitalization_date": str(a.capitalization_date or a.available_for_use_date or ""),
                        "location": loc,
                        "department": dept,
                        "original_cost": scale(cost),
                        "method": (a.dep_method or "SLM").upper(),
                        "opening_acc_dep": scale(open_dep),
                        "dep_for_year": scale(fy_dep),
                        "closing_acc_dep": scale(close_dep),
                        "net_book_value": scale(nbv),
                        "status": (a.lifecycle_status.value if hasattr(a.lifecycle_status, "value") else str(a.lifecycle_status)).capitalize(),
                    }
                )
            )

        total_cost += cat_cost
        total_opening_dep += cat_open_dep
        total_dep += cat_fy_dep
        total_closing_dep += cat_close_dep
        total_nbv += cat_nbv

        sub_sections.append(
            ReportSection(
                title=cat_name,
                columns=cols,
                rows=tuple(cat_rows),
                total=ReportTotal(
                    label=f"Subtotal — {cat_name}",
                    cells={
                        "original_cost": scale(cat_cost),
                        "opening_acc_dep": scale(cat_open_dep),
                        "dep_for_year": scale(cat_fy_dep),
                        "closing_acc_dep": scale(cat_close_dep),
                        "net_book_value": scale(cat_nbv),
                    },
                    level=1,
                ),
            )
        )

    root_section = ReportSection(
        title=None,
        columns=cols,
        children=tuple(sub_sections),
        total=ReportTotal(
            label="Grand Total",
            cells={
                "original_cost": scale(total_cost),
                "opening_acc_dep": scale(total_opening_dep),
                "dep_for_year": scale(total_dep),
                "closing_acc_dep": scale(total_closing_dep),
                "net_book_value": scale(total_nbv),
            },
            level=0,
        ),
    )

    return ReportDocument(
        title="Fixed Asset Register",
        subtitle="Complete asset register with carrying values and category subtotals",
        company_name=company_name,
        period_label=fy_label,
        units=units,
        sections=(root_section,),
    )


# ============================================================================
# 2. Companies Act / Schedule II Depreciation Schedule (PPE Note)
# ============================================================================
def build_companies_act_schedule_ii_report(
    run: DepreciationRun,
    assets_by_id: Dict[str, Asset],
    company_name: str,
    fy_label: str,
    units: str = "absolute",
) -> ReportDocument:
    scale = lambda v: scale_for_units(v, units)

    cols = (
        ColumnSpec(header="Asset / Class Description", key="asset_desc", kind=ColumnKind.text, width=28),
        ColumnSpec(header="Opening Gross", key="opening_gross", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Additions", key="additions", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Deletions", key="disposals", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Closing Gross", key="closing_gross", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Opening Acc Dep", key="opening_dep", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Dep for FY", key="dep_for_year", kind=ColumnKind.money, width=14),
        ColumnSpec(header="On Deletions", key="disposal_dep", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Closing Acc Dep", key="closing_dep", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Closing Net (NBV)", key="closing_nbv", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Opening Net", key="opening_nbv", kind=ColumnKind.money, width=15),
    )

    by_category: Dict[str, List[AssetDepreciationLine]] = {}
    for line in run.lines:
        asset = assets_by_id.get(str(line.asset_id))
        cat_name = asset.category.name if asset and asset.category else "General Assets"
        by_category.setdefault(cat_name, []).append(line)

    sub_sections: List[ReportSection] = []
    tot = {k: Decimal("0.00") for k in ["og", "add", "disp", "cg", "od", "dep", "dd", "cd", "cnbv", "onbv"]}

    for cat_name in sorted(by_category.keys()):
        lines = by_category[cat_name]
        cat_tot = {k: Decimal("0.00") for k in tot.keys()}
        cat_rows: List[ReportRow] = []

        for l in lines:
            asset = assets_by_id.get(str(l.asset_id))
            code_prefix = f"[{asset.asset_code}] " if asset and asset.asset_code else ""
            desc = f"{code_prefix}{asset.asset_name if asset else 'Asset'}"

            cat_tot["og"] += l.opening_gross_block
            cat_tot["add"] += l.additions
            cat_tot["disp"] += l.disposals
            cat_tot["cg"] += l.closing_gross_block
            cat_tot["od"] += l.opening_accumulated_depreciation
            cat_tot["dep"] += l.depreciation_for_year
            cat_tot["dd"] += l.disposal_accumulated_depreciation
            cat_tot["cd"] += l.closing_accumulated_depreciation
            cat_tot["cnbv"] += l.closing_carrying_amount
            cat_tot["onbv"] += l.opening_carrying_amount

            cat_rows.append(
                ReportRow(
                    cells={
                        "asset_desc": desc,
                        "opening_gross": scale(l.opening_gross_block),
                        "additions": scale(l.additions),
                        "disposals": scale(l.disposals),
                        "closing_gross": scale(l.closing_gross_block),
                        "opening_dep": scale(l.opening_accumulated_depreciation),
                        "dep_for_year": scale(l.depreciation_for_year),
                        "disposal_dep": scale(l.disposal_accumulated_depreciation),
                        "closing_dep": scale(l.closing_accumulated_depreciation),
                        "closing_nbv": scale(l.closing_carrying_amount),
                        "opening_nbv": scale(l.opening_carrying_amount),
                    }
                )
            )

        for k in tot:
            tot[k] += cat_tot[k]

        sub_sections.append(
            ReportSection(
                title=cat_name,
                columns=cols,
                rows=tuple(cat_rows),
                total=ReportTotal(
                    label=f"Total {cat_name}",
                    cells={
                        "opening_gross": scale(cat_tot["og"]),
                        "additions": scale(cat_tot["add"]),
                        "disposals": scale(cat_tot["disp"]),
                        "closing_gross": scale(cat_tot["cg"]),
                        "opening_dep": scale(cat_tot["od"]),
                        "dep_for_year": scale(cat_tot["dep"]),
                        "disposal_dep": scale(cat_tot["dd"]),
                        "closing_dep": scale(cat_tot["cd"]),
                        "closing_nbv": scale(cat_tot["cnbv"]),
                        "opening_nbv": scale(cat_tot["onbv"]),
                    },
                    level=1,
                ),
            )
        )

    root_section = ReportSection(
        title=None,
        columns=cols,
        children=tuple(sub_sections),
        total=ReportTotal(
            label="Grand Total (Property, Plant & Equipment)",
            cells={
                "opening_gross": scale(tot["og"]),
                "additions": scale(tot["add"]),
                "disposals": scale(tot["disp"]),
                "closing_gross": scale(tot["cg"]),
                "opening_dep": scale(tot["od"]),
                "dep_for_year": scale(tot["dep"]),
                "disposal_dep": scale(tot["dd"]),
                "closing_dep": scale(tot["cd"]),
                "closing_nbv": scale(tot["cnbv"]),
                "opening_nbv": scale(tot["onbv"]),
            },
            level=0,
        ),
    )

    return ReportDocument(
        title="Schedule II — Depreciation & PPE Statement",
        subtitle="Companies Act 2013 statutory fixed asset and depreciation movement schedule",
        company_name=company_name,
        period_label=fy_label,
        units=units,
        sections=(root_section,),
    )


# ============================================================================
# 3. Income Tax Act / Appendix I Block Depreciation Schedule
# ============================================================================
def build_income_tax_appendix_i_report(
    run: DepreciationRun,
    company_name: str,
    fy_label: str,
    units: str = "absolute",
) -> ReportDocument:
    scale = lambda v: scale_for_units(v, units)

    cols = (
        ColumnSpec(header="Asset Block & Prescribed Rate", key="block_name", kind=ColumnKind.text, width=28),
        ColumnSpec(header="Rate %", key="rate", kind=ColumnKind.percent, width=10),
        ColumnSpec(header="Opening WDV", key="opening_wdv", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Additions >=180d", key="add_180", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Additions <180d", key="add_less_180", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Realized Sales", key="sales", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Balance Before Dep", key="balance_before_dep", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Dep @ Full Rate", key="dep_full", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Dep @ Half Rate", key="dep_half", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Total Tax Dep", key="total_dep", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Closing Tax WDV", key="closing_wdv", kind=ColumnKind.money, width=16),
        ColumnSpec(header="STCG u/s 50", key="capital_gain", kind=ColumnKind.money, width=14),
    )

    rows: List[ReportRow] = []
    tot = {
        "ow": Decimal("0.00"),
        "a180": Decimal("0.00"),
        "al180": Decimal("0.00"),
        "s": Decimal("0.00"),
        "bbd": Decimal("0.00"),
        "df": Decimal("0.00"),
        "dh": Decimal("0.00"),
        "td": Decimal("0.00"),
        "cw": Decimal("0.00"),
        "cg": Decimal("0.00"),
    }

    for l in run.it_lines:
        tot["ow"] += l.opening_wdv
        tot["a180"] += l.additions_more_than_180
        tot["al180"] += l.additions_less_than_180
        tot["s"] += l.realized_from_sales
        tot["bbd"] += l.balance_before_depreciation
        tot["df"] += l.depreciation_full_rate
        tot["dh"] += l.depreciation_half_rate
        tot["td"] += l.total_depreciation
        tot["cw"] += l.closing_wdv
        tot["cg"] += l.capital_gain_or_loss if l.has_stcg else Decimal("0.00")

        rows.append(
            ReportRow(
                cells={
                    "block_name": l.block_name,
                    "rate": l.prescribed_rate,
                    "opening_wdv": scale(l.opening_wdv),
                    "add_180": scale(l.additions_more_than_180),
                    "add_less_180": scale(l.additions_less_than_180),
                    "sales": scale(l.realized_from_sales),
                    "balance_before_dep": scale(l.balance_before_depreciation),
                    "dep_full": scale(l.depreciation_full_rate),
                    "dep_half": scale(l.depreciation_half_rate),
                    "total_dep": scale(l.total_depreciation),
                    "closing_wdv": scale(l.closing_wdv),
                    "capital_gain": scale(l.capital_gain_or_loss if l.has_stcg else Decimal("0.00")),
                }
            )
        )

    section = ReportSection(
        title="Income Tax Depreciation Schedule (Appendix I)",
        columns=cols,
        rows=tuple(rows),
        total=ReportTotal(
            label="Grand Total (All Tax Blocks)",
            cells={
                "opening_wdv": scale(tot["ow"]),
                "add_180": scale(tot["a180"]),
                "add_less_180": scale(tot["al180"]),
                "sales": scale(tot["s"]),
                "balance_before_dep": scale(tot["bbd"]),
                "dep_full": scale(tot["df"]),
                "dep_half": scale(tot["dh"]),
                "total_dep": scale(tot["td"]),
                "closing_wdv": scale(tot["cw"]),
                "capital_gain": scale(tot["cg"]),
            },
            level=0,
        ),
    )

    return ReportDocument(
        title="Income Tax Act — Section 32 Depreciation Schedule",
        subtitle="Block-wise tax depreciation, 180-day split, and Capital Gains u/s 50",
        company_name=company_name,
        period_label=fy_label,
        units=units,
        sections=(section,),
    )


# ============================================================================
# 4. Income Tax — Asset-wise Block Annexure
# ============================================================================
def build_it_asset_annexure_report(
    assets: Sequence[Asset],
    blocks_by_id: Dict[str, ItAssetBlock],
    company_name: str,
    fy_label: str,
    fy_end: date,
    units: str = "absolute",
) -> ReportDocument:
    scale = lambda v: scale_for_units(v, units)

    cols = (
        ColumnSpec(header="Tax Block", key="block_name", kind=ColumnKind.text, width=22),
        ColumnSpec(header="Asset Code", key="asset_code", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Asset Description", key="asset_name", kind=ColumnKind.text, width=26),
        ColumnSpec(header="Put to Use Date", key="put_to_use", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Days Put to Use", key="days_used", kind=ColumnKind.number, width=14),
        ColumnSpec(header="Applicable Rate", key="rate_type", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Original / Addition Cost", key="cost", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Disposal Date", key="disposal_date", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Sale Proceeds", key="proceeds", kind=ColumnKind.money, width=16),
    )

    by_block: Dict[str, List[Asset]] = {}
    for a in assets:
        block = blocks_by_id.get(str(a.it_block_id)) if a.it_block_id else None
        b_name = block.name if block else "Unassigned Tax Block"
        by_block.setdefault(b_name, []).append(a)

    sub_sections: List[ReportSection] = []
    tot_cost = Decimal("0.00")
    tot_sales = Decimal("0.00")

    for b_name in sorted(by_block.keys()):
        b_assets = by_block[b_name]
        b_rows: List[ReportRow] = []
        b_cost = Decimal("0.00")
        b_sales = Decimal("0.00")

        for a in b_assets:
            cap_date = a.it_put_to_use_date or a.capitalization_date or a.available_for_use_date
            days = (fy_end - cap_date).days + 1 if cap_date else 0
            rate_type = "Full Rate" if days >= 180 else "Half Rate"
            cost = a.original_cost or Decimal("0.00")
            proceeds = a.disposal_it_proceeds or a.sale_proceeds or Decimal("0.00")

            b_cost += cost
            b_sales += proceeds

            b_rows.append(
                ReportRow(
                    cells={
                        "block_name": b_name,
                        "asset_code": a.asset_code or "",
                        "asset_name": a.asset_name,
                        "put_to_use": str(cap_date or ""),
                        "days_used": days,
                        "rate_type": rate_type,
                        "cost": scale(cost),
                        "disposal_date": str(a.disposal_date or ""),
                        "proceeds": scale(proceeds),
                    }
                )
            )

        tot_cost += b_cost
        tot_sales += b_sales

        sub_sections.append(
            ReportSection(
                title=b_name,
                columns=cols,
                rows=tuple(b_rows),
                total=ReportTotal(
                    label=f"Subtotal — {b_name}",
                    cells={"cost": scale(b_cost), "proceeds": scale(b_sales)},
                    level=1,
                ),
            )
        )

    root_section = ReportSection(
        title=None,
        columns=cols,
        children=tuple(sub_sections),
        total=ReportTotal(
            label="Grand Total",
            cells={"cost": scale(tot_cost), "proceeds": scale(tot_sales)},
            level=0,
        ),
    )

    return ReportDocument(
        title="Income Tax — Asset-wise Block Annexure",
        subtitle="Itemized breakdown of additions, days put to use, and realization per tax block",
        company_name=company_name,
        period_label=fy_label,
        units=units,
        sections=(root_section,),
    )


# ============================================================================
# 5. Additions Register
# ============================================================================
def build_additions_register_report(
    assets: Sequence[Asset],
    company_name: str,
    fy_label: str,
    fy_start: date,
    fy_end: date,
    units: str = "absolute",
) -> ReportDocument:
    scale = lambda v: scale_for_units(v, units)

    cols = (
        ColumnSpec(header="Cap. Date", key="cap_date", kind=ColumnKind.text, width=12),
        ColumnSpec(header="Asset Code", key="asset_code", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Asset Description", key="asset_name", kind=ColumnKind.text, width=26),
        ColumnSpec(header="Category", key="category", kind=ColumnKind.text, width=18),
        ColumnSpec(header="Supplier", key="supplier", kind=ColumnKind.text, width=20),
        ColumnSpec(header="Invoice No.", key="invoice_no", kind=ColumnKind.text, width=15),
        ColumnSpec(header="Basic Price", key="basic_price", kind=ColumnKind.money, width=15),
        ColumnSpec(header="GST Capitalized", key="gst_capitalized", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Total Capitalized", key="total_cost", kind=ColumnKind.money, width=16),
    )

    additions = [
        a for a in assets
        if a.capitalization_date and fy_start <= a.capitalization_date <= fy_end
    ]

    by_category: Dict[str, List[Asset]] = {}
    for a in additions:
        cat_name = a.category.name if a.category else "General Additions"
        by_category.setdefault(cat_name, []).append(a)

    sub_sections: List[ReportSection] = []
    total_basic = Decimal("0.00")
    total_gst = Decimal("0.00")
    total_cost = Decimal("0.00")

    for cat_name in sorted(by_category.keys()):
        cat_assets = by_category[cat_name]
        cat_rows: List[ReportRow] = []
        c_basic = Decimal("0.00")
        c_gst = Decimal("0.00")
        c_cost = Decimal("0.00")

        for a in cat_assets:
            cost = a.original_cost or Decimal("0.00")
            acq = a.acquisition
            basic = (acq.unit_basic_price if acq else cost) or cost
            gst_cap = cost - basic if cost > basic else Decimal("0.00")
            supp = acq.supplier.name if acq and acq.supplier else ""
            inv = acq.invoice_number if acq else ""

            c_basic += basic
            c_gst += gst_cap
            c_cost += cost

            cat_rows.append(
                ReportRow(
                    cells={
                        "cap_date": str(a.capitalization_date or ""),
                        "asset_code": a.asset_code or "",
                        "asset_name": a.asset_name,
                        "category": cat_name,
                        "supplier": supp,
                        "invoice_no": inv,
                        "basic_price": scale(basic),
                        "gst_capitalized": scale(gst_cap),
                        "total_cost": scale(cost),
                    }
                )
            )

        total_basic += c_basic
        total_gst += c_gst
        total_cost += c_cost

        sub_sections.append(
            ReportSection(
                title=cat_name,
                columns=cols,
                rows=tuple(cat_rows),
                total=ReportTotal(
                    label=f"Subtotal — {cat_name}",
                    cells={
                        "basic_price": scale(c_basic),
                        "gst_capitalized": scale(c_gst),
                        "total_cost": scale(c_cost),
                    },
                    level=1,
                ),
            )
        )

    root_section = ReportSection(
        title=None,
        columns=cols,
        children=tuple(sub_sections),
        total=ReportTotal(
            label="Grand Total Additions",
            cells={
                "basic_price": scale(total_basic),
                "gst_capitalized": scale(total_gst),
                "total_cost": scale(total_cost),
            },
            level=0,
        ),
    )

    return ReportDocument(
        title="Fixed Assets — Additions Register",
        subtitle=f"Additions capitalized during {fy_label} with supplier and invoice particulars",
        company_name=company_name,
        period_label=fy_label,
        units=units,
        sections=(root_section,),
    )


# ============================================================================
# 6. Disposals Register
# ============================================================================
def build_disposals_register_report(
    assets: Sequence[Asset],
    dep_lines_by_asset_id: Dict[str, AssetDepreciationLine],
    company_name: str,
    fy_label: str,
    fy_start: date,
    fy_end: date,
    units: str = "absolute",
) -> ReportDocument:
    scale = lambda v: scale_for_units(v, units)

    cols = (
        ColumnSpec(header="Disposal Date", key="disp_date", kind=ColumnKind.text, width=12),
        ColumnSpec(header="Asset Code", key="asset_code", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Asset Description", key="asset_name", kind=ColumnKind.text, width=26),
        ColumnSpec(header="Disposal Type", key="disp_type", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Original Cost", key="cost", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Acc Depreciation", key="acc_dep", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Carrying Value (WDV)", key="nbv", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Sale Proceeds", key="proceeds", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Gain / (Loss) on Sale", key="gain_loss", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Buyer / Recipient", key="buyer", kind=ColumnKind.text, width=18),
        ColumnSpec(header="Disposed By", key="disposed_by", kind=ColumnKind.text, width=18),
    )

    disposed = [
        a for a in assets
        if a.disposal_date and fy_start <= a.disposal_date <= fy_end
    ]

    rows: List[ReportRow] = []
    tot_cost = Decimal("0.00")
    tot_acc_dep = Decimal("0.00")
    tot_nbv = Decimal("0.00")
    tot_proceeds = Decimal("0.00")
    tot_gain_loss = Decimal("0.00")

    for a in disposed:
        line = dep_lines_by_asset_id.get(str(a.id))
        cost = a.original_cost if a.original_cost is not None else Decimal("0.00")
        acc_dep = line.disposal_accumulated_depreciation if line else (a.opening_accumulated_depreciation if a.opening_accumulated_depreciation is not None else Decimal("0.00"))
        nbv = max(Decimal("0.00"), cost - acc_dep)
        proceeds = a.sale_proceeds if a.sale_proceeds is not None else Decimal("0.00")
        gain_loss = line.gain_loss_on_disposal if line and line.gain_loss_on_disposal is not None else (proceeds - nbv)

        tot_cost += cost
        tot_acc_dep += acc_dep
        tot_nbv += nbv
        tot_proceeds += proceeds
        tot_gain_loss += gain_loss

        disp_user_name = ""
        if getattr(a, "disposed_by_user", None):
            u = a.disposed_by_user
            disp_user_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip() or getattr(u, "email", "")
        elif getattr(a, "disposed_by", None):
            disp_user_name = str(a.disposed_by)

        rows.append(
            ReportRow(
                cells={
                    "disp_date": str(a.disposal_date),
                    "asset_code": a.asset_code or "",
                    "asset_name": a.asset_name,
                    "disp_type": (a.disposal_type or "Sale").capitalize(),
                    "cost": scale(cost),
                    "acc_dep": scale(acc_dep),
                    "nbv": scale(nbv),
                    "proceeds": scale(proceeds),
                    "gain_loss": scale(gain_loss),
                    "buyer": a.buyer_name or "",
                    "disposed_by": disp_user_name,
                }
            )
        )

    section = ReportSection(
        title="Disposals and Retirals",
        columns=cols,
        rows=tuple(rows),
        total=ReportTotal(
            label="Grand Total Disposals",
            cells={
                "cost": scale(tot_cost),
                "acc_dep": scale(tot_acc_dep),
                "nbv": scale(tot_nbv),
                "proceeds": scale(tot_proceeds),
                "gain_loss": scale(tot_gain_loss),
            },
            level=0,
        ),
    )

    return ReportDocument(
        title="Fixed Assets — Disposals & Retirals Register",
        subtitle=f"Assets sold, scrapped or written off during {fy_label} with profit/loss computation",
        company_name=company_name,
        period_label=fy_label,
        units=units,
        sections=(section,),
    )


# ============================================================================
# 7. CWIP / Uncapitalized Assets Register
# ============================================================================
def build_cwip_register_report(
    assets: Sequence[Asset],
    company_name: str,
    fy_label: str,
    units: str = "absolute",
) -> ReportDocument:
    scale = lambda v: scale_for_units(v, units)

    cols = (
        ColumnSpec(header="Asset / Project Description", key="asset_name", kind=ColumnKind.text, width=28),
        ColumnSpec(header="Category", key="category", kind=ColumnKind.text, width=18),
        ColumnSpec(header="Acquisition Date", key="purchase_date", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Supplier", key="supplier", kind=ColumnKind.text, width=20),
        ColumnSpec(header="Invoice No.", key="invoice_no", kind=ColumnKind.text, width=15),
        ColumnSpec(header="Basic / Work Value", key="amount", kind=ColumnKind.money, width=16),
        ColumnSpec(header="Lifecycle Status", key="status", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Ageing (Days)", key="ageing_days", kind=ColumnKind.number, width=14),
    )

    cwip_assets = [
        a for a in assets
        if a.lifecycle_status in [AssetLifecycleStatus.draft, AssetLifecycleStatus.ready]
    ]

    rows: List[ReportRow] = []
    tot_amt = Decimal("0.00")
    today = date.today()

    for a in cwip_assets:
        acq = a.acquisition
        cost = a.original_cost or (acq.unit_basic_price if acq else Decimal("0.00")) or Decimal("0.00")
        p_date = acq.purchase_date if acq else None
        ageing = (today - p_date).days if p_date else 0
        supp = acq.supplier.name if acq and acq.supplier else ""
        inv = acq.invoice_number if acq else ""
        cat = a.category.name if a.category else ""

        tot_amt += cost

        rows.append(
            ReportRow(
                cells={
                    "asset_name": a.asset_name,
                    "category": cat,
                    "purchase_date": str(p_date or ""),
                    "supplier": supp,
                    "invoice_no": inv,
                    "amount": scale(cost),
                    "status": a.lifecycle_status.value.capitalize(),
                    "ageing_days": ageing,
                }
            )
        )

    section = ReportSection(
        title="Capital Work-in-Progress (CWIP)",
        columns=cols,
        rows=tuple(rows),
        total=ReportTotal(
            label="Grand Total CWIP",
            cells={"amount": scale(tot_amt)},
            level=0,
        ),
    )

    return ReportDocument(
        title="Capital Work-in-Progress (CWIP) & Uncapitalized Assets",
        subtitle="Uncapitalized assets in draft and ready verification states",
        company_name=company_name,
        period_label=fy_label,
        units=units,
        sections=(section,),
    )


# ============================================================================
# 8. Dimension Summary (Location / Department / Custodian)
# ============================================================================
def build_dimension_summary_report(
    assets: Sequence[Asset],
    dep_lines_by_asset_id: Dict[str, AssetDepreciationLine],
    company_name: str,
    fy_label: str,
    units: str = "absolute",
    lookups_by_id: Optional[Dict[str, str]] = None,
) -> ReportDocument:
    lookups = lookups_by_id or {}
    scale = lambda v: scale_for_units(v, units)

    cols = (
        ColumnSpec(header="Dimension / Group", key="dim_name", kind=ColumnKind.text, width=28),
        ColumnSpec(header="Asset Count", key="count", kind=ColumnKind.number, width=12),
        ColumnSpec(header="Gross Block", key="gross_block", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Accumulated Dep", key="acc_dep", kind=ColumnKind.money, width=18),
        ColumnSpec(header="Net Carrying Value", key="nbv", kind=ColumnKind.money, width=18),
    )

    # Sub-breakdown by Location & Department
    by_loc: Dict[str, List[Asset]] = {}
    by_dept: Dict[str, List[Asset]] = {}
    for a in assets:
        loc = lookups.get(str(a.location_id), "Unassigned Location")
        dept = lookups.get(str(a.department_id), "Unassigned Department")
        by_loc.setdefault(loc, []).append(a)
        by_dept.setdefault(dept, []).append(a)

    def _make_section(title: str, mapping: Dict[str, List[Asset]]) -> ReportSection:
        rows: List[ReportRow] = []
        sec_gb = Decimal("0.00")
        sec_dep = Decimal("0.00")
        sec_nbv = Decimal("0.00")
        sec_cnt = 0

        for name in sorted(mapping.keys()):
            items = mapping[name]
            cnt = len(items)
            gb = sum((x.original_cost or Decimal("0.00") for x in items), Decimal("0.00"))
            dep = sum(
                (
                    dep_lines_by_asset_id[str(x.id)].closing_accumulated_depreciation
                    if str(x.id) in dep_lines_by_asset_id
                    else (x.opening_accumulated_depreciation or Decimal("0.00"))
                    for x in items
                ),
                Decimal("0.00"),
            )
            nbv = max(Decimal("0.00"), gb - dep)

            sec_cnt += cnt
            sec_gb += gb
            sec_dep += dep
            sec_nbv += nbv

            rows.append(
                ReportRow(
                    cells={
                        "dim_name": name,
                        "count": cnt,
                        "gross_block": scale(gb),
                        "acc_dep": scale(dep),
                        "nbv": scale(nbv),
                    }
                )
            )

        return ReportSection(
            title=title,
            columns=cols,
            rows=tuple(rows),
            total=ReportTotal(
                label=f"Total — {title}",
                cells={
                    "count": sec_cnt,
                    "gross_block": scale(sec_gb),
                    "acc_dep": scale(sec_dep),
                    "nbv": scale(sec_nbv),
                },
                level=1,
            ),
        )

    sub_sections = [
        _make_section("Breakdown by Location", by_loc),
        _make_section("Breakdown by Department", by_dept),
    ]

    total_gb = sum((a.original_cost or Decimal("0.00") for a in assets), Decimal("0.00"))
    total_dep = sum(
        (
            dep_lines_by_asset_id[str(a.id)].closing_accumulated_depreciation
            if str(a.id) in dep_lines_by_asset_id
            else (a.opening_accumulated_depreciation or Decimal("0.00"))
            for a in assets
        ),
        Decimal("0.00"),
    )
    total_nbv = max(Decimal("0.00"), total_gb - total_dep)

    root_section = ReportSection(
        title=None,
        columns=cols,
        children=tuple(sub_sections),
        total=ReportTotal(
            label="Grand Total Assets",
            cells={
                "count": len(assets),
                "gross_block": scale(total_gb),
                "acc_dep": scale(total_dep),
                "nbv": scale(total_nbv),
            },
            level=0,
        ),
    )

    return ReportDocument(
        title="Fixed Assets — Dimension Summary",
        subtitle="Asset distribution and carrying amounts across locations and departments",
        company_name=company_name,
        period_label=fy_label,
        units=units,
        sections=(root_section,),
    )


# ============================================================================
# 9. Physical Verification Sheet
# ============================================================================
def build_physical_verification_report(
    assets: Sequence[Asset],
    company_name: str,
    fy_label: str,
    lookups_by_id: Optional[Dict[str, str]] = None,
) -> ReportDocument:
    lookups = lookups_by_id or {}
    cols = (
        ColumnSpec(header="Location", key="location", kind=ColumnKind.text, width=16),
        ColumnSpec(header="Asset Code", key="asset_code", kind=ColumnKind.text, width=14),
        ColumnSpec(header="Asset Description", key="asset_name", kind=ColumnKind.text, width=26),
        ColumnSpec(header="Manufacturer Serial No.", key="serial_no", kind=ColumnKind.text, width=20),
        ColumnSpec(header="Department", key="department", kind=ColumnKind.text, width=16),
        ColumnSpec(header="Custodian", key="custodian", kind=ColumnKind.text, width=16),
        ColumnSpec(header="Condition", key="condition", kind=ColumnKind.text, width=12),
        ColumnSpec(header="Verification Status", key="status", kind=ColumnKind.text, width=16),
        ColumnSpec(header="Auditor Remarks", key="remarks", kind=ColumnKind.text, width=22),
    )

    by_loc: Dict[str, List[Asset]] = {}
    for a in assets:
        loc = lookups.get(str(a.location_id), "Unassigned Location")
        by_loc.setdefault(loc, []).append(a)

    sections: List[ReportSection] = []
    for loc in sorted(by_loc.keys()):
        loc_assets = by_loc[loc]
        rows: List[ReportRow] = []
        for a in loc_assets:
            dept = lookups.get(str(a.department_id), "")
            cust = a.custodian_name or ""
            rows.append(
                ReportRow(
                    cells={
                        "location": loc,
                        "asset_code": a.asset_code or "",
                        "asset_name": a.asset_name,
                        "serial_no": a.manufacturer_serial_number or "",
                        "department": dept,
                        "custodian": cust,
                        "condition": (a.condition.value if hasattr(a.condition, "value") else str(a.condition or "Good")).capitalize(),
                        "status": "[  ] Verified",
                        "remarks": "",
                    }
                )
            )
        sections.append(ReportSection(title=f"Location: {loc}", columns=cols, rows=tuple(rows)))

    return ReportDocument(
        title="Fixed Assets — Physical Verification Checklist",
        subtitle="Physical inventory verification and audit inspection sheet",
        company_name=company_name,
        period_label=fy_label,
        units="absolute",
        sections=tuple(sections),
    )


# ============================================================================
# 10. GST & ITC Summary on Asset Acquisitions
# ============================================================================
def build_gst_itc_summary_report(
    assets: Sequence[Asset],
    company_name: str,
    fy_label: str,
    units: str = "absolute",
) -> ReportDocument:
    scale = lambda v: scale_for_units(v, units)

    cols = (
        ColumnSpec(header="Invoice Date", key="invoice_date", kind=ColumnKind.text, width=12),
        ColumnSpec(header="Invoice No.", key="invoice_no", kind=ColumnKind.text, width=15),
        ColumnSpec(header="Supplier Name", key="supplier", kind=ColumnKind.text, width=22),
        ColumnSpec(header="Supplier GSTIN", key="gstin", kind=ColumnKind.text, width=16),
        ColumnSpec(header="Taxable Value", key="taxable_value", kind=ColumnKind.money, width=16),
        ColumnSpec(header="GST Rate %", key="gst_rate", kind=ColumnKind.percent, width=10),
        ColumnSpec(header="CGST", key="cgst", kind=ColumnKind.money, width=14),
        ColumnSpec(header="SGST", key="sgst", kind=ColumnKind.money, width=14),
        ColumnSpec(header="IGST", key="igst", kind=ColumnKind.money, width=14),
        ColumnSpec(header="Total Tax", key="total_tax", kind=ColumnKind.money, width=15),
        ColumnSpec(header="ITC Treatment", key="itc_treatment", kind=ColumnKind.text, width=14),
        ColumnSpec(header="ITC Claimed", key="itc_claimed", kind=ColumnKind.money, width=15),
        ColumnSpec(header="Tax Capitalized", key="tax_capitalized", kind=ColumnKind.money, width=15),
    )

    # De-duplicate by acquisition if multiple units share an invoice
    acquisitions_seen = set()
    rows: List[ReportRow] = []
    tot = {k: Decimal("0.00") for k in ["taxable", "cgst", "sgst", "igst", "tax", "itc", "cap"]}

    for a in assets:
        acq = a.acquisition
        if not acq or acq.id in acquisitions_seen:
            continue
        acquisitions_seen.add(acq.id)

        taxable = (acq.unit_basic_price * acq.quantity) if (acq.unit_basic_price is not None and acq.quantity is not None) else Decimal("0.00")
        
        # Read stored splits directly
        cgst = acq.cgst_amount if acq.cgst_amount is not None else Decimal("0.00")
        sgst = acq.sgst_amount if acq.sgst_amount is not None else Decimal("0.00")
        igst = acq.igst_amount if acq.igst_amount is not None else Decimal("0.00")
        total_gst = cgst + sgst + igst

        is_eligible = acq.itc_treatment and "eligible" in str(acq.itc_treatment).lower()
        itc_claimed = total_gst if is_eligible else Decimal("0.00")
        tax_cap = Decimal("0.00") if is_eligible else total_gst

        tot["taxable"] += taxable
        tot["cgst"] += cgst
        tot["sgst"] += sgst
        tot["igst"] += igst
        tot["tax"] += total_gst
        tot["itc"] += itc_claimed
        tot["cap"] += tax_cap

        supp_name = acq.supplier.name if acq.supplier else ""
        supp_gstin = acq.supplier.gstin if acq.supplier else ""
        gst_rate = acq.gst_rate

        rows.append(
            ReportRow(
                cells={
                    "invoice_date": str(acq.invoice_date or ""),
                    "invoice_no": acq.invoice_number or "",
                    "supplier": supp_name,
                    "gstin": supp_gstin or "",
                    "taxable_value": scale(taxable),
                    "gst_rate": gst_rate,
                    "cgst": scale(cgst),
                    "sgst": scale(sgst),
                    "igst": scale(igst),
                    "total_tax": scale(total_gst),
                    "itc_treatment": (str(acq.itc_treatment) if acq.itc_treatment else "Eligible").capitalize(),
                    "itc_claimed": scale(itc_claimed),
                    "tax_capitalized": scale(tax_cap),
                }
            )
        )

    section = ReportSection(
        title="GST & Input Tax Credit Analysis",
        columns=cols,
        rows=tuple(rows),
        total=ReportTotal(
            label="Grand Total GST",
            cells={
                "taxable_value": scale(tot["taxable"]),
                "cgst": scale(tot["cgst"]),
                "sgst": scale(tot["sgst"]),
                "igst": scale(tot["igst"]),
                "total_tax": scale(tot["tax"]),
                "itc_claimed": scale(tot["itc"]),
                "tax_capitalized": scale(tot["cap"]),
            },
            level=0,
        ),
    )

    return ReportDocument(
        title="GST & Input Tax Credit (ITC) Summary on Capital Assets",
        subtitle="Tax breakdown and input tax credit eligibility for capital goods acquisitions",
        company_name=company_name,
        period_label=fy_label,
        units=units,
        sections=(section,),
    )
