"""Render a phrasing duel as a self-contained "fight card" (US5).

Two phrasings of the same instruction enter; the readout shows which one the
model actually complies with more, and whether the difference clears the region
of practical equivalence. This is the "what matters vs what you think matters"
proof. Same instrument aesthetic and brand toggle as the verdict report.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from proseweight.duel.duel import DuelOutcome

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_VERDICT_LABEL = {
    "a_wins": "Phrasing A wins",
    "b_wins": "Phrasing B wins",
    "practically_equivalent": "Too close to call",
    "inconclusive": "Inconclusive",
}


def render_duel_html(
    outcome: DuelOutcome,
    phrasing_a: str,
    phrasing_b: str,
    label_a: str = "A",
    label_b: str = "B",
    suite_version: str = "1.0.0",
    model: str = "",
    brand: bool = False,
) -> str:
    from proseweight.report.brand import BRAND_NAME, lion_data_uri

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "jinja"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    winner = outcome.verdict
    total = max(outcome.score_a + outcome.score_b, 1e-9)
    return env.get_template("duel.html.jinja").render(
        verdict=winner,
        verdict_label=_VERDICT_LABEL.get(winner, winner),
        decisive=winner in ("a_wins", "b_wins"),
        a={
            "label": label_a, "text": phrasing_a.strip(),
            "score": f"{outcome.score_a:.0f}", "pct": f"{outcome.score_a:.1f}",
            "share": f"{100 * outcome.score_a / total:.1f}", "won": winner == "a_wins",
        },
        b={
            "label": label_b, "text": phrasing_b.strip(),
            "score": f"{outcome.score_b:.0f}", "pct": f"{outcome.score_b:.1f}",
            "share": f"{100 * outcome.score_b / total:.1f}", "won": winner == "b_wins",
        },
        effect=f"{abs(outcome.effect_size) * 100:.1f}",
        p_out=f"{outcome.p_out_rope * 100:.0f}",
        rope=f"{outcome.rope_width * 100:.1f}",
        suite_version=suite_version,
        model=model,
        brand=brand,
        brand_name=BRAND_NAME,
        brand_tagline="Prose Weight · Duel",
        lion_uri=lion_data_uri(),
    )


def export_duel_html(outcome, phrasing_a, phrasing_b, path, **kw) -> Path:
    out = Path(path)
    out.write_text(render_duel_html(outcome, phrasing_a, phrasing_b, **kw), encoding="utf-8")
    return out
