"""Phrasing duel (US5 / FR-024).

Compares two phrasings of the same instruction across the probe suite and reports
a winner only when the posterior probability of a difference outside the ROPE
clears the threshold. The ROPE is anchored to the measured noise floor
(research.md R1 step 7). Absolute per-probe compliance is measured for each
phrasing; the stats reuse the shared engine. Measurement is behind a backend so
this is testable with a deterministic fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from proseweight.engine.determinism import named_generator
from proseweight.stats.engine import bayes_bootstrap_mean, duel_decision

# per-probe compliance = weighted blend of judge score and programmatic pass
_W_JUDGE = 0.6
_W_PASS = 0.4


@dataclass
class PhrasingSignals:
    """Absolute compliance of one phrasing across the probe suite."""

    judge: np.ndarray  # 0..1 per probe
    passed: np.ndarray  # bool per probe
    noise_sd: float  # null-condition compliance SD


class DuelBackend(Protocol):
    def measure_phrasing(self, phrasing: str, suite, cfg) -> PhrasingSignals: ...


@dataclass
class DuelOutcome:
    verdict: str  # a_wins | b_wins | practically_equivalent | inconclusive
    p_out_rope: float
    p_in_rope: float
    effect_size: float
    rope_width: float

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "p_out_rope": self.p_out_rope,
            "p_in_rope": self.p_in_rope,
            "effect_size": self.effect_size,
            "rope_width": self.rope_width,
        }


def _compliance_composite(sig: PhrasingSignals, rng, s: int) -> np.ndarray:
    per_probe = _W_JUDGE * np.clip(sig.judge, 0, 1) + _W_PASS * sig.passed.astype(float)
    return bayes_bootstrap_mean(per_probe, s, rng).draws


def run_duel(
    phrasing_a: str,
    phrasing_b: str,
    backend: DuelBackend,
    suite,
    cfg,
    threshold: float = 0.95,
) -> DuelOutcome:
    sa = backend.measure_phrasing(phrasing_a, suite, cfg)
    sb = backend.measure_phrasing(phrasing_b, suite, cfg)
    s = cfg.posterior_samples
    comp_a = _compliance_composite(sa, named_generator(cfg.seed, "duel:a"), s)
    comp_b = _compliance_composite(sb, named_generator(cfg.seed, "duel:b"), s)
    rope = 2.0 * max(sa.noise_sd, sb.noise_sd)
    res = duel_decision(comp_a, comp_b, rope, threshold)
    return DuelOutcome(res.verdict, res.p_out_rope, res.p_in_rope, res.effect_size, rope)
