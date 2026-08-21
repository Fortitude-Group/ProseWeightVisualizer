"""Four-way classification (FR-010).

Ordering of precedence:
  1. Not distinguishable from noise (pd < 0.95)      -> decorative (noise floor)
  2. Ablation improves another instruction's compliance -> contradicted
  3. Otherwise thresholds on the 0-100 weight.
"""

from __future__ import annotations

from proseweight.report.schema import Classification, WeightScore

LOAD_BEARING_MIN = 67.0
CONTRIBUTING_MIN = 34.0


def classify(
    weight: WeightScore, contradicts_instruction_id: str | None
) -> tuple[Classification, str | None]:
    if weight.is_noise_floor:
        return Classification.DECORATIVE, None
    if contradicts_instruction_id:
        return Classification.CONTRADICTED, contradicts_instruction_id
    if weight.weight >= LOAD_BEARING_MIN:
        return Classification.LOAD_BEARING, None
    if weight.weight >= CONTRIBUTING_MIN:
        return Classification.CONTRIBUTING, None
    return Classification.DECORATIVE, None
