"""Neutral report document model for Kubera statutory and asset reporting.

Pure, frozen dataclasses with no I/O, no database imports, and no library-specific
rendering logic (neither openpyxl nor WeasyPrint).

The organising principle:
    Build each report ONCE as a neutral ReportDocument structure, then render it
    TWICE — to Excel (.xlsx) and to PDF (.pdf). The report builder computes every
    total; the renderers only format and display them.

Sections can nest hierarchically (`ReportSection.children`), producing subtotals at
every level of the group hierarchy without duplicate arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ColumnKind(str, Enum):
    """Semantic data type for a report column, driving alignment and formatting."""
    text = "text"
    money = "money"
    number = "number"
    date = "date"
    percent = "percent"


@dataclass(frozen=True)
class ColumnSpec:
    """Specification of a single report column."""
    header: str
    key: str
    kind: ColumnKind = ColumnKind.text
    width: int | None = None
    align: str | None = None

    @property
    def effective_align(self) -> str:
        """Derive text alignment if not explicitly provided."""
        if self.align is not None:
            return self.align
        if self.kind in (ColumnKind.money, ColumnKind.number, ColumnKind.percent):
            return "right"
        return "left"


@dataclass(frozen=True)
class ReportRow:
    """A single data row in a report section."""
    cells: dict[str, Any]
    style: str | None = None  # None | "muted" | "italic" | "synthetic"
    indent: int = 0


@dataclass(frozen=True)
class ReportTotal:
    """A computed summary row for a section, sub-section, or grand total."""
    label: str
    cells: dict[str, Any]
    level: int = 0  # 0 = grand total (double bottom border), 1 = section (thin top border), 2 = sub-section


@dataclass(frozen=True)
class ReportSection:
    """A logical section of a report, potentially containing rows and child sections.
    
    Nested children enable 'sums in the middle': sub-sections each have their own total,
    and the parent section holds the rolled-up total.
    """
    title: str | None
    columns: tuple[ColumnSpec, ...]
    rows: tuple[ReportRow, ...] = ()
    children: tuple[ReportSection, ...] = ()
    total: ReportTotal | None = None
    note_ref: str | None = None

    def iter_all_rows_depth_first(self) -> list[tuple[ReportRow | ReportTotal | str, int]]:
        """Yield (item, depth) depth-first for rendering or verification."""
        items: list[tuple[ReportRow | ReportTotal | str, int]] = []
        if self.title:
            items.append((f"SECTION: {self.title}", 0))
        for r in self.rows:
            items.append((r, r.indent))
        for child in self.children:
            items.extend(child.iter_all_rows_depth_first())
        if self.total:
            items.append((self.total, 0))
        return items


@dataclass(frozen=True)
class ReportDocument:
    """Complete neutral representation of a standalone report or pack sheet."""
    title: str
    subtitle: str | None
    company_name: str
    period_label: str
    units: str  # "absolute" | "thousands" | "lakhs" | "crores"
    sections: tuple[ReportSection, ...]
    meta: dict[str, Any] = field(default_factory=dict)  # generated_at, generated_by, basis notes
    warnings: tuple[str, ...] = ()
    landscape: bool = False

