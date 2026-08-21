# Phase 1 Data Model: Prompt Weight Linter

**Date**: 2026-08-20 | **Feature**: `001-prompt-weight-linter` | **Plan**: [plan.md](./plan.md)

Entities are the durable domain objects the engine produces, stores, and renders. All are serialisable to the versioned report schema (see [contracts/report-schema.md](./contracts/report-schema.md)). "Stored as" notes the on-disk home; everything is local files (single-tenant, no database). Field types are language-agnostic.

---

## Prompt

The text under test. May carry multiple versions (for diff mode).

| Field | Type | Notes |
|---|---|---|
| `id` | string | content-derived (hash), stable |
| `source_text` | string | the original, **immutable** pasted text — canonical truth for all offsets |
| `label` | string? | optional human name (e.g. filename, "Claude system prompt v3") |
| `version_tag` | string? | for diff mode: which version this is (e.g. "v1"/"v2") |

**Relationships**: decomposed into ordered `Instruction[]`. A `Diff` references two Prompts.

---

## Instruction (Segment)

A discrete, individually-editable unit of the prompt. Produced by segmentation; carries the measurement result.

| Field | Type | Notes |
|---|---|---|
| `id` | string | stable id for undo/audit |
| `start_offset`, `end_offset` | int | char offsets into `Prompt.source_text` — canonical for reconstruction |
| `text` | string | exact substring; recomputed-and-asserted from offsets on load, never independently hand-edited |
| `block_type` | enum | `heading \| paragraph \| list_item \| code_fence \| xml_block \| table_row \| blockquote \| front_matter \| thematic_break` |
| `block_level` | int | heading depth / list nesting depth |
| `parent_id` | string? | reconstructs hierarchy (clause → list item → list → section) |
| `order_index` | string | **fractional-index string** so a manual split slots between neighbours without renumbering |
| `source` | enum | `rule \| model \| manual` — boundary provenance; decides whether an edited segment is re-run through the model step |
| `is_atomic` | bool | true for `code_fence`/`xml_block`/`table_row` — never auto-split |
| `merged_from` / `split_from` | string[] | prior segment ids — undo/audit trail |
| `heading_path` | string[] | breadcrumb of enclosing headings — lint context + paraphrase prompting |
| `checksum` | string | hash of `text`; detects source drift under a cached segmentation |
| `confidence` | float? | from the model step; surfaces likely mis-splits for review |
| `token_cost` | int | tokens this instruction costs per call (for dead-weight framing) |

**Validation / invariants**:
- **Round-trip**: concatenating top-level non-overlapping segments in `order_index` order reproduces `Prompt.source_text` exactly (modulo tracked user edits). Asserted on every segmentation run.
- A run MUST NOT start on segmentation the user has not had the chance to review (FR-002).
- `is_atomic` segments are excluded from auto-split; expanding an `xml_block` interior is an explicit opt-in edit.

**Relationships**: each Instruction gets one `WeightScore` and one `Classification` per Run; may appear in `Conflict` pairs; has `Paraphrase[]`.

---

## Paraphrase

A same-intent rewording of an Instruction, for paraphrase-sensitivity.

| Field | Type | Notes |
|---|---|---|
| `instruction_id` | string | parent |
| `k` | int | index 0..K-1 |
| `strategy` | enum | rotating rewrite strategy (reorder / voice / synonym / imperative→conditional / length) |
| `text` | string | the paraphrase |
| `seed` | int | `hash(instruction_id)+k` — reproducible |
| `validation_failed` | bool | NLI/backstop intent check failed but kept (never silent-dropped) |

---

## ProbeTask

One small discriminating task. Authored as a promptfoo `tests[]` entry.

| Field | Type | Notes |
|---|---|---|
| `probe_id` | string | e.g. `P01` |
| `category` | enum | `deferral \| format \| tone \| refusal \| constraint \| unclassified` (BYO imports default to `unclassified`) |
| `input_vars` | object | promptfoo `vars` |
| `checks` | Check[] | each tagged signal type `PROG \| JUDGE \| EMB`, mapped to a promptfoo assert type |
| `rubric` | Rubric? | for JUDGE checks: criterion, 0–4 anchors, one high + one low worked example |
| `discrimination` | float? | suite-quality `D(p)` (populated from runs) |
| `snr` | float? | suite-quality `SNR(p)` |
| `quality_flag` | enum? | `null \| LOW_DISCRIMINATION \| SATURATED` |

