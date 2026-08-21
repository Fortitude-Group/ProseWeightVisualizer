"""Position sensitivity (US7 / FR-026).

Moves an instruction through prompt positions and re-measures its weight at each,
giving a per-model empirical answer to "does putting it first matter?". The
repositioning is a pure text operation; the weight measurement is injected so
this is testable without models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

POSITIONS = ("top", "middle", "bottom")


def reposition(prompt: str, instruction_text: str, position: str) -> str:
    """Remove ``instruction_text`` (line-matched) and reinsert it at ``position``."""
    key = instruction_text.strip()
    lines = prompt.splitlines()
    kept = [ln for ln in lines if ln.strip() != key]
    if position == "top":
        idx = 0
    elif position == "bottom":
        idx = len(kept)
    else:  # middle
        idx = len(kept) // 2
    kept.insert(idx, key)
    return "\n".join(kept) + ("\n" if prompt.endswith("\n") else "")


class PositionBackend(Protocol):
    def measure_instruction_weight(
        self, prompt: str, instruction_text: str, suite, cfg
    ) -> tuple[float, float, float]:
        """Return (weight, ci_low, ci_high) for the instruction in this prompt."""
        ...


@dataclass
class PositionPoint:
    position: str
    weight: float
    ci_low: float
    ci_high: float


def run_position_sweep(
    prompt: str,
    instruction_text: str,
    backend: PositionBackend,
    suite,
    cfg,
    positions=POSITIONS,
) -> list[PositionPoint]:
    points: list[PositionPoint] = []
    for pos in positions:
        variant = reposition(prompt, instruction_text, pos)
        w, lo, hi = backend.measure_instruction_weight(variant, instruction_text, suite, cfg)
        points.append(PositionPoint(pos, w, lo, hi))
    return points
