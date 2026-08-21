"""CI mode exit-code tests (US12 / FR-031)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _builders import make_verdict  # noqa: E402
from proseweight.ci.lint import Baseline, lint  # noqa: E402


def _baseline():
    v = make_verdict([("Never defer.", 90, 0.99), ("Be concise.", 40, 0.99)])
    return v, Baseline.from_verdict(v, "CLAUDE.md", load_bearing_drop=15.0, dead_weight_budget_tokens=40)


def test_benign_exits_zero():
    _, base = _baseline()
    current = make_verdict([("Never defer.", 88, 0.99), ("Be concise.", 42, 0.99)])
    res = lint(current, base)
    assert res.exit_code == 0 and res.ok


def test_load_bearing_regression_exits_one():
    _, base = _baseline()
    current = make_verdict([("Never defer.", 60, 0.99), ("Be concise.", 40, 0.99)])
    res = lint(current, base)
    assert res.exit_code == 1
    assert any("regression" in m for m in res.messages)


def test_new_dead_weight_over_budget_exits_one():
    _, base = _baseline()
    # a new below-noise instruction with a large token cost blows the budget
    current = make_verdict(
        [("Never defer.", 90, 0.99), ("Be concise.", 40, 0.99), ("Fluff filler line.", 3, 0.70)]
    )
    base.dead_weight_budget_tokens = 5  # the new below-noise line (10 tokens) exceeds this
    res = lint(current, base)
    assert res.exit_code == 1
    assert any("dead-weight budget" in m for m in res.messages)


def test_scoping_mismatch_exits_three():
    _, base = _baseline()
    current = make_verdict([("Never defer.", 90, 0.99)], suite_version="2.0.0")
    res = lint(current, base)
    assert res.exit_code == 3
    assert any("scoping" in m for m in res.messages)


def test_baseline_roundtrip(tmp_path):
    v, base = _baseline()
    p = base.save(tmp_path / "weights.json")
    loaded = Baseline.load(p)
    assert loaded.to_dict() == base.to_dict()
