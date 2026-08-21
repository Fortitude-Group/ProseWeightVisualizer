"""Deterministic inline-SVG chart builder (research.md R5).

Pure functions: a verdict's rows -> an SVG string. Every coordinate is routed
through one formatter so the output is byte-stable for snapshot tests; element
ids are content-derived (never uuid/id()).
"""

from __future__ import annotations

from proseweight.report.schema import Classification, Verdict

# Colour per classification (CSS-class-driven in the template; inline here for the card).
CLASS_COLOUR = {
    Classification.LOAD_BEARING: "#155263",
    Classification.CONTRIBUTING: "#3c8da3",
    Classification.DECORATIVE: "#b7c4c9",
    Classification.CONTRADICTED: "#c0532b",
}

_ROW_H = 26
_LABEL_W = 44
_BAR_W = 360
_PAD = 8


def _f(x: float) -> str:
    """Single coordinate formatter — the one source of float rendering."""
    return f"{x:.2f}"


def weight_bars_svg(verdict: Verdict) -> str:
    rows = verdict.rows
    height = _PAD * 2 + _ROW_H * max(len(rows), 1)
    width = _LABEL_W + _BAR_W + 90
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img">'
    ]
    for i, row in enumerate(rows):
        y = _PAD + i * _ROW_H
        w = row.weight
        bar = _BAR_W * w.weight / 100.0
        lo = _BAR_W * w.ci_low / 100.0
        hi = _BAR_W * w.ci_high / 100.0
        colour = CLASS_COLOUR.get(row.label, "#999")
        opacity = "0.45" if w.is_noise_floor else "1.0"
        rid = f"r{i}"
        parts.append(
            f'<text x="{_f(0)}" y="{_f(y + 16)}" class="w" id="{rid}l">{_f(w.weight)}</text>'
        )
        parts.append(
            f'<rect x="{_f(_LABEL_W)}" y="{_f(y + 5)}" width="{_f(bar)}" height="12" '
            f'fill="{colour}" fill-opacity="{opacity}" id="{rid}b"/>'
        )
        # credible-interval whisker
        parts.append(
            f'<line x1="{_f(_LABEL_W + lo)}" y1="{_f(y + 11)}" x2="{_f(_LABEL_W + hi)}" '
            f'y2="{_f(y + 11)}" stroke="#333" stroke-width="1" id="{rid}w"/>'
        )
        if w.is_noise_floor:
            parts.append(
                f'<text x="{_f(_LABEL_W + _BAR_W + 6)}" y="{_f(y + 16)}" '
                f'class="noise" id="{rid}n">◊ noise</text>'
            )
    parts.append("</svg>")
    return "".join(parts)
