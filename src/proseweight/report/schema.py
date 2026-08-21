"""Versioned report / verdict schema — the shared contract (Principle I/II).

Every surface (CLI, web, export, API, CI) reads and writes these types. The
``schema_version`` is stamped into every artefact; a breaking field change is a
MAJOR bump with a migration note (see contracts/report-schema.md).

These are plain dataclasses with explicit ``to_dict`` / ``from_dict`` and a
``validate`` pass so the guarantees in the contract are enforced in code and
tested, without a heavyweight validation dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

SCHEMA_VERSION = "1.0.0"

# ``pd`` (probability of direction) below this threshold => not distinguishable
# from noise. Kept here so the schema guarantee and the stats engine agree.
NOISE_FLOOR_PD = 0.95


class Classification(str, Enum):
    LOAD_BEARING = "load_bearing"
    CONTRIBUTING = "contributing"
    DECORATIVE = "decorative"
    CONTRADICTED = "contradicted"


class Reproducibility(str, Enum):
    GUARANTEED = "guaranteed"
    BEST_EFFORT = "best_effort"


class RunStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    INTERRUPTED = "interrupted"


class JudgeBackendKind(str, Enum):
    LOCAL_HF = "local-hf"
    ANTHROPIC_API = "anthropic-api"


class SchemaError(ValueError):
    """Raised when a report object violates a contract guarantee."""


@dataclass(frozen=True)
class ModelRef:
    model_id: str
    revision: str = "unpinned"
    runtime: str = "cpu"  # cuda | cpu
    dtype: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BlendConfig:
    config_version: str = "1.0.0"
    w_judge: float = 0.5
    w_prog: float = 0.3
    w_embed: float = 0.2
    embedding_ceiling: float = 1.0
    embedding_ceiling_calibrated_on: str = ""
    judge_decoding: dict[str, Any] = field(default_factory=lambda: {"mode": "greedy"})

    def validate(self) -> None:
        total = self.w_judge + self.w_prog + self.w_embed
        if abs(total - 1.0) > 1e-9:
            raise SchemaError(f"blend weights must sum to 1.0, got {total}")
        if not (0.0 < self.embedding_ceiling <= 1.0):
            raise SchemaError("embedding_ceiling must be in (0, 1]")

    @property
    def weights(self) -> tuple[float, float, float]:
        return (self.w_judge, self.w_prog, self.w_embed)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WeightScore:
    """A per-instruction 0-100 behavioural weight with its Bayesian posterior."""

    instruction_id: str
    weight: float
    ci_low: float
    ci_high: float
    pd: float  # probability of direction
    component_ablation: float = 0.0
    component_attention: float = 0.0
    component_paraphrase: float = 0.0
    raw_delta_judge: float = 0.0
    raw_delta_prog: float = 0.0
    raw_delta_embed: float = 0.0

    @property
    def is_noise_floor(self) -> bool:
        return self.pd < NOISE_FLOOR_PD

    def validate(self) -> None:
        if not (0.0 <= self.weight <= 100.0):
            raise SchemaError(f"weight out of range: {self.weight}")
        if not (self.ci_low <= self.weight <= self.ci_high):
            raise SchemaError(
                f"weight {self.weight} not within CI [{self.ci_low}, {self.ci_high}]"
            )
        if not (0.0 <= self.pd <= 1.0):
            raise SchemaError(f"pd out of range: {self.pd}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["is_noise_floor"] = self.is_noise_floor
        return d


@dataclass(frozen=True)
class InstructionRow:
    id: str
    text: str
    start_offset: int
    end_offset: int
    block_type: str = "paragraph"
    heading_path: list[str] = field(default_factory=list)
    token_cost: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClassifiedRow:
    instruction: InstructionRow
    weight: WeightScore
    label: Classification
    contradicts_instruction_id: str | None = None

    def validate(self) -> None:
        self.weight.validate()
        if self.label is Classification.CONTRADICTED and not self.contradicts_instruction_id:
            raise SchemaError(
                f"instruction {self.instruction.id} classified 'contradicted' "
                "but names no conflicting instruction"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction.to_dict(),
            "weight": self.weight.to_dict(),
            "classification": {
                "label": self.label.value,
                "contradicts_instruction_id": self.contradicts_instruction_id,
            },
        }


@dataclass(frozen=True)
class Conflict:
    instruction_a_id: str
    instruction_b_id: str
    interaction_delta: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeadWeightItem:
    instruction_id: str
    token_cost: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunMeta:
    run_id: str
    subject_model: ModelRef
    suite_version: str
    suite_hash: str
    depth: str  # quick_scan | deep_audit
    seed: int
    n_runs: int
    judge_backend: JudgeBackendKind
    blend_config: BlendConfig
    reproducibility: Reproducibility = Reproducibility.GUARANTEED
    status: RunStatus = RunStatus.COMPLETE
    judge_model: ModelRef | None = None
    j_rescores: int = 1
    posterior_samples: int = 4000
    promptfoo_schema_ref: str = ""

    def validate(self) -> None:
        self.blend_config.validate()
        if self.judge_backend is JudgeBackendKind.ANTHROPIC_API and (
            self.reproducibility is not Reproducibility.BEST_EFFORT
        ):
            raise SchemaError(
                "runs using the anthropic-api judge must be marked reproducibility=best_effort"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "subject_model": self.subject_model.to_dict(),
            "judge_backend": self.judge_backend.value,
            "judge_model": self.judge_model.to_dict() if self.judge_model else None,
            "suite_version": self.suite_version,
            "suite_hash": self.suite_hash,
            "promptfoo_schema_ref": self.promptfoo_schema_ref,
            "depth": self.depth,
            "seed": self.seed,
            "N": self.n_runs,
            "J": self.j_rescores,
            "S": self.posterior_samples,
            "blend_config": self.blend_config.to_dict(),
            "reproducibility": self.reproducibility.value,
            "status": self.status.value,
        }


@dataclass
class Verdict:
    run: RunMeta
    noise_floor_headline_pct: float
    rows: list[ClassifiedRow]
    dead_weight: list[DeadWeightItem] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        """Enforce the report-schema.md guarantees. Raises SchemaError on breach."""
        self.run.validate()
        if self.run.status is not RunStatus.COMPLETE:
            raise SchemaError(
                f"verdict rendered from a {self.run.status.value} run; "
                "incomplete runs must not be presented as a finished verdict"
            )
        for row in self.rows:
            row.validate()
        # headline must match the fraction of rows in the noise-floor state
        if self.rows:
            noise = sum(1 for r in self.rows if r.weight.is_noise_floor)
            expected = round(100.0 * noise / len(self.rows), 1)
            if abs(expected - round(self.noise_floor_headline_pct, 1)) > 0.11:
                raise SchemaError(
                    f"headline {self.noise_floor_headline_pct}% disagrees with "
                    f"{noise}/{len(self.rows)} noise-floor rows ({expected}%)"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run": self.run.to_dict(),
            "noise_floor_headline_pct": self.noise_floor_headline_pct,
            "rows": [r.to_dict() for r in self.rows],
            "dead_weight": [d.to_dict() for d in self.dead_weight],
            "conflicts": [c.to_dict() for c in self.conflicts],
        }
