"""Candidate pairwise conflict detection (US2 / FR-013 / T040).

Full pairwise ablation is combinatorial; only the candidate pairs flagged by the
single-ablation pass are measured. A pair is a conflict when removing one
instruction increases the other's measured effect (they fight each other). The
pairwise-ablation measurement is injected so this is testable without models.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import combinations

from proseweight.report.schema import ClassifiedRow, Conflict

# a positive interaction_delta above this => the pair meaningfully fights
CONFLICT_MIN_DELTA = 0.1


def candidate_pairs(rows: list[ClassifiedRow]) -> list[tuple[str, str]]:
    """Pairs worth checking: instructions with non-trivial individual effect.

    Cheap heuristic pre-filter so pairwise ablation runs on candidates only.
    """
    active = [r.instruction.id for r in rows if not r.weight.is_noise_floor]
    return list(combinations(active, 2))


def detect_conflicts(
    rows: list[ClassifiedRow],
    interaction: Callable[[str, str], float],
    min_delta: float = CONFLICT_MIN_DELTA,
) -> list[Conflict]:
    """Return conflicts among candidate pairs. ``interaction(a, b)`` returns the
    measured mutual-reduction delta for the pair (>0 = they reduce each other)."""
    conflicts: list[Conflict] = []
    for a, b in candidate_pairs(rows):
        delta = interaction(a, b)
        if delta >= min_delta:
            conflicts.append(Conflict(a, b, float(delta)))
    return conflicts
