"""Tests for judge-noise isolation (FR-006a / T020)."""

from __future__ import annotations

import pytest

from proseweight.judge.noise import (
    assert_local_judge_deterministic,
    estimate_judge_noise,
)


def test_greedy_judge_is_deterministic():
    noise = estimate_judge_noise(lambda: 3.0, m=15)
    assert noise.sd == 0.0
    assert noise.mean == 3.0
    assert_local_judge_deterministic(noise)  # gate passes


def test_noisy_judge_fails_gate():
    scores = iter([3, 4, 2, 3, 4] * 4)
    noise = estimate_judge_noise(lambda: next(scores), m=20)
    assert noise.sd > 0
    with pytest.raises(AssertionError):
        assert_local_judge_deterministic(noise)
