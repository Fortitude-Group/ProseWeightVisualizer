"""Deterministic fake measurement backend for testing verdict assembly.

Plants ground truth by marker word: an instruction whose text contains "[LB]" is
load-bearing (large, consistent signal); "[NOOP]" is inert (near-zero). This lets
us test the stats/blend/classify/headline pipeline — Gate A ranking and Gate B
reproducibility of the ASSEMBLY — without any model weights.
"""

from __future__ import annotations

import numpy as np

from proseweight.verdict.backend import InstructionMeasurement, MeasurementBundle


def _signal(rng, kind: str, n_probes: int):
    if kind == "lb":
        dj = np.clip(rng.normal(0.7, 0.05, n_probes), 0, 1)
        de = np.clip(rng.normal(0.5, 0.05, n_probes), 0, 1)
        pf = np.ones(n_probes, dtype=bool)
        pa = rng.random(n_probes) > 0.85  # removing it mostly breaks compliance
    else:  # noop
        dj = np.clip(rng.normal(0.02, 0.02, n_probes), 0, 1)
        de = np.clip(rng.normal(0.02, 0.02, n_probes), 0, 1)
        pf = rng.random(n_probes) > 0.5
        pa = pf.copy()  # removing it changes nothing
    return dj, de, pf, pa


class FakeBackend:
    """Implements the MeasurementBackend protocol deterministically."""

    def __init__(self, seed: int = 0, n_probes: int = 12):
        self.seed = seed
        self.n_probes = n_probes

    def measure(self, source, segments, suite, cfg) -> MeasurementBundle:
        root = np.random.SeedSequence(self.seed)
        gens = [np.random.default_rng(s) for s in root.spawn(len(segments))]
        instrs = []
        for seg, rng in zip(segments, gens, strict=True):
            kind = "lb" if "[LB]" in seg.text else "noop"
            dj, de, pf, pa = _signal(rng, kind, self.n_probes)
            instrs.append(
                InstructionMeasurement(
                    instruction_id=seg.id,
                    delta_judge=dj,
                    delta_embed=de,
                    pass_full=pf,
                    pass_ablated=pa,
                    attention_prescreen=float(np.mean(dj)),
                    token_cost=seg.token_cost(),
                )
            )
        return MeasurementBundle(
            instructions=instrs,
            noise_sd={"judge": 0.05, "prog": 0.05, "embed": 0.05},
            ceiling=1.0,
            runtime="cpu",
            extra={"embedding_ceiling": 1.0, "ceiling_calibrated_on": "test"},
        )