**Rule** (FR-006c authoring requirement): every shipped probe MUST define at least a weak `PROG` check (non-empty / length band / parseable) so all three blend components are always populated.

---

## ProbeSuite

A versioned collection of ProbeTasks.

| Field | Type | Notes |
|---|---|---|
| `suite_version` | string | semver human label |
| `suite_hash` | string | `sha256:` over canonicalised YAML — the actual reproducibility guarantee |
| `promptfoo_schema_ref` | string | e.g. `0.122.0` |
| `probes` | ProbeTask[] | 10–15; shipped default or BYO |
| `origin` | enum | `shipped \| byo` |

**Guard**: a file tagged `vX` that doesn't hash-match the manifest (`suite-versions.json`) is refused, not silently attributed. **Stored as**: `data/suites/*.yaml` + append-only `data/suites/suite-versions.json`.

---

## Model

A model the prompt is measured against (subject), or a judge/embedder.

| Field | Type | Notes |
|---|---|---|
| `model_id` | string | e.g. `Qwen/Qwen2.5-1.5B-Instruct` |
| `revision` | string | exact HF commit SHA (reproducibility) |
| `role` | enum | `subject \| judge \| embedder \| segmenter \| paraphraser \| nli` |
| `runtime` | enum | `cuda \| cpu` — recorded per run (CPU degraded mode) |
| `dtype` / `quant` | string | e.g. `bf16`, `nf4-4bit` |

**Storage**: results are stored **per model** from R1 (anticipates the R2 grid).

---

## Run

One execution producing per-instruction results. The reproducibility unit.

| Field | Type | Notes |
|---|---|---|
| `run_id` | string | |
| `prompt_id` | string | |
| `subject_model` | Model | |
| `judge_backend` | enum | `local-hf \| anthropic-api` |
| `judge_model` | Model | |
| `suite_version` + `suite_hash` | string | scoping (FR-035) |
| `depth` | enum | `quick_scan \| deep_audit` |
| `seed` | int | |
| `N` | int | runs per condition |
| `J` | int | judge re-scores per output (noise isolation) |
| `S` | int | posterior sample count |
| `blend_config` | BlendConfig | versioned (weights, embedding ceiling, decoding) |
| `reproducibility` | enum | `guaranteed` (fully local) \| `best_effort` (API judge) |
| `status` | enum | `complete \| incomplete \| interrupted` — incomplete never rendered as a finished verdict |
| `cost_estimate` | object | shown before run starts (time, and API cost if applicable) |
| `null_condition` | object | full-prompt repeats characterising the noise floor |

**Relationships**: produces `WeightScore[]`, `Classification[]`, `Conflict[]`, and the headline. **Stored as**: `results/<model>/<run_id>/…` (JSON + columnar ablation matrix for deep audits).

---

## BlendConfig

The fixed, documented divergence blend — versioned so a change is a detectable confound.

| Field | Type | Notes |
|---|---|---|
| `config_version` | string | |
| `w_judge` / `w_prog` / `w_embed` | float | default 0.5 / 0.3 / 0.2 |
| `embedding_ceiling` | float | 95th-pct calibration from Gate A corpus |
| `embedding_ceiling_calibrated_on` | string | date/corpus id |
| `judge_decoding` | object | greedy / constrained-enum config |

---

## WeightScore

A per-instruction 0–100 behavioural weight with its Bayesian posterior.

| Field | Type | Notes |
|---|---|---|
| `instruction_id` | string | |
| `weight` | float | 0–100, `100·clip(θ_shrunk/ceiling,0,1)` |
| `ci_low` / `ci_high` | float | posterior credible interval (shrunk sample quantiles) |
| `pd` | float | probability of direction; `< 0.95` ⇒ noise floor |
| `component_ablation` | float | dominant signal (per-component transparency, FR-009) |
| `component_attention` | float | attention-mass pre-screen (explainer only, never a verdict) |
| `component_paraphrase` | float | paraphrase sensitivity |
| `raw_delta_judge` / `raw_delta_prog` / `raw_delta_embed` | float | pre-blend raw components (FR-034 transparency) |
| `is_noise_floor` | bool | `pd < 0.95` — rendered visually distinct from a low weight |

---

## Classification

