"""Contract tests for the report schema (contracts/report-schema.md)."""

from __future__ import annotations

import pytest

from proseweight.report.schema import (
    BlendConfig,
    Classification,
    ClassifiedRow,
    InstructionRow,
    JudgeBackendKind,
    ModelRef,
    Reproducibility,
    RunMeta,
    RunStatus,
    SchemaError,
    Verdict,
    WeightScore,
)


def _run(**over) -> RunMeta:
    kw = dict(
        run_id="r1",
        subject_model=ModelRef("Qwen/Qwen2.5-1.5B-Instruct", "sha", "cpu"),
        suite_version="1.0.0",
        suite_hash="sha256:abc",
        depth="deep_audit",
        seed=42,
        n_runs=30,
        judge_backend=JudgeBackendKind.LOCAL_HF,
        blend_config=BlendConfig(),
    )
    kw.update(over)
    return RunMeta(**kw)


def _row(iid: str, weight: float, pd: float, label=Classification.CONTRIBUTING, contra=None):
    return ClassifiedRow(
        instruction=InstructionRow(iid, "text", 0, 4),
        weight=WeightScore(iid, weight, weight - 3, weight + 3, pd),
        label=label,
        contradicts_instruction_id=contra,
    )


def test_every_weight_has_interval_and_pd():
    w = WeightScore("i0", 50.0, 45.0, 55.0, 0.99)
    w.validate()
    assert w.ci_low <= w.weight <= w.ci_high


def test_weight_outside_ci_rejected():
    with pytest.raises(SchemaError):
        WeightScore("i0", 90.0, 45.0, 55.0, 0.99).validate()


def test_noise_floor_flag_matches_pd():
    assert WeightScore("i0", 3.0, 0.0, 9.0, 0.80).is_noise_floor is True
    assert WeightScore("i0", 3.0, 0.0, 9.0, 0.99).is_noise_floor is False


def test_contradicted_requires_target():
    good = _row("i1", 80, 0.99, Classification.CONTRADICTED, contra="i2")
    good.validate()
    with pytest.raises(SchemaError):
        _row("i1", 80, 0.99, Classification.CONTRADICTED).validate()


def test_api_judge_forces_best_effort():
    with pytest.raises(SchemaError):
        _run(judge_backend=JudgeBackendKind.ANTHROPIC_API).validate()
    _run(
        judge_backend=JudgeBackendKind.ANTHROPIC_API,
        reproducibility=Reproducibility.BEST_EFFORT,
    ).validate()


def test_incomplete_run_never_a_verdict():
    v = Verdict(_run(status=RunStatus.INCOMPLETE), 0.0, [_row("i0", 50, 0.99)])
    with pytest.raises(SchemaError):
        v.validate()


def test_headline_must_match_noise_rows():
    rows = [_row("i0", 90, 0.99), _row("i1", 3, 0.80)]  # one noise-floor of two = 50%
    Verdict(_run(), 50.0, rows).validate()
    with pytest.raises(SchemaError):
        Verdict(_run(), 0.0, rows).validate()


def test_blend_weights_must_sum_to_one():
    with pytest.raises(SchemaError):
        BlendConfig(w_judge=0.5, w_prog=0.5, w_embed=0.5).validate()


def test_verdict_roundtrips_to_dict():
    v = Verdict(_run(), 50.0, [_row("i0", 90, 0.99), _row("i1", 3, 0.80)])
    v.validate()
    d = v.to_dict()
    assert d["schema_version"] == "1.0.0"
    assert d["rows"][0]["weight"]["is_noise_floor"] is False
    assert d["run"]["reproducibility"] == "guaranteed"
