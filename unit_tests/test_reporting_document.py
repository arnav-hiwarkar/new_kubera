"""Unit tests for neutral ReportDocument data structures and traversal."""
from decimal import Decimal
from app.services.reporting.document import (
    ColumnKind,
    ColumnSpec,
    ReportDocument,
    ReportRow,
    ReportSection,
    ReportTotal,
)


def test_nested_report_section_depth_first_order():
    cols = (
        ColumnSpec(header="Particulars", key="particulars", kind=ColumnKind.text),
        ColumnSpec(header="Amount", key="amount", kind=ColumnKind.money),
    )

    child_sub = ReportSection(
        title="Cash on Hand",
        columns=cols,
        rows=(
            ReportRow(cells={"particulars": "Petty Cash", "amount": Decimal("500.00")}, indent=0),
        ),
        total=ReportTotal(label="Total Cash on Hand", cells={"amount": Decimal("500.00")}, level=2),
    )

    parent_sec = ReportSection(
        title="Current Assets",
        columns=cols,
        rows=(
            ReportRow(cells={"particulars": "Prepayments", "amount": Decimal("200.00")}, indent=0),
        ),
        children=(child_sub,),
        total=ReportTotal(label="Total Current Assets", cells={"amount": Decimal("700.00")}, level=1),
    )

    doc = ReportDocument(
        title="Sample Assets Report",
        subtitle="Schedule III",
        company_name="Acme Corp Ltd",
        period_label="FY 2024-25",
        units="absolute",
        sections=(parent_sec,),
    )

    items = parent_sec.iter_all_rows_depth_first()
    labels = []
    for item, depth in items:
        if isinstance(item, str):
            labels.append((item, depth))
        elif isinstance(item, ReportRow):
            labels.append((item.cells["particulars"], depth))
        elif isinstance(item, ReportTotal):
            labels.append((item.label, depth))

    expected = [
        ("SECTION: Current Assets", 0),
        ("Prepayments", 0),
        ("SECTION: Cash on Hand", 0),
        ("Petty Cash", 0),
        ("Total Cash on Hand", 0),
        ("Total Current Assets", 0),
    ]
    assert labels == expected
    assert doc.title == "Sample Assets Report"
