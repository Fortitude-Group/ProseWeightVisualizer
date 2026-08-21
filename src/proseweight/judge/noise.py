"""Judge-noise isolation (FR-006a, research.md R4 / task T020).

Hold a fixed output constant and re-score it M times to measure judge variance
directly, isolated from subject-model variance. With a local greedy judge this
must be near-zero; ``assert_local_judge_deterministic`` is the CI gate that fails
loudly if it isn't (usually a missing determinism flag, not real uncertainty).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

NEAR_ZERO_SD = 1e-6


@dataclass(frozen=True)
class JudgeNoise:
    sd: float
    mean: float
    n_repeats: int


def estimate_judge_noise(score_fn: Callable[[], float], m: int = 20) -> JudgeNoise:
    """Re-score an identical output ``m`` times; return the score SD/mean."""
    scores = np.array([float(score_fn()) for _ in range(m)], dtype=float)
    return JudgeNoise(sd=float(np.std(scores)), mean=float(np.mean(scores)), n_repeats=m)


def assert_local_judge_deterministic(noise: JudgeNoise) -> None:
    """CI gate: a local greedy judge's self-consistency noise must be ~0."""
    if noise.sd > NEAR_ZERO_SD:
        raise AssertionError(
            f"local judge self-consistency SD={noise.sd:.3g} is not near zero; "
            "check greedy decoding / determinism flags rather than treating it as signal"
        )
