"""Surface audits: ablation-led ordering (T074) and no-bypass copy (T074a)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _builders import make_verdict  # noqa: E402
from proseweight.report.render import render_verdict_html  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
METHODOLOGY = ROOT / "docs" / "methodology.md"

# public human-facing text surfaces
SURFACES = [
    METHODOLOGY.read_text(encoding="utf-8"),
    render_verdict_html(make_verdict([("Never defer.", 90, 0.99), ("Be nice.", 3, 0.7)])),
]

# marketing terms that would imply the tool is a bypass/jailbreak finder (FR-036)
BYPASS_TERMS = ["jailbreak", "bypass the", "evade the filter", "defeat the guardrail", "circumvent safety"]


def test_ablation_led_ordering_stated_on_surfaces():
    for text in SURFACES:
        low = text.lower()
        assert "ablation" in low
        assert "attention" in low
        # attention is framed as pre-screen/explainer, never the verdict
        assert "pre-screen" in low or "supporting visual" in low
        assert "never" in low  # "never the verdict" / "never as the verdict"


def test_no_bypass_marketing_on_surfaces():
    for text in SURFACES:
        low = text.lower()
        for term in BYPASS_TERMS:
            assert term not in low


def test_html_demotes_attention_to_how_it_works():
    html = render_verdict_html(make_verdict([("x", 80, 0.99)]))
    assert "how it works" in html.lower()
    # the headline surface is the verdict, not the attention chart
    assert html.lower().index("verdict") < html.lower().index("how it works")
