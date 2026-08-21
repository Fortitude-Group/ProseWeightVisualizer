"""Scan orchestration: assemble a validated Verdict from a MeasurementBundle.

Pipeline (research.md R1): per-signal posteriors -> composite -> cross-instruction
shrinkage -> 0-100 scale + credible interval + pd -> classification -> headline +
dead-weight. Deterministic given the seed; the model work is behind the backend.
"""

from __future__ import annotations

import numpy as np

from proseweight.engine.blend import SIGNAL_EMBED, SIGNAL_JUDGE, SIGNAL_PROG, blend_weights
from proseweight.engine.determinism import named_generator
from proseweight.report.schema import (
    BlendConfig,
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
from proseweight.stats.engine import (
    bayes_bootstrap_mean,
    beta_binomial_effect,
    composite_effect,
    empirical_bayes_shrink,
    hdi,
    probability_of_direction,
    scale_to_weight,
)
from proseweight.verdict.backend import MeasurementBundle
from proseweight.verdict.classify import classify


def _composite_for_instruction(m, weights, noise_sd, cfg: BlendConfig, s: int, seed: int):
    n_probes = len(m.pass_full)
    k_harm = int(np.sum(m.pass_full & ~m.pass_ablated))
    k_help = int(np.sum(~m.pass_full & m.pass_ablated))
    # normalise embed by the calibrated ceiling before it enters the posterior
    embed_norm = np.clip(m.delta_embed, 0.0, cfg.embedding_ceiling) / cfg.embedding_ceiling

    signals = {
        SIGNAL_JUDGE: bayes_bootstrap_mean(
            m.delta_judge, s, named_generator(seed, f"{m.instruction_id}:judge")
        ),
        SIGNAL_PROG: beta_binomial_effect(
            k_harm, k_help, n_probes, s, named_generator(seed, f"{m.instruction_id}:prog")
        ),
        SIGNAL_EMBED: bayes_bootstrap_mean(
            embed_norm, s, named_generator(seed, f"{m.instruction_id}:embed")
        ),
    }
    return composite_effect(signals, weights, noise_sd)


def run_verdict(
    source: str,
    segments,
    suite,
    cfg,
    bundle: MeasurementBundle,
    run_id: str = "run",
) -> Verdict:
    """Turn measured signals into a full, validated verdict."""
    blend = BlendConfig(
        w_judge=0.5,
        w_prog=0.3,
        w_embed=0.2,
        embedding_ceiling=bundle.extra.get("embedding_ceiling", 1.0),
        embedding_ceiling_calibrated_on=bundle.extra.get("ceiling_calibrated_on", ""),
    )
    weights = blend_weights(blend)
    s = cfg.posterior_samples

    seg_by_id = {seg.id: seg for seg in segments}
    composites = []
    for m in bundle.instructions:
        composites.append(_composite_for_instruction(m, weights, bundle.noise_sd, blend, s, cfg.seed))

    theta_hat = np.array([float(np.mean(c)) for c in composites])
    sigma2 = np.array([float(np.var(c)) + 1e-9 for c in composites])
    shrunk = empirical_bayes_shrink(theta_hat, sigma2)

    # Ceiling = composite effect of removing the WHOLE prompt (calibration), so a
    # single instruction's weight is a fraction of the whole-prompt effect.
    if bundle.calibration is not None:
        cal_composite = _composite_for_instruction(
            bundle.calibration, weights, bundle.noise_sd, blend, s, cfg.seed
        )
        ceiling = max(float(np.mean(cal_composite)), 1e-9)
    else:
        ceiling = max(bundle.ceiling, 1e-9)
    rows: list[ClassifiedRow] = []
    dead: list[DeadWeightItem] = []

    for idx, m in enumerate(bundle.instructions):
        rng = named_generator(cfg.seed, f"{m.instruction_id}:shrunk")
        draws = rng.normal(shrunk.theta[idx], np.sqrt(shrunk.var[idx]), s)
        pd = probability_of_direction(draws)
        weight = scale_to_weight(shrunk.theta[idx], ceiling)
        lo_raw, hi_raw = hdi(draws, 0.95)
        ci_lo = scale_to_weight(lo_raw, ceiling)
        ci_hi = scale_to_weight(hi_raw, ceiling)
        ci_lo = min(ci_lo, weight)
        ci_hi = max(ci_hi, weight)

        ws = WeightScore(
            instruction_id=m.instruction_id,
            weight=weight,
            ci_low=ci_lo,
            ci_high=ci_hi,
            pd=pd,
            component_ablation=float(np.mean(m.delta_judge)),
            component_attention=m.attention_prescreen,
            component_paraphrase=0.0,
            raw_delta_judge=float(np.mean(m.delta_judge)),
            raw_delta_prog=float(np.mean(m.pass_full != m.pass_ablated)),
            raw_delta_embed=float(np.mean(m.delta_embed)),
        )
        label, contra = classify(ws, m.contradicts_instruction_id)
        seg = seg_by_id.get(m.instruction_id)
        row_instr = InstructionRow(
            id=m.instruction_id,
            text=seg.text if seg else "",
            start_offset=seg.start_offset if seg else 0,
            end_offset=seg.end_offset if seg else 0,
            block_type=seg.block_type if seg else "paragraph",
            heading_path=seg.heading_path if seg else [],
            token_cost=m.token_cost,
        )
        rows.append(ClassifiedRow(row_instr, ws, label, contra))
        if ws.is_noise_floor:
            dead.append(DeadWeightItem(m.instruction_id, m.token_cost))

    rows.sort(key=lambda r: r.weight.weight, reverse=True)
    noise_pct = round(100.0 * sum(1 for r in rows if r.weight.is_noise_floor) / len(rows), 1) if rows else 0.0

    judge_backend = (
        JudgeBackendKind.ANTHROPIC_API if cfg.uses_api_judge else JudgeBackendKind.LOCAL_HF
    )
    best_effort = cfg.uses_api_judge or bool(bundle.extra.get("best_effort"))
    repro = Reproducibility.BEST_EFFORT if best_effort else Reproducibility.GUARANTEED
    run = RunMeta(
        run_id=run_id,
        subject_model=ModelRef(cfg.subject_model, runtime=bundle.runtime),
        suite_version=suite.version,
        suite_hash=suite.content_hash,
        depth=cfg.depth,
        seed=cfg.seed,
        n_runs=cfg.n_runs,
        judge_backend=judge_backend,
        blend_config=blend,
        reproducibility=repro,
        status=RunStatus.COMPLETE,
        promptfoo_schema_ref=suite.promptfoo_schema_ref,
    )

    conflicts = [
        Conflict(m.instruction_id, m.contradicts_instruction_id, float(np.mean(m.delta_judge)))
        for m in bundle.instructions
        if m.contradicts_instruction_id
    ]

    verdict = Verdict(run, noise_pct, rows, dead, conflicts)
    verdict.validate()
    return verdict
