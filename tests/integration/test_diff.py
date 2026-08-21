"""Prompt diff tests (US9 / FR-028)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _builders import make_verdict  # noqa: E402
from proseweight.diff.diff import diff_verdicts  # noqa: E402


def test_regression_flagged_when_load_bearing_drops():
    v1 = make_verdict([("Never defer.", 90, 0.99), ("Be nice.", 20, 0.80)])
    v2 = make_verdict([("Never defer.", 60, 0.99), ("Be nice.", 20, 0.80)])
    d = diff_verdicts(v1, v2, load_bearing_drop=15.0)
    assert any("Never defer" in r.text for r in d.regressions)
    assert d.regressions[0].delta == -30.0


def test_benign_change_no_regression():
    v1 = make_verdict([("Never defer.", 90, 0.99)])
    v2 = make_verdict([("Never defer.", 85, 0.99)])  # small drop, within threshold
    d = diff_verdicts(v1, v2, load_bearing_drop=15.0)
    assert d.regressions == []


def test_added_and_removed_detected():
    v1 = make_verdict([("Keep this.", 80, 0.99), ("Old line.", 70, 0.99)])
    v2 = make_verdict([("Keep this.", 80, 0.99), ("New line.", 75, 0.99)])
    d = diff_verdicts(v1, v2)
    assert "New line." in d.added
    assert "Old line." in d.removed


def test_blend_config_change_flagged():
    v1 = make_verdict([("X.", 80, 0.99)], blend_version="1.0.0")
    v2 = make_verdict([("X.", 80, 0.99)], blend_version="2.0.0")
    d = diff_verdicts(v1, v2)
    assert d.blend_config_changed is True
