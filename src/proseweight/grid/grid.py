"""Model comparison grid (US8 / FR-027).

Runs one prompt across several local models and stores per-instruction weights
per model, side by side. It NEVER produces or implies a single cross-model score
— the grid is the honest alternative to a universal prompt score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from proseweight.report.schema import Verdict


@dataclass
class GridCell:
    instruction_id: str
    instruction_text: str
    model_id: str
    weight: float
    is_noise_floor: bool


@dataclass
class ComparisonGrid:
    models: list[str] = field(default_factory=list)
    cells: list[GridCell] = field(default_factory=list)

    def weight_of(self, instruction_text: str, model_id: str) -> float | None:
        key = " ".join(instruction_text.split()).lower()
        for c in self.cells:
            if c.model_id == model_id and " ".join(c.instruction_text.split()).lower() == key:
                return c.weight
        return None

    def to_dict(self) -> dict:
        # Deliberately no aggregate/universal score field.
        return {
            "models": self.models,
            "cells": [
                {
                    "instruction_id": c.instruction_id,
                    "instruction_text": c.instruction_text,
                    "model_id": c.model_id,
                    "weight": c.weight,
                    "is_noise_floor": c.is_noise_floor,
                }
                for c in self.cells
            ],
        }


def build_grid(verdicts_by_model: dict[str, Verdict]) -> ComparisonGrid:
    """Assemble a grid from one verdict per model (each already stored per model)."""
    grid = ComparisonGrid(models=list(verdicts_by_model.keys()))
    for model_id, verdict in verdicts_by_model.items():
        for row in verdict.rows:
            grid.cells.append(
                GridCell(
                    instruction_id=row.instruction.id,
                    instruction_text=row.instruction.text,
                    model_id=model_id,
                    weight=row.weight.weight,
                    is_noise_floor=row.weight.is_noise_floor,
                )
            )
    return grid
