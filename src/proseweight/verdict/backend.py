"""Measurement backend boundary.

The engine's model-dependent work (running the subject model, judging, embedding,
attention) lives behind this Protocol so the verdict-assembly logic — stats,
blend, classification, headline — is fully testable with a deterministic fake.
The real Hugging Face backend (``proseweight.engine.hf_backend``) implements the
same interface and is the only part that needs GPU + model weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass
class InstructionMeasurement:
    """Per-instruction raw signals across the probe suite (already vs the full prompt)."""

    instruction_id: str
    delta_judge: np.ndarray  # |Δjudge|/4 per probe, [0,1]
    delta_embed: np.ndarray  # 1-cos_sim per probe, pre-ceiling
    pass_full: np.ndarray  # bool per probe, full prompt
    pass_ablated: np.ndarray  # bool per probe, instruction removed
    attention_prescreen: float  # attention mass (ranking only, never a verdict)
    token_cost: int
    contradicts_instruction_id: str | None = None


@dataclass
class MeasurementBundle:
    """Everything the stats layer needs for one run."""

    instructions: list[InstructionMeasurement]
    noise_sd: dict[str, float]  # null-condition SD per signal (judge/prog/embed)
    ceiling: float  # calibration composite (bare-task strip) for the 0-100 scale
    runtime: str = "cpu"
    extra: dict = field(default_factory=dict)


class MeasurementBackend(Protocol):
    def measure(self, source: str, segments, suite, cfg) -> MeasurementBundle: ...
