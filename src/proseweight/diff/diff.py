"""Prompt diff (US9 / FR-028).

Compares two verdicts (v1 vs v2), reporting per-instruction weight changes,
added/removed instructions, and distinctly flagging any previously load-bearing
instruction whose weight dropped beyond the shared ``load_bearing_drop`` threshold
(the same threshold CI mode uses — Am1). Instructions are matched by their
normalised text (ids are not stable across prompt versions). A differing
blend_config between the two runs is surfaced as a confound, not a regression.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from proseweight.report.schema import Classification, Verdict

LOAD_BEARING_MIN = 67.0


def _key(text: str) -> str:
    return " ".join(text.split()).lower()


@dataclass
class WeightChange:
    text: str
    weight_v1: float
    weight_v2: float

    @property
    def delta(self) -> float:
        return self.weight_v2 - self.weight_v1


@dataclass
class PromptDiff:
    weight_changes: list[WeightChange] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    regressions: list[WeightChange] = field(default_factory=list)
    blend_config_changed: bool = False

    def to_dict(self) -> dict:
        return {
            "weight_changes": [
                {"text": c.text, "weight_v1": c.weight_v1, "weight_v2": c.weight_v2, "delta": c.delta}
                for c in self.weight_changes
            ],
            "added": self.added,
            "removed": self.removed,
            "regressions": [{"text": c.text, "delta": c.delta} for c in self.regressions],
            "blend_config_changed": self.blend_config_changed,
        }


def diff_verdicts(v1: Verdict, v2: Verdict, load_bearing_drop: float = 15.0) -> PromptDiff:
    m1 = {_key(r.instruction.text): r for r in v1.rows}
    m2 = {_key(r.instruction.text): r for r in v2.rows}

    diff = PromptDiff()
    diff.blend_config_changed = v1.run.blend_config.to_dict() != v2.run.blend_config.to_dict()

    for k, r2 in m2.items():
        if k not in m1:
            diff.added.append(r2.instruction.text.strip())
            continue
        r1 = m1[k]
        change = WeightChange(r1.instruction.text.strip(), r1.weight.weight, r2.weight.weight)
        diff.weight_changes.append(change)
        was_load_bearing = (
            r1.label == Classification.LOAD_BEARING or r1.weight.weight >= LOAD_BEARING_MIN
        )
        if was_load_bearing and change.delta <= -load_bearing_drop:
            diff.regressions.append(change)

    for k, r1 in m1.items():
        if k not in m2:
            diff.removed.append(r1.instruction.text.strip())

    return diff
