"""Tests for the brand toggle (concealment guarantee) and the duel fight-card render."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _builders import make_verdict  # noqa: E402
from proseweight.duel.duel import DuelOutcome  # noqa: E402
from proseweight.report.duel_render import render_duel_html  # noqa: E402
from proseweight.report.render import render_verdict_html  # noqa: E402


def test_unbranded_report_has_no_fortitude_trace():
    """brand=False MUST leave zero Fortitude traces (the colleague audience)."""
    html = render_verdict_html(make_verdict([("x", 80, 0.99)]), brand=False)
    assert "fortitude" not in html.lower()
    assert "lion" not in html.lower()


def test_branded_report_shows_fortitude():
    html = render_verdict_html(make_verdict([("x", 80, 0.99)]), brand=True)
    assert "Fortitude Omnis Group" in html
    assert "<svg" in html  # lion emblem present


def test_brand_toggle_does_not_change_the_data():
    v = make_verdict([("Never defer.", 90, 0.99)])
    assert "Never defer." in render_verdict_html(v, brand=False)
    assert "Never defer." in render_verdict_html(v, brand=True)


def _outcome(verdict, sa, sb):
    return DuelOutcome(verdict=verdict, p_out_rope=0.9, p_in_rope=0.05, effect_size=(sa - sb) / 100,
                       rope_width=0.1, score_a=sa, score_b=sb)


def test_duel_render_self_contained_and_names_winner():
    html = render_duel_html(_outcome("a_wins", 74, 52), "BOIL THE OCEAN", "please be thorough", brand=True)
    assert "<!doctype html>" in html.lower()
    assert 'src="http' not in html and 'href="http' not in html
    assert "Phrasing A wins" in html
    assert "Winner" in html
    assert "BOIL THE OCEAN" in html and "please be thorough" in html


def test_duel_render_tie_declares_no_winner():
    html = render_duel_html(_outcome("practically_equivalent", 50, 49), "A phrasing", "B phrasing")
    assert "Too close to call" in html
    assert "neither phrasing wins" in html


def test_duel_unbranded_no_fortitude():
    html = render_duel_html(_outcome("a_wins", 74, 52), "A", "B", brand=False)
    assert "fortitude" not in html.lower()
