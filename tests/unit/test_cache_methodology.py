"""Unit test: the methodology page carries the cache-cost section (T047 / US9 / FR-026)."""

from __future__ import annotations

from pathlib import Path

_DOC = Path(__file__).resolve().parents[2] / "docs" / "methodology.md"


def test_cache_cost_section_exists_and_covers_the_required_topics():
    text = _DOC.read_text(encoding="utf-8").lower()
    assert "how cachescope measures cache waste" in text
    # divergence detection to the byte
    assert "byte-diff" in text or "first byte that differs" in text
    # measured cost versus attributed cause
    assert "measured" in text and "attribut" in text
    # the PAYG vs subscription meter fork
    assert "shadow-price" in text and "subscription" in text
    # breakpoint model + per-model minimums (non-monotonic)
    assert "breakpoint" in text
    for minimum in ("512", "1,024", "2,048", "4,096"):
        assert minimum in text
    # known limitations
    for topic in ("reconstruction", "diagnostics", "amortisation"):
        assert topic in text
