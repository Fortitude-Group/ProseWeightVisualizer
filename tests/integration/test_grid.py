"""Model comparison grid tests (US8 / FR-027)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _builders import make_verdict  # noqa: E402
from proseweight.grid.grid import build_grid  # noqa: E402


def test_grid_has_per_model_cells():
    v_small = make_verdict([("Never defer.", 90, 0.99), ("Be nice.", 20, 0.80)], model="qwen-0.5b")
    v_big = make_verdict([("Never defer.", 70, 0.99), ("Be nice.", 55, 0.99)], model="qwen-3b")
    grid = build_grid({"qwen-0.5b": v_small, "qwen-3b": v_big})
    assert set(grid.models) == {"qwen-0.5b", "qwen-3b"}
    assert grid.weight_of("Never defer.", "qwen-0.5b") == 90
    assert grid.weight_of("Never defer.", "qwen-3b") == 70


def test_grid_emits_no_universal_score():
    v = make_verdict([("X.", 80, 0.99)], model="m1")
    grid = build_grid({"m1": v})
    d = grid.to_dict()
    # a universal/aggregate cross-model score must not exist
    assert "universal_score" not in d
    assert "aggregate" not in d
    assert "overall" not in d
    assert set(d.keys()) == {"models", "cells"}


def test_grid_shows_model_specificity():
    v1 = make_verdict([("Put this first.", 30, 0.99)], model="m1")
    v2 = make_verdict([("Put this first.", 85, 0.99)], model="m2")
    grid = build_grid({"m1": v1, "m2": v2})
    # same instruction, different weight per model — the whole point of the grid
    assert grid.weight_of("Put this first.", "m1") != grid.weight_of("Put this first.", "m2")