The verdict label for an instruction.

| Field | Type | Notes |
|---|---|---|
| `instruction_id` | string | |
| `label` | enum | `load_bearing \| contributing \| decorative \| contradicted` |
| `contradicts_instruction_id` | string? | required when `label = contradicted`: the instruction whose compliance improves on ablation |

---

## Conflict

A pair of instructions that reduce each other's effect (candidate pairwise ablation).

| Field | Type | Notes |
|---|---|---|
| `instruction_a_id` / `instruction_b_id` | string | |
| `interaction_delta` | float | measured mutual reduction |

---

## Verdict (Report)

The rendered output of a Run — the headline + per-instruction rows + findings.

| Field | Type | Notes |
|---|---|---|
| `run` | Run | provenance |
| `noise_floor_headline_pct` | float | "N% of this prompt is below the noise floor" (FR-011) |
| `rows` | (Instruction, WeightScore, Classification)[] | ranked |
| `dead_weight` | (instruction_id, token_cost)[] | below-noise list with cost (FR-012) |
| `conflicts` | Conflict[] | |
| `schema_version` | string | versioned report contract |

**Exports**: self-contained HTML + PNG summary card (pure functions of the Verdict). **Never** rewrites prompt text (FR-014); the cut list is a report artefact only.

---

## Duel (R2)

| Field | Type | Notes |
|---|---|---|
| `phrasing_a` / `phrasing_b` | string | two phrasings of one instruction |
| `effect_size` | float | |
| `p_out_rope` | float | posterior P(|diff| > ROPE) |
| `verdict` | enum | `a_wins \| b_wins \| practically_equivalent \| inconclusive` |
| `rope_width` | float | `2·noise_floor_SD` (or domain SESOI) |

Sub-types reuse this shape: **EmphasisAudit** (variants = CAPS/bold/IMPORTANT/exclamation/repetition/list-position per model), **PositionSensitivity** (variants = prompt positions).

---

## Grid (R2)

Per-instruction weights across 3–4 subject models side by side. **Never** collapses to a single cross-model score (FR-027).

| Field | Type | Notes |
|---|---|---|
| `prompt_id` | string | |
| `models` | Model[] | 3–4 |
| `cells` | (instruction_id, model_id, WeightScore)[] | per-model, stored separately |

---

## Diff (R2)

| Field | Type | Notes |
|---|---|---|
| `prompt_v1_id` / `prompt_v2_id` | string | |
| `weight_changes` | (matched_instruction, delta_weight)[] | |
| `added` / `removed` | instruction[] | |
| `regressions` | instruction[] | previously load-bearing, weight dropped materially — flagged distinctly |
| `blend_config_changed` | bool | confound flag (differing BlendConfig between runs) |

---

## Baseline (R3, CI)

A stored weights file checked into the user's repo like a lockfile.

| Field | Type | Notes |
|---|---|---|
| `prompt_ref` | string | file the baseline is for |
| `weights` | (instruction, weight, ci)[] | frozen reference |
| `suite_version` + `suite_hash` + `model` + `blend_config` | — | scoping; a mismatch is flagged as a confound, not a regression |
| `load_bearing_threshold` | float | weight-drop that fails the build |
| `dead_weight_budget` | float | added dead weight that fails the build |

**Stored as**: JSON in the user's repo.

---

## DecayResult (R3)

| Field | Type | Notes |
|---|---|---|
| `instruction_id` | string | |
| `turns` | int[] | sampled conversation lengths (1, 5, 10, 20) |
| `compliance` | (turn, value, ci_low, ci_high)[] | per turn, with intervals |
| `filler_spec` | object | controlled synthetic filler description (avoids topical confound) |
| `model_id` | string | per model |

---

## Entity relationship summary

```text
Prompt 1─* Instruction 1─1 WeightScore
                     1─1 Classification
                     1─* Paraphrase
                     *─* Conflict
Run 1─* WeightScore/Classification/Conflict  →  Verdict ─(export)→ HTML + PNG
Run *─1 ProbeSuite (version+hash)   Run *─1 subject Model   Run *─1 BlendConfig
Duel/EmphasisAudit/PositionSensitivity  → reuse WeightScore machinery
Grid *─* Model (per-model cells, never merged)
Diff 2─1 Prompt   Baseline ─(CI compare)→ Run   DecayResult *─1 Model
```
