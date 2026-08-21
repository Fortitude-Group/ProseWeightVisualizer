"""Phrasing-duel tests (US5 / FR-024 / SC-009)."""

from __future__ import annotations

import numpy as np

from proseweight.config import RunConfig
from proseweight.duel.duel import PhrasingSignals, run_duel


class FakeDuelBackend:
    """Compliance keyed by a marker: '[WIN]' phrasings comply strongly."""

    def __init__(self, seed=0, n_probes=12):
        self.seed = seed
        self.n_probes = n_probes

    def measure_phrasing(self, phrasing, suite, cfg) -> PhrasingSignals:
        rng = np.random.default_rng(self.seed + hash(phrasing) % 1000)
        if "[WIN]" in phrasing:
            judge = np.clip(rng.normal(0.9, 0.03, self.n_probes), 0, 1)
            passed = rng.random(self.n_probes) > 0.1
        elif "[SAME]" in phrasing:
            judge = np.clip(rng.normal(0.5, 0.03, self.n_probes), 0, 1)
            passed = rng.random(self.n_probes) > 0.5
        else:
            judge = np.clip(rng.normal(0.3, 0.03, self.n_probes), 0, 1)
            passed = rng.random(self.n_probes) > 0.7
        return PhrasingSignals(judge=judge, passed=passed, noise_sd=0.03)


def _cfg():
    return RunConfig(seed=3, posterior_samples=3000)


def test_clear_winner_declared():
    out = run_duel("[WIN] do the thing", "beige do the thing", FakeDuelBackend(), None, _cfg())
    assert out.verdict == "a_wins"
    assert out.p_out_rope > 0.95


def test_no_significant_difference_not_a_winner():
    out = run_duel("[SAME] one", "[SAME] two", FakeDuelBackend(), None, _cfg())
    assert out.verdict in ("practically_equivalent", "inconclusive")
    assert out.verdict not in ("a_wins", "b_wins")


def test_reports_effect_and_posterior_always():
    out = run_duel("[SAME] a", "[SAME] b", FakeDuelBackend(), None, _cfg())
    d = out.to_dict()
    assert "effect_size" in d and "p_out_rope" in d and "rope_width" in d
