"""Per-auditor engagement activity report.

Neutral ReportDocument in, rendered twice downstream (xlsx/pdf) like every other
AuditEase report. Pure — takes prepared event dicts, touches no DB.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from app.services.reporting.document import (
    ColumnKind, ColumnSpec, ReportDocument, ReportRow, ReportSection,
)

_COLS = (
    ColumnSpec(header="Timestamp", key="ts", kind=ColumnKind.text, width=24),
    ColumnSpec(header="Action", key="action", kind=ColumnKind.text, width=28),
    ColumnSpec(header="Entity", key="entity", kind=ColumnKind.text, width=24),
    ColumnSpec(header="Details", key="details", kind=ColumnKind.text, width=46),
)


def _details(meta: dict[str, Any] | None) -> str:
    if not meta:
        return ""
    parts = []
    for k, v in meta.items():
        s = str(v)
        parts.append(f"{k}: {s}")
    return "; ".join(parts)[:120]


def build_auditor_activity_report(
    events: Sequence[dict],
    auditor_name: str,
    auditor_email: str,
    company_name: str,
    period_label: str,
) -> ReportDocument:
    rows = tuple(
        ReportRow(cells={
            "ts": e["created_at"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(e["created_at"], datetime) else str(e["created_at"]),
            "action": e["action"],
            "entity": e["entity_type"],
            "details": _details(e.get("metadata")),
        })
        for e in events
    )
    section = ReportSection(title="Activity", columns=_COLS, rows=rows)
    return ReportDocument(
        title=f"Auditor Activity Report — {auditor_name}",
        subtitle=f"{auditor_email} · {len(rows)} event(s)",
        company_name=company_name,
        period_label=period_label,
        units="none",
        sections=(section,),
    )
