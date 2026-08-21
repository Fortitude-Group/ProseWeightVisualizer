"""Helpers to build controlled Verdict objects for diff/CI/store tests."""

from __future__ import annotations

from proseweight.report.schema import (
    BlendConfig,
    Classification,
    ClassifiedRow,
    DeadWeightItem,
    InstructionRow,
    JudgeBackendKind,
    ModelRef,
    RunMeta,
    Verdict,
    WeightScore,
)


def make_row(text: str, weight: float, pd: float = 0.99, label=None, token_cost: int = 10, offset: int = 0):
    if label is None:
        label = Classification.LOAD_BEARING if weight >= 67 else Classification.DECORATIVE
    if pd < 0.95:
        label = Classification.DECORATIVE
    return ClassifiedRow(
        instruction=InstructionRow(f"i{offset}", text, offset, offset + len(text), token_cost=token_cost),
        weight=WeightScore(f"i{offset}", weight, max(weight - 4, 0), min(weight + 4, 100), pd),
        label=label,
    )


def make_verdict(
    rows_spec: list[tuple[str, float, float]],
    model: str = "Qwen/Qwen2.5-1.5B-Instruct",
    suite_version: str = "1.0.0",
    suite_hash: str = "sha256:abc",
    blend_version: str = "1.0.0",
    run_id: str = "run",
) -> Verdict:
    rows = [make_row(t, w, pd, offset=i) for i, (t, w, pd) in enumerate(rows_spec)]
    dead = [DeadWeightItem(r.instruction.id, r.instruction.token_cost) for r in rows if r.weight.is_noise_floor]
    noise = sum(1 for r in rows if r.weight.is_noise_floor)
    pct = round(100.0 * noise / len(rows), 1) if rows else 0.0
    run = RunMeta(
        run_id=run_id,
        subject_model=ModelRef(model),
        suite_version=suite_version,
        suite_hash=suite_hash,
        depth="deep_audit",
        seed=1,
        n_runs=30,
        judge_backend=JudgeBackendKind.LOCAL_HF,
        blend_config=BlendConfig(config_version=blend_version),
    )
    v = Verdict(run, pct, rows, dead)
    v.validate()
    return v
