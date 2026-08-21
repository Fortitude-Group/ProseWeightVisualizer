"""CI mode (US12 / FR-031): lint a prompt's verdict against a checked-in baseline.

Exit codes (contracts/cli.md):
  0  all within thresholds
  1  a load-bearing instruction dropped beyond threshold, OR new dead weight
     exceeded the budget
  2  usage/config error (raised by the caller)
  3  baseline scoping mismatch (different suite/model/blend_config) — a confound,
     reported distinctly, never a silent pass or a false regression
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from proseweight.report.schema import Verdict

LOAD_BEARING_MIN = 67.0


def _key(text: str) -> str:
    return " ".join(text.split()).lower()


@dataclass
class Baseline:
    prompt_ref: str
    scoping: dict
    load_bearing_drop: float
    dead_weight_budget_tokens: int
    weights: dict[str, float]  # key(text) -> weight
    schema_version: str = "1.0.0"

    @classmethod
    def from_verdict(
        cls,
        verdict: Verdict,
        prompt_ref: str,
        load_bearing_drop: float = 15.0,
        dead_weight_budget_tokens: int = 40,
    ) -> Baseline:
        return cls(
            prompt_ref=prompt_ref,
            scoping={
                "suite_version": verdict.run.suite_version,
                "suite_hash": verdict.run.suite_hash,
                "subject_model": verdict.run.subject_model.model_id,
                "blend_config_version": verdict.run.blend_config.config_version,
            },
            load_bearing_drop=load_bearing_drop,
            dead_weight_budget_tokens=dead_weight_budget_tokens,
            weights={_key(r.instruction.text): r.weight.weight for r in verdict.rows},
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "prompt_ref": self.prompt_ref,
            "scoping": self.scoping,
            "thresholds": {
                "load_bearing_drop": self.load_bearing_drop,
                "dead_weight_budget_tokens": self.dead_weight_budget_tokens,
            },
            "weights": self.weights,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Baseline:
        t = d.get("thresholds", {})
        return cls(
            prompt_ref=d["prompt_ref"],
            scoping=d["scoping"],
            load_bearing_drop=t.get("load_bearing_drop", 15.0),
            dead_weight_budget_tokens=t.get("dead_weight_budget_tokens", 40),
            weights=d["weights"],
            schema_version=d.get("schema_version", "1.0.0"),
        )

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        out.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return out

    @classmethod
    def load(cls, path: str | Path) -> Baseline:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class LintResult:
    exit_code: int
    messages: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _scoping_of(verdict: Verdict) -> dict:
    return {
        "suite_version": verdict.run.suite_version,
        "suite_hash": verdict.run.suite_hash,
        "subject_model": verdict.run.subject_model.model_id,
        "blend_config_version": verdict.run.blend_config.config_version,
    }


def lint(verdict: Verdict, baseline: Baseline) -> LintResult:
    """Compare a fresh verdict against a baseline and return an exit code."""
    if _scoping_of(verdict) != baseline.scoping:
        return LintResult(
            3,
            [
                "scoping mismatch: this run was measured against a different suite/model/"
                "blend_config than the baseline — results are not comparable (confound, "
                "not a regression). Re-baseline or align scoping."
            ],
        )

    msgs: list[str] = []
    current = {_key(r.instruction.text): r for r in verdict.rows}

    for key, base_weight in baseline.weights.items():
        row = current.get(key)
        if row is None:
            continue  # instruction removed; diff mode reports this, lint doesn't fail on it
        if base_weight >= LOAD_BEARING_MIN:
            drop = base_weight - row.weight.weight
            if drop >= baseline.load_bearing_drop:
                msgs.append(
                    f"load-bearing regression: '{row.instruction.text.strip()[:60]}' "
                    f"dropped {drop:.0f} (from {base_weight:.0f} to {row.weight.weight:.0f})"
                )

    new_dead_tokens = sum(d.token_cost for d in verdict.dead_weight)
    if new_dead_tokens > baseline.dead_weight_budget_tokens:
        msgs.append(
            f"dead-weight budget exceeded: {new_dead_tokens} tokens below the noise floor "
            f"(budget {baseline.dead_weight_budget_tokens})"
        )

    return LintResult(1 if msgs else 0, msgs)
