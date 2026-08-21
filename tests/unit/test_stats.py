"""Tests for the Bayesian stats engine (research.md R1)."""

from __future__ import annotations

import numpy as np

from proseweight.stats.engine import (
    bayes_bootstrap_mean,
    beta_binomial_effect,
    composite_effect,
    duel_decision,
    empirical_bayes_shrink,
    hdi,
    probability_of_direction,
    scale_to_weight,
)


def test_determinism_same_seed_identical():
    a = bayes_bootstrap_mean(np.array([0.1, 0.4, 0.9]), 500, np.random.default_rng(7))
    b = bayes_bootstrap_mean(np.array([0.1, 0.4, 0.9]), 500, np.random.default_rng(7))
    assert np.array_equal(a.draws, b.draws)


def test_beta_binomial_signed_direction():
    rng = np.random.default_rng(1)
    harmful = beta_binomial_effect(k_harm=18, k_help=1, n=20, s=4000, rng=rng)
    assert probability_of_direction(harmful.draws) > 0.95
    assert float(np.mean(harmful.draws)) > 0  # removing it hurts => positive effect


def test_noise_floor_detected_for_null_effect():
    rng = np.random.default_rng(2)
    # equal harm/help => no real effect => low probability of direction
    null = beta_binomial_effect(k_harm=5, k_help=5, n=20, s=4000, rng=rng)
    assert probability_of_direction(null.draws) < 0.95


def test_composite_zscored_blend():
    rng = np.random.default_rng(3)
    sig = {
        "judge": bayes_bootstrap_mean(np.array([0.6, 0.7, 0.65]), 2000, rng),
        "embed": bayes_bootstrap_mean(np.array([0.2, 0.25, 0.22]), 2000, rng),
    }
    comp = composite_effect(sig, {"judge": 0.6, "embed": 0.4}, {"judge": 0.1, "embed": 0.1})
    assert comp.shape == (2000,)
    assert probability_of_direction(comp) > 0.95


def test_shrinkage_pulls_noisy_toward_mean():
    theta = np.array([1.0, 1.1, 0.9, 5.0])  # last is an outlier
    sigma2 = np.array([0.05, 0.05, 0.05, 4.0])  # ...with high uncertainty
    res = empirical_bayes_shrink(theta, sigma2)
    # the uncertain outlier is pulled toward the group far more than the tight ones
    assert abs(res.theta[3] - theta[3]) > abs(res.theta[0] - theta[0])
    assert res.theta[3] < theta[3]


def test_shrinkage_single_instruction_no_pooling():
    res = empirical_bayes_shrink(np.array([2.0]), np.array([0.1]))
    assert res.theta[0] == 2.0
    assert res.tau2 == 0.0


def test_scale_to_weight_clips():
    assert scale_to_weight(0.0, 1.0) == 0.0
    assert scale_to_weight(2.0, 1.0) == 100.0
    assert 40.0 < scale_to_weight(0.5, 1.0) < 60.0


def test_hdi_contains_mass():
    draws = np.random.default_rng(4).normal(0, 1, 10000)
    lo, hi = hdi(draws, 0.95)
    assert lo < 0 < hi
    assert -2.5 < lo < -1.5 and 1.5 < hi < 2.5


def test_duel_practically_equivalent_and_wins():
    rng = np.random.default_rng(5)
    a = rng.normal(0.5, 0.05, 4000)
    b = rng.normal(0.5, 0.05, 4000)
    eq = duel_decision(a, b, rope=0.2)
    assert eq.verdict == "practically_equivalent"

    c = rng.normal(0.9, 0.05, 4000)
    d = rng.normal(0.2, 0.05, 4000)
    win = duel_decision(c, d, rope=0.1)
    assert win.verdict == "a_wins"
