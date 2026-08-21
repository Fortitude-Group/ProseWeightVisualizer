"""Suite self-quality — the instrument's own dead-weight logic (research.md R3).

Harvested from the same (run x instruction x probe x score) table, pivoted along
the PROBE axis instead of the instruction axis. No second measurement mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MIN_ABLATION_RUNS = 20  # don't kill a good probe on sparse early data
SNR_FLOOR = 1.0
SATURATION_HIGH = 0.97
SATURATION_LOW = 0.03


@dataclass(frozen=True)
class ProbeQuality:
    probe_id: str
    discrimination: float
    snr: float
    n_ablation_runs: int
    flag: str | None  # None | LOW_DISCRIMINATION | SATURATED


def probe_quality(
    probe_id: str,
    deltas_by_instruction: np.ndarray,  # |delta_p_i| across instructions for this probe
    fixed_prompt_noise_sd: float,
    all_cell_scores: np.ndarray,  # every (prompt-variant, model) score for this probe
) -> ProbeQuality:
    deltas = np.abs(np.asarray(deltas_by_instruction, dtype=float))
    n = deltas.shape[0]
    discrimination = float(np.mean(deltas)) if n else 0.0
    sd = max(float(fixed_prompt_noise_sd), 1e-9)
    snr = discrimination / sd
    mean_score = float(np.mean(all_cell_scores)) if all_cell_scores.size else 0.5

    flag: str | None = None
    if mean_score > SATURATION_HIGH or mean_score < SATURATION_LOW:
        flag = "SATURATED"
    elif n >= MIN_ABLATION_RUNS and snr < SNR_FLOOR:
        flag = "LOW_DISCRIMINATION"
    return ProbeQuality(probe_id, discrimination, snr, n, flag)
