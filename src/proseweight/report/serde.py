"""Reconstruct schema objects from their ``to_dict`` form.

Lets a stored verdict be rehydrated for diff, CI, and export (US9/US12/US10).
Kept separate from ``schema.py`` so the frozen dataclasses stay declarative.
"""

from __future__ import annotations

from typing import Any

from proseweight.report.schema import (
    BlendConfig,
    Classification,
    ClassifiedRow,
    Conflict,
    DeadWeightItem,
    InstructionRow,
    JudgeBackendKind,
    ModelRef,
    Reproducibility,
    RunMeta,
    RunStatus,
    Verdict,
    WeightScore,
)


def _model(d: dict[str, Any]) -> ModelRef:
    return ModelRef(
        model_id=d["model_id"],
        revision=d.get("revision", "unpinned"),
        runtime=d.get("runtime", "cpu"),
        dtype=d.get("dtype", ""),
    )


def _blend(d: dict[str, Any]) -> BlendConfig:
    return BlendConfig(
        config_version=d.get("config_version", "1.0.0"),
        w_judge=d["w_judge"],
        w_prog=d["w_prog"],
        w_embed=d["w_embed"],
        embedding_ceiling=d.get("embedding_ceiling", 1.0),
        embedding_ceiling_calibrated_on=d.get("embedding_ceiling_calibrated_on", ""),
        judge_decoding=d.get("judge_decoding", {}),
    )


def _run(d: dict[str, Any]) -> RunMeta:
    jm = d.get("judge_model")
    return RunMeta(
        run_id=d["run_id"],
        subject_model=_model(d["subject_model"]),
        suite_version=d["suite_version"],
        suite_hash=d["suite_hash"],
        depth=d["depth"],
        seed=d["seed"],
        n_runs=d["N"],
        judge_backend=JudgeBackendKind(d["judge_backend"]),
        blend_config=_blend(d["blend_config"]),
        reproducibility=Reproducibility(d["reproducibility"]),
        status=RunStatus(d["status"]),
        judge_model=_model(jm) if jm else None,
        j_rescores=d.get("J", 1),
        posterior_samples=d.get("S", 4000),
        promptfoo_schema_ref=d.get("promptfoo_schema_ref", ""),
    )


def _row(d: dict[str, Any]) -> ClassifiedRow:
    i = d["instruction"]
    w = d["weight"]
    c = d["classification"]
    return ClassifiedRow(
        instruction=InstructionRow(
            id=i["id"],
            text=i["text"],
            start_offset=i["start_offset"],
            end_offset=i["end_offset"],
            block_type=i.get("block_type", "paragraph"),
            heading_path=i.get("heading_path", []),
            token_cost=i.get("token_cost", 0),
        ),
        weight=WeightScore(
            instruction_id=w["instruction_id"],
            weight=w["weight"],
            ci_low=w["ci_low"],
            ci_high=w["ci_high"],
            pd=w["pd"],
            component_ablation=w.get("component_ablation", 0.0),
            component_attention=w.get("component_attention", 0.0),
            component_paraphrase=w.get("component_paraphrase", 0.0),
            raw_delta_judge=w.get("raw_delta_judge", 0.0),
            raw_delta_prog=w.get("raw_delta_prog", 0.0),
            raw_delta_embed=w.get("raw_delta_embed", 0.0),
        ),
        label=Classification(c["label"]),
        contradicts_instruction_id=c.get("contradicts_instruction_id"),
    )


def verdict_from_dict(d: dict[str, Any]) -> Verdict:
    v = Verdict(
        run=_run(d["run"]),
        noise_floor_headline_pct=d["noise_floor_headline_pct"],
        rows=[_row(r) for r in d["rows"]],
        dead_weight=[DeadWeightItem(x["instruction_id"], x["token_cost"]) for x in d.get("dead_weight", [])],
        conflicts=[
            Conflict(c["instruction_a_id"], c["instruction_b_id"], c["interaction_delta"])
            for c in d.get("conflicts", [])
        ],
        schema_version=d.get("schema_version", "1.0.0"),
    )
    return v
