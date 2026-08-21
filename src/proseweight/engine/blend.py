"""Fixed divergence blend + embedding-ceiling calibration (FR-006c, research.md R4).

The three divergence signals combine with fixed, documented weights applied
uniformly across probes. No renormalize-on-missing path: every probe is
required to populate all three components (a weak PROG check at minimum), so the
nominally-fixed weights stay genuinely uniform. The weights are *validated*
against Gate A, never *fitted* to it.
"""

from __future__ import annotations

import numpy as np

from proseweight.report.schema import BlendConfig

# Signal keys used consistently across the stats + blend + report layers.
SIGNAL_JUDGE = "judge"
SIGNAL_PROG = "prog"
SIGNAL_EMBED = "embed"


def normalise_components(
    delta_judge: float, delta_prog: float, delta_embed: float, cfg: BlendConfig
) -> dict[str, float]:
    """Put the three raw deltas on a common [0, 1] scale before blending.

    - judge: already |Δscore| / 4 in [0, 1]
    - prog:  each probe's check returns [0, 1] (binary is the degenerate case)
    - embed: 1 - cos_sim, clipped to the calibrated ceiling then rescaled to [0, 1]
    """
    embed = float(np.clip(delta_embed, 0.0, cfg.embedding_ceiling) / cfg.embedding_ceiling)
    return {
        SIGNAL_JUDGE: float(np.clip(delta_judge, 0.0, 1.0)),
        SIGNAL_PROG: float(np.clip(delta_prog, 0.0, 1.0)),
        SIGNAL_EMBED: embed,
    }


def blend_weights(cfg: BlendConfig) -> dict[str, float]:
    return {SIGNAL_JUDGE: cfg.w_judge, SIGNAL_PROG: cfg.w_prog, SIGNAL_EMBED: cfg.w_embed}


def blended_delta(
    delta_judge: float, delta_prog: float, delta_embed: float, cfg: BlendConfig
) -> float:
    """Scalar blended behavioural delta for a single (probe, instruction) cell."""
    comps = normalise_components(delta_judge, delta_prog, delta_embed, cfg)
    w = blend_weights(cfg)
    return sum(w[k] * comps[k] for k in comps)


def calibrate_embedding_ceiling(pairwise_distances, percentile: float = 95.0) -> float:
    """Freeze the embedding ceiling as a percentile of the Gate A corpus (T026a).

    A fixed calibration (not the theoretical [0, 2] cosine range) keeps a handful
    of degenerate long-tail outputs from blowing the scale for everything else.
    """
    arr = np.asarray(list(pairwise_distances), dtype=float)
    if arr.size == 0:
        return 1.0
    ceiling = float(np.percentile(arr, percentile))
    return min(max(ceiling, 1e-6), 1.0)
