"""Write a Verdict as a self-contained HTML file (US10 / FR-029).

The rendered HTML inlines all CSS + SVG and needs no server to view. This module
is the file-writing wrapper around the pure ``render_verdict_html``.
"""

from __future__ import annotations

from pathlib import Path

from proseweight.report.render import render_verdict_html
from proseweight.report.schema import Verdict


def export_html(verdict: Verdict, path: str | Path, brand: bool = False) -> Path:
    html = render_verdict_html(verdict, brand=brand)
    out = Path(path)
    out.write_text(html, encoding="utf-8")
    return out
