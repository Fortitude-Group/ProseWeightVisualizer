"""Edge-case coverage (T073): empty prompt, all-noise, ties, interrupted runs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _builders import make_verdict  # noqa: E402
from proseweight.report.schema import RunStatus, SchemaError, Verdict  # noqa: E402
from proseweight.segmentation.pipeline import segment_prompt  # noqa: E402


def test_empty_prompt_yields_no_segments():
    assert segment_prompt("") == []
    assert segment_prompt("   \n  \n") == []


def test_whitespace_only_verdict_has_zero_headline():
    v = Verdict(make_verdict([("x", 50, 0.99)]).run, 0.0, [])
    v.validate()  # empty rows are allowed
    assert v.noise_floor_headline_pct == 0.0


def test_all_below_noise_headline_is_100():
    v = make_verdict([("a", 3, 0.70), ("b", 4, 0.72)])
    v.validate()
    assert v.noise_floor_headline_pct == 100.0
    assert all(r.weight.is_noise_floor for r in v.rows)


def test_interval_overlapping_ties_are_allowed():
    # two instructions with identical weight/interval must both validate
    v = make_verdict([("a", 50, 0.99), ("b", 50, 0.99)])
    v.validate()
    assert len(v.rows) == 2


def test_interrupted_run_never_renders_as_verdict():
    base = make_verdict([("a", 90, 0.99)])
    interrupted = Verdict(
        __import__("dataclasses").replace(base.run, status=RunStatus.INTERRUPTED),
        base.noise_floor_headline_pct,
        base.rows,
    )
    with pytest.raises(SchemaError):
        interrupted.validate()


def test_headline_disagreement_is_rejected():
    rows = make_verdict([("a", 90, 0.99), ("b", 3, 0.70)]).rows  # 1 of 2 noise = 50%
    good = make_verdict([("a", 90, 0.99)])
    bad = Verdict(good.run, 0.0, rows)
    with pytest.raises(SchemaError):
        bad.validate()
