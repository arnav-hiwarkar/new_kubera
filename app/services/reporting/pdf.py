import ctypes.util
import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Any, Sequence

# On macOS, Homebrew installs libraries in /opt/homebrew/lib (or /usr/local/lib on Intel).
# Standard ctypes.util.find_library on macOS does not search Homebrew directories by default.
# Providing a fallback hook allows WeasyPrint / CFFI to locate pango, gobject, harfbuzz, and cairo
# seamlessly in local development without requiring system-wide environment variables.
if sys.platform == "darwin" and not os.environ.get("DISABLE_MACOS_DYLIB_FALLBACK"):
    _orig_find_library = ctypes.util.find_library

    def _macos_find_library(name: str) -> str | None:
        res = _orig_find_library(name)
        if res:
            return res
        for base_dir in ("/opt/homebrew/lib", "/usr/local/lib"):
            candidates = [
                os.path.join(base_dir, name),
                os.path.join(base_dir, f"lib{name}.dylib"),
                os.path.join(base_dir, f"{name}.dylib"),
            ]
            # Strip trailing -0 or version suffixes e.g. gobject-2.0-0 -> libgobject-2.0.dylib
            if "-" in name:
                parts = name.split("-")
                candidates.extend([
                    os.path.join(base_dir, f"lib{parts[0]}-{parts[1]}.dylib") if len(parts) > 1 else "",
                    os.path.join(base_dir, f"lib{parts[0]}.dylib"),
                ])
            for candidate in candidates:
                if candidate and os.path.exists(candidate):
                    return candidate
        return None

    ctypes.util.find_library = _macos_find_library

from jinja2 import Environment, FileSystemLoader, select_autoescape
import weasyprint

from app.services.reporting.document import ColumnKind, ColumnSpec, ReportDocument, ReportSection
from app.services.reporting.format import format_date, format_money, format_number, format_percent, scale_for_units


def _format_cell(val: Any, kind: ColumnKind, units: str) -> str:
    """Helper used in Jinja2 templates to format cell values cleanly."""
    if val is None or val == "":
        return "—"
    if kind == ColumnKind.money:
        return format_money(val, units=units, indian=True)
    if kind == ColumnKind.number:
        return format_number(val, decimals=2, indian=True)
    if kind == ColumnKind.percent:
        return format_percent(val, decimals=2)
    if kind == ColumnKind.date:
        return format_date(val)
    return str(val)


def _get_jinja_env() -> Environment:
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals.update({
        "format_cell": _format_cell,
        "format_money": format_money,
        "format_quantity": format_number,
        "format_number": format_number,
        "format_percent": format_percent,
        "format_date": format_date,
        "scale_for_units": scale_for_units,
        "ColumnKind": ColumnKind,
    })
    return env


_ENV = _get_jinja_env()


def render_html(doc: ReportDocument, landscape: bool | None = None) -> str:
    """Render a ReportDocument to a standalone HTML string."""
    eff_landscape = doc.landscape if landscape is None else landscape
    template = _ENV.get_template("report.html")
    return template.render(doc=doc, landscape=eff_landscape)


def render_pdf(doc: ReportDocument, landscape: bool | None = None) -> bytes:
    """Render a ReportDocument to PDF binary bytes via WeasyPrint."""
    html_str = render_html(doc, landscape=landscape)
    html = weasyprint.HTML(string=html_str)
    return html.write_pdf()


def render_pack_html(
    docs: Sequence[ReportDocument],
    pack_title: str = "Financial & Statutory Reports Pack",
    landscape: bool = False,
) -> str:
    """Render multiple ReportDocuments to a multi-page HTML document with Cover sheet."""
    template = _ENV.get_template("pack.html")
    company_name = docs[0].company_name if docs else ""
    period_label = docs[0].period_label if docs else ""
    units = docs[0].units if docs else "absolute"
    generated_at = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    return template.render(
        docs=docs,
        pack_title=pack_title,
        company_name=company_name,
        period_label=period_label,
        units=units,
        generated_at=generated_at,
        landscape=landscape,
    )


def render_pack_pdf(
    docs: Sequence[ReportDocument],
    pack_title: str = "Financial & Statutory Reports Pack",
    landscape: bool = False,
) -> bytes:
    """Render multiple ReportDocuments to a single combined PDF document."""
    html_str = render_pack_html(docs, pack_title=pack_title, landscape=landscape)
    html = weasyprint.HTML(string=html_str)
    return html.write_pdf()
