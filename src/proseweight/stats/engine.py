"""Bayesian statistics engine — numpy/scipy only, no PPL/MCMC (see research.md R1).

Three stages:
  1. Per-signal posteriors: Beta-Binomial (conjugate) for the pass/fail signal;
     Rubin's Bayesian bootstrap for the two continuous signals.
  2. Composite: z-score each signal by its null-condition SD, combine with the
     fixed blend weights via Monte-Carlo posterior propagation.
  3. Cross-instruction shrinkage: closed-form Normal-Normal empirical Bayes
     (Morris estimator) — the principled substitute for a multiple-comparisons
     correction.

Everything is deterministic given seeded ``numpy.random.Generator`` streams.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_EPS = 1e-12


@dataclass(frozen=True)
class SignalSamples:
    """Posterior draws for a single signal's effect (already noise-subtracted)."""

    draws: np.ndarray  # shape (S,)

    @property
    def sd(self) -> float:
        return float(np.std(self.draws)) or _EPS


def beta_binomial_effect(
    k_harm: int, k_help: int, n: int, s: int, rng: np.random.Generator, prior: float = 1.0
) -> SignalSamples:
    """Signed pass/fail effect from discordant pairs (McNemar-style).

    ``k_harm`` = full passed / ablated failed; ``k_help`` = the reverse. The
    signed effect ``p_harm - p_help`` is positive when removing the instruction
    hurts compliance. Weak Beta(prior, prior) prior (1.0 = uniform).
    """
    p_harm = rng.beta(prior + k_harm, prior + max(n - k_harm, 0), size=s)
    p_help = rng.beta(prior + k_help, prior + max(n - k_help, 0), size=s)
    return SignalSamples(p_harm - p_help)


def bayes_bootstrap_mean(x: np.ndarray, s: int, rng: np.random.Generator) -> SignalSamples:
    """Rubin's Bayesian bootstrap of the mean — nonparametric, exact, seeded."""
    x = np.asarray(x, dtype=float)
    n = x.shape[0]
    if n == 0:
        return SignalSamples(np.zeros(s))
    w = rng.dirichlet(np.ones(n), size=s)  # (S, n) simplex weights
    return SignalSamples(w @ x)


def composite_effect(
    signals: dict[str, SignalSamples],
    weights: dict[str, float],
    noise_sd: dict[str, float],
) -> np.ndarray:
    """Blend per-signal posteriors into one effect posterior.

    Each signal is z-scored by its own null-condition SD so unit-free weights
    combine comparable quantities (research.md R1 step 2).
    """
    total = np.zeros_like(next(iter(signals.values())).draws)
    for name, sig in signals.items():
        z = sig.draws / max(noise_sd.get(name, sig.sd), _EPS)
        total = total + weights.get(name, 0.0) * z
    return total


def probability_of_direction(draws: np.ndarray) -> float:
    """pd = max(P(effect>0), P(effect<0)). Below 0.95 => noise floor."""
    pos = float(np.mean(draws > 0))
    return max(pos, 1.0 - pos)


def hdi(draws: np.ndarray, cred_mass: float = 0.95) -> tuple[float, float]:
    """Highest-density interval of a sample vector."""
    s = np.sort(draws)
    n = s.shape[0]
    if n == 0:
        return (0.0, 0.0)
    interval_idx = int(np.floor(cred_mass * n))
    if interval_idx <= 0:
        return (float(s[0]), float(s[-1]))
    widths = s[interval_idx:] - s[: n - interval_idx]
    lo = int(np.argmin(widths))
    return (float(s[lo]), float(s[lo + interval_idx]))


@dataclass(frozen=True)
class ShrunkPosterior:
    theta: np.ndarray  # per-instruction shrunk posterior mean, shape (M,)
    var: np.ndarray  # per-instruction shrunk posterior variance, shape (M,)
    mu: float  # grand mean
    tau2: float  # between-instruction variance


def empirical_bayes_shrink(theta_hat: np.ndarray, sigma2: np.ndarray) -> ShrunkPosterior:
    """Closed-form Normal-Normal partial pooling (Morris 1983).

    Shrinks noisy per-instruction estimates toward the precision-weighted grand
    mean in proportion to their uncertainty — the multiple-comparisons answer.
    """
    theta_hat = np.asarray(theta_hat, dtype=float)
    sigma2 = np.clip(np.asarray(sigma2, dtype=float), _EPS, None)
    m = theta_hat.shape[0]
    if m == 0:
        return ShrunkPosterior(theta_hat, sigma2, 0.0, 0.0)
    prec = 1.0 / sigma2
    mu = float(np.average(theta_hat, weights=prec))
    if m == 1:
        return ShrunkPosterior(theta_hat.copy(), sigma2.copy(), mu, 0.0)
    num = float(np.sum((theta_hat - mu) ** 2 * prec) - (m - 1))
    denom = float(np.sum(prec) - np.sum(prec**2) / np.sum(prec))
    tau2 = max(0.0, num / denom) if denom > _EPS else 0.0
    b = sigma2 / (sigma2 + tau2)  # shrinkage factor per instruction
    theta = b * mu + (1.0 - b) * theta_hat
    var = (1.0 - b) * sigma2
    return ShrunkPosterior(theta, var, mu, tau2)


def scale_to_weight(theta: float, ceiling: float) -> float:
    """Map a composite effect onto 0-100 against a fixed calibration ceiling."""
    ceiling = max(ceiling, _EPS)
    return float(100.0 * np.clip(theta / ceiling, 0.0, 1.0))


@dataclass(frozen=True)
class DuelResult:
    p_out_rope: float
    p_in_rope: float
    verdict: str  # a_wins | b_wins | practically_equivalent | inconclusive
    effect_size: float


def duel_decision(
    composite_a: np.ndarray,
    composite_b: np.ndarray,
    rope: float,
    threshold: float = 0.95,
) -> DuelResult:
    """ROPE-based duel verdict (research.md R1 step 7). ``rope`` = 2*noise SD."""
    diff = composite_a - composite_b
    p_out = float(np.mean(np.abs(diff) > rope))
    p_in = float(np.mean(np.abs(diff) <= rope))
    effect = float(np.mean(diff))
    if p_out > threshold:
        verdict = "a_wins" if effect > 0 else "b_wins"
    elif p_in > threshold:
        verdict = "practically_equivalent"
    else:
        verdict = "inconclusive"
    return DuelResult(p_out, p_in, verdict, effect)
