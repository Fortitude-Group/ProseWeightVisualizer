"""Emphasis audit (US6 / FR-025).

Auto-generates formatting variants of one instruction (CAPS, bold, "IMPORTANT:",
exclamation, repetition, list position) and measures which devices actually move
weight, per model, by duelling each variant against the plain phrasing. Variant
generation is a pure text transform; measurement reuses the duel machinery.
"""

from __future__ import annotations

from dataclasses import dataclass

from proseweight.duel.duel import DuelBackend, DuelOutcome, run_duel


def emphasis_variants(text: str) -> dict[str, str]:
    """Return one variant per formatting device. Deterministic."""
    stripped = text.strip()
    no_period = stripped.rstrip(".")
    return {
        "caps": stripped.upper(),
        "bold": f"**{stripped}**",
        "important": f"IMPORTANT: {stripped}",
        "exclamation": f"{no_period}!",
        "repetition": f"{stripped} {stripped}",
        "list_item": f"- {stripped}",
    }


@dataclass
class EmphasisResult:
    device: str
    outcome: DuelOutcome
    moved_weight: bool

    def to_dict(self) -> dict:
        return {"device": self.device, "moved_weight": self.moved_weight, **self.outcome.to_dict()}


def run_emphasis_audit(
    text: str, backend: DuelBackend, suite, cfg
) -> list[EmphasisResult]:
    """Duel each emphasis variant against the plain phrasing."""
    results: list[EmphasisResult] = []
    for device, variant in emphasis_variants(text).items():
        outcome = run_duel(variant, text, backend, suite, cfg)
        moved = outcome.verdict in ("a_wins", "b_wins")
        results.append(EmphasisResult(device, outcome, moved))
    return results
