"""Tests for the fixed divergence blend + ceiling calibration (FR-006c)."""

from __future__ import annotations

import numpy as np

from proseweight.engine.blend import (
    blend_weights,
    blended_delta,
    calibrate_embedding_ceiling,
    normalise_components,
)
from proseweight.report.schema import BlendConfig


def test_weights_are_fixed_and_sum_to_one():
    cfg = BlendConfig()
    w = blend_weights(cfg)
    assert (w["judge"], w["prog"], w["embed"]) == (0.5, 0.3, 0.2)
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_components_normalised_to_unit_range():
    cfg = BlendConfig(embedding_ceiling=0.5)
    comps = normalise_components(0.8, 0.4, 0.5, cfg)
    assert comps["embed"] == 1.0  # 0.5 clipped to ceiling 0.5 -> 1.0
    assert all(0.0 <= v <= 1.0 for v in comps.values())


def test_blended_delta_is_judge_dominant():
    cfg = BlendConfig()
    only_judge = blended_delta(1.0, 0.0, 0.0, cfg)
    only_prog = blended_delta(0.0, 1.0, 0.0, cfg)
    only_embed = blended_delta(0.0, 0.0, 1.0, cfg)
    assert only_judge > only_prog > only_embed
    assert abs(only_judge - 0.5) < 1e-9


def test_ceiling_calibration_uses_percentile_not_range():
    dists = np.concatenate([np.full(99, 0.3), [0.99]])  # one degenerate outlier
    ceiling = calibrate_embedding_ceiling(dists, percentile=95.0)
    assert ceiling < 0.5  # the outlier does not blow the scale
    assert 0.0 < ceiling <= 1.0


def test_ceiling_empty_defaults_to_one():
    assert calibrate_embedding_ceiling([]) == 1.0
