"""Tests for report export (US10 / FR-029): self-contained HTML + PNG determinism."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _fakes import FakeBackend  # noqa: E402
from proseweight.config import RunConfig  # noqa: E402
from proseweight.probes.suite import load_suite  # noqa: E402
from proseweight.report.export_html import export_html  # noqa: E402
from proseweight.report.png_card import export_png_card, render_card  # noqa: E402
from proseweight.report.render import render_verdict_html  # noqa: E402
from proseweight.report.svg_charts import weight_bars_svg  # noqa: E402
from proseweight.segmentation.pipeline import segment_prompt  # noqa: E402
from proseweight.verdict.orchestrator import run_verdict  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "data" / "suites" / "default-v1.yaml"
PROMPT = "[LB] Never defer.\n[NOOP] Be nice.\n[LB] Output strict JSON.\n"


def _verdict(seed=3):
    suite = load_suite(SUITE)
    segs = segment_prompt(PROMPT)
    cfg = RunConfig(seed=seed, posterior_samples=1500)
    bundle = FakeBackend(seed=seed).measure(PROMPT, segs, suite, cfg)
    return run_verdict(PROMPT, segs, suite, cfg, bundle)


def test_html_is_self_contained_no_external_refs():
    html = render_verdict_html(_verdict())
    assert "<!doctype html>" in html.lower()
    assert "src=\"http" not in html and "href=\"http" not in html
    assert "<svg" in html  # chart inlined as markup
    assert "below the noise floor" in html


def test_html_deterministic_same_seed():
    a = render_verdict_html(_verdict(seed=5))
    b = render_verdict_html(_verdict(seed=5))
    assert a == b


def test_svg_coordinates_are_rounded():
    svg = weight_bars_svg(_verdict())
    # no long floating tails in coordinates
    assert ".000000" not in svg
    assert "◊ noise" in svg  # a noise-floor row is marked


def test_html_size_budget(tmp_path):
    out = export_html(_verdict(), tmp_path / "v.html")
    assert out.stat().st_size < 500_000  # size regression guard


def test_png_card_deterministic_pixels():
    a = render_card(_verdict(seed=8)).convert("RGBA").tobytes()
    b = render_card(_verdict(seed=8)).convert("RGBA").tobytes()
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_png_card_written(tmp_path):
    out = export_png_card(_verdict(), tmp_path / "card.png")
    assert out.exists()
    im = Image.open(out)
    assert im.size == (640, 360)
