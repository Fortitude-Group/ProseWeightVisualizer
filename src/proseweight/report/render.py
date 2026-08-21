"""Render a Verdict to self-contained HTML (research.md R5).

Pure function of the verdict plus an injected ``now`` (default None => omitted),
so output is deterministic and golden-testable.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from proseweight.report.schema import Classification, Verdict
from proseweight.report.svg_charts import weight_bars_svg

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_LABEL_HUMAN = {
    Classification.LOAD_BEARING: "load-bearing",
    Classification.CONTRIBUTING: "contributing",
    Classification.DECORATIVE: "decorative",
    Classification.CONTRADICTED: "contradicted",
}


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "jinja"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_verdict_html(verdict: Verdict) -> str:
    """Self-contained HTML string (no external assets, no server needed)."""
    rows = [
        {
            "weight": f"{r.weight.weight:.0f}",
            "ci_low": f"{r.weight.ci_low:.0f}",
            "ci_high": f"{r.weight.ci_high:.0f}",
            "is_noise_floor": r.weight.is_noise_floor,
            "label": r.label.value,
            "label_h": _LABEL_HUMAN[r.label],
            "text": r.instruction.text.strip(),
        }
        for r in verdict.rows
    ]
    return _env().get_template("verdict.html.jinja").render(
        headline=f"{verdict.noise_floor_headline_pct:.0f}",
        suite_version=verdict.run.suite_version,
        model=verdict.run.subject_model.model_id,
        seed=verdict.run.seed,
        depth=verdict.run.depth,
        reproducibility=verdict.run.reproducibility.value,
        rows=rows,
        dead_weight=[{"instruction_id": d.instruction_id, "token_cost": d.token_cost} for d in verdict.dead_weight],
        chart_svg=weight_bars_svg(verdict),
    )
