# Contract: Report / Verdict JSON Schema

**Stability**: public, SemVer'd. `schema_version` is stamped into every artefact; a breaking field change is a MAJOR bump with a migration note. This is the shared contract the CLI, web, API, export, and CI (diff/baseline) all read and write — one source of truth (Principle I/II).

## Verdict object (Release 1)

```jsonc
{
  "schema_version": "1.0.0",
  "run": {
    "run_id": "…",
    "prompt": { "id": "…", "label": "CLAUDE.md", "version_tag": null },
    "subject_model": { "model_id": "Qwen/Qwen2.5-1.5B-Instruct", "revision": "<sha>", "runtime": "cuda", "dtype": "bf16" },
    "judge_backend": "local-hf",
    "judge_model": { "model_id": "meta-llama/Llama-3.1-8B-Instruct", "revision": "<sha>", "quant": "nf4-4bit" },
    "suite_version": "1.3.0",
    "suite_hash": "sha256:…",
    "promptfoo_schema_ref": "0.122.0",
    "depth": "deep_audit",
    "seed": 42,
    "N": 30, "J": 5, "S": 4000,
    "blend_config": {
      "config_version": "1.0.0",
      "w_judge": 0.5, "w_prog": 0.3, "w_embed": 0.2,
      "embedding_ceiling": 0.71, "embedding_ceiling_calibrated_on": "gateA-2026-08",
      "judge_decoding": { "mode": "greedy", "constrained_enum": [0,1,2,3,4] }
    },
    "reproducibility": "guaranteed",
    "status": "complete"
  },
  "noise_floor_headline_pct": 34.0,
  "rows": [
    {
      "instruction": {
        "id": "i7", "start_offset": 812, "end_offset": 861,
        "text": "Never defer; attempt the fix directly.",
        "block_type": "list_item", "heading_path": ["Behaviour"], "token_cost": 9
      },
      "weight": { "weight": 92.0, "ci_low": 88.0, "ci_high": 95.0, "pd": 0.999,
        "component_ablation": 0.81, "component_attention": 0.44, "component_paraphrase": 0.20,
        "raw_delta_judge": 0.75, "raw_delta_prog": 0.66, "raw_delta_embed": 0.41,
        "is_noise_floor": false },
      "classification": { "label": "load_bearing", "contradicts_instruction_id": null }
    }
  ],
  "dead_weight": [ { "instruction_id": "i3", "token_cost": 14 } ],
  "conflicts": [ { "instruction_a_id": "i5", "instruction_b_id": "i9", "interaction_delta": 0.22 } ]
}
```

### Guarantees (tested as contract tests)

- Every `weight` object carries `ci_low`/`ci_high` and `pd` (SC-004); no score ships without an interval (FR-018).
- `is_noise_floor` is true iff `pd < 0.95`; renderers MUST show it distinctly from a low weight (FR-016).
- `classification.label == "contradicted"` REQUIRES a non-null `contradicts_instruction_id` (FR-010).
- `component_attention` is present for transparency but is NEVER the basis of `weight` or `label` (FR-007); a renderer that surfaces it does so only under "how it works".
- `run` always carries `suite_version`+`suite_hash`+`subject_model` (scoping, FR-035) and `reproducibility` (`best_effort` whenever `judge_backend == "anthropic-api"`, FR-006b).
- `status == "incomplete"|"interrupted"` MUST NOT be rendered as a finished verdict.

## Duel / Grid / Diff / Decay objects (Release 2/3)

Each is its own top-level object sharing `schema_version`, the `run` provenance block, and the `WeightScore` shape:

- **Duel**: `{ phrasing_a, phrasing_b, effect_size, p_out_rope, verdict: a_wins|b_wins|practically_equivalent|inconclusive, rope_width }`. `verdict` is a win only when `p_out_rope > threshold` (FR-024/SC-009). EmphasisAudit and PositionSensitivity are Duel objects with a `variants[]` array.
- **Grid**: `{ models[], cells: [{instruction_id, model_id, weight}] }` — per-model cells, never a merged score (FR-027).
- **Diff**: `{ prompt_v1, prompt_v2, weight_changes[], added[], removed[], regressions[], blend_config_changed }` (FR-028).
- **Decay**: `{ instruction_id, model_id, compliance: [{turn, value, ci_low, ci_high}], filler_spec }` (FR-030).

## Baseline object (CI)

```jsonc
{
  "schema_version": "1.0.0",
  "prompt_ref": "CLAUDE.md",
  "scoping": { "suite_version": "1.3.0", "suite_hash": "sha256:…",
               "subject_model": "…@<sha>", "blend_config_version": "1.0.0" },
  "thresholds": { "load_bearing_drop": 15.0, "dead_weight_budget_tokens": 40 },
  "weights": [ { "instruction": "…", "weight": 92.0, "ci_low": 88.0, "ci_high": 95.0 } ]
}
```
`lint` compares a fresh run against this; a `scoping` mismatch → exit 3 (confound), not a regression.
