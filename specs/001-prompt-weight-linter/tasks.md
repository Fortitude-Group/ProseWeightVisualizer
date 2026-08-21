---
description: "Task list for Prompt Weight Linter (Prose Weight Visualiser)"
---

# Tasks: Prompt Weight Linter (Prose Weight Visualiser)

**Input**: Design documents from `specs/001-prompt-weight-linter/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Included. The constitution (Principle III) requires comprehensive coverage of public contracts at merge, and the spec makes the honesty kill-criteria (Gate A instrument validity, Gate B reproducibility, Gate C flagship publication) non-negotiable executable checks. Test-first ordering is encouraged but not mandated.

**Organization**: Tasks are grouped by user story. Priorities map to releases — P1 = Release 1, P2 = Release 2, P3 = Release 3. The shared measurement engine is Foundational (blocks every story). MVP = User Story 1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US14 for story-phase tasks; Setup/Foundational/Polish carry no story label
- All paths are relative to repo root and follow the structure in [plan.md](./plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton, packaging, and absorbing the predecessor.

- [X] T001 Create the source tree per plan.md: `src/proseweight/{segmentation,probes,models,engine,judge,stats,verdict,duel,grid,diff,decay,report,ci,api,web,cli,methodology}/` with `__init__.py`, plus `tests/{unit,integration,contract,gates}/` and `data/{suites,teardowns,fixtures}/`
- [X] T002 Author `pyproject.toml` for single-command install (`pip install -e .`) with the pinned dependencies from research.md, and a `proseweight` console-script entry point
- [X] T003 [P] Configure ruff + formatter + `pytest.ini`/`pyproject` test config, and a `scripts/build-test.ps1` single-entry wrapper (restore/lint/test)
- [ ] T004 [P] Add the checked-in OFL font (Inter or IBM Plex Sans) + its licence to `src/proseweight/report/assets/fonts/`
- [X] T005 [P] Port the predecessor as the token-level core: `prose_weight_visualiser.py::get_model` (bf16-on-CUDA, eager attention, one-model cache) into `src/proseweight/models/loader.py`, and `ablation_scores` + attention extraction into `src/proseweight/engine/token_core.py` (adapt, keep the numerics)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared measurement engine every user story consumes. No story work begins until this phase is complete.

**⚠️ CRITICAL**: All of Phase 2 blocks all user stories.

### Core plumbing

- [X] T006 [P] Implement deterministic RNG + run-metadata infrastructure in `src/proseweight/engine/determinism.py` (`SeedSequence(cfg.seed).spawn(...)`, `Generator` threading, run-metadata record capturing seed/S/J/N/blend_config/suite/model/revision/reproducibility per data-model.md)
- [X] T007 [P] Implement structured logging + telemetry and config management in `src/proseweight/config.py` and `src/proseweight/logging.py` (Principle IV observability; `ANTHROPIC_API_KEY` read from env only, never logged)
- [X] T008 Implement the model abstraction, loaders, and per-model result storage in `src/proseweight/models/` (subject/judge/embedder/segmenter/paraphraser/nli roles; CUDA/CPU selection recorded; results tree `results/<model>/<run_id>/…`) — depends on T005

### Report schema (contract)

- [X] T009 [P] Implement the versioned report/verdict schema + validation in `src/proseweight/report/schema.py` per [contracts/report-schema.md](./contracts/report-schema.md) (Verdict, Duel, Grid, Diff, Decay, Baseline objects; `schema_version`)
- [X] T010 [P] Contract test for the report schema in `tests/contract/test_report_schema.py` (every weight has CI+pd; contradicted requires target id; incomplete never a finished verdict; scoping+reproducibility always present)

### Segmentation

- [X] T011 [P] Implement the segment data model + round-trip invariant in `src/proseweight/segmentation/model.py` (fields per data-model.md; assert concatenation reproduces source)
- [X] T012 [US-shared] Implement segmentation pipeline in `src/proseweight/segmentation/pipeline.py`: markdown-it-py AST + line→offset index, XML-tag pre-pass (atomic `xml_block`), pysbd sentence split, grammar-constrained Qwen2.5-1.5B split-index step, merge/split API, caching — depends on T008, T011
- [X] T013 [P] Unit tests for segmentation in `tests/unit/test_segmentation.py` (round-trip invariant, atomic code-fence/xml handling, compound-directive split, merge/split)

### Probe suite

- [X] T014 [P] Implement probe-suite loader, promptfoo-format mapping, and the semver+sha256 hash guard in `src/proseweight/probes/suite.py` per [contracts/probe-suite.md](./contracts/probe-suite.md)
- [X] T015 [P] Author the shipped default suite v1 (12 probes) in `data/suites/default-v1.yaml` + `data/suites/suite-versions.json` manifest (inputs, PROG/JUDGE/EMB checks, rubric anchors; every probe has ≥1 weak PROG check)
- [X] T016 [P] Implement suite self-quality (probe-axis pivot: `D(p)`, `SNR`, LOW_DISCRIMINATION/SATURATED flags) in `src/proseweight/probes/quality.py`
- [X] T017 [P] Contract test for suite format + hash guard in `tests/contract/test_suite_format.py` (BYO import classifies signal types; mismatched hash is refused)

### Signals

- [ ] T018 [P] Implement the embedding-distance signal (bge-small-en-v1.5 @ pinned SHA, `1−cos_sim`, ceiling calibration hook) in `src/proseweight/engine/embedding.py`
- [ ] T019 [P] Implement the `JudgeBackend` protocol + `LocalHFJudge` (Llama-3.1-8B 4-bit @ pinned SHA, grammar-constrained 0–4, independent scoring of full vs ablated) in `src/proseweight/judge/backend.py` and `judge/local.py`
- [X] T020 [US-shared] Implement judge-noise isolation (M-repeat `σ_judge²`) + a CI gate that fails if local greedy noise isn't near-zero, in `src/proseweight/judge/noise.py` — depends on T019
- [X] T020a [US-shared] Implement the opt-in frontier `AnthropicAPIJudge` backend (FR-006b) in `src/proseweight/judge/api.py`: `claude-haiku-4-5` via forced structured output `{reasoning, score}`, key from `ANTHROPIC_API_KEY` env only (never a request/config field), SDK retry/backoff, and its own M-repeat `σ_judge²` measurement; when selected, set the run's `reproducibility: "best_effort"` flag and record `judge_backend: "anthropic-api"` (waiving SC-002 for that run) — depends on T019
- [ ] T021 [US-shared] Implement instruction-level ablation + attention pre-screen aggregation in `src/proseweight/engine/ablation.py` (aggregate the token-core over segments; attention ranks candidates, never verdicts) — depends on T005, T012
- [ ] T022 [P] Implement paraphrase generation + NLI intent gate + negation/modal backstop in `src/proseweight/engine/paraphrase.py`

### Statistics + blend

- [X] T023 [P] Implement the Bayesian stats engine in `src/proseweight/stats/engine.py` (Beta-Binomial, Bayesian bootstrap, composite propagation, empirical-Bayes shrinkage, noise-floor `pd`, 0–100 calibration, ROPE) per research.md — numpy/scipy only
- [X] T024 [P] Unit tests for the stats engine in `tests/unit/test_stats.py` (determinism under seed, noise-floor detection on planted no-ops, shrinkage behaviour, ROPE decisions)
- [X] T025 [US-shared] Implement the fixed divergence blend + versioned `blend_config` in `src/proseweight/engine/blend.py` (0.5/0.3/0.2, per-signal normalization, no renormalize-on-missing path, full component transparency) — depends on T018, T019, T023

### Gate harness scaffolding

- [X] T026 [P] Author Gate A planted-ground-truth fixtures in `data/fixtures/planted-ground-truth.md` (known load-bearing instructions the probes test + planted no-ops) and the gate harness scaffold in `tests/gates/`
- [X] T026a [US-shared] Compute and **freeze** the embedding-distance ceiling (95th percentile of pairwise distances over the Gate A corpus) into the versioned `blend_config` in `src/proseweight/engine/blend.py`, with the calibration date recorded — so the [0,1] embedding normalization is fixed, not silently re-derived per run — depends on T018, T025, T026

**Checkpoint**: The engine can segment, ablate, judge, score with intervals, and classify noise — user stories can now begin.

---

## Phase 3: User Story 1 - Verdict report for a pasted prompt (Priority: P1) 🎯 MVP

**Goal**: Paste a prompt → reviewed segmentation → run config → live progress → ranked verdict with weights, four-way classification, and credible intervals, leading with the noise-floor headline.

**Independent Test**: Run a deep audit on a mixed prompt (load-bearing + inert filler); load-bearing ranks above filler, filler lands in the noise-floor state, every score shows an interval and its suite/model scoping.

### Tests for User Story 1

- [ ] T027 [P] [US1] Gate A instrument-validity test in `tests/gates/test_gate_a.py` (planted load-bearing ranked above all no-ops, no-ops in noise floor, ≥90% of deep-audit runs)
- [ ] T028 [P] [US1] Gate B reproducibility test in `tests/gates/test_gate_b.py` (same seed → identical verdict; different seeds → ≥85% classification agreement, disagreements interval-overlapping)
- [X] T029 [P] [US1] Integration test for the scan journey in `tests/integration/test_scan_verdict.py`

### Implementation for User Story 1

- [X] T030 [US1] Implement scan orchestration (quick scan = attention pre-screen + top-candidate ablation; deep audit = full matrix × N; null-condition run) in `src/proseweight/verdict/orchestrator.py` — depends on T021, T023, T025
- [X] T031 [P] [US1] Implement weight assembly + per-component transparency (ablation/attention/paraphrase + raw judge/prog/embed) in `src/proseweight/verdict/weights.py`
- [X] T032 [P] [US1] Implement four-way classification incl. single-ablation "contradicted" detection (names the conflicting instruction) in `src/proseweight/verdict/classify.py`
- [X] T033 [P] [US1] Implement the noise-floor headline ("N% below the noise floor") and dead-weight framing in `src/proseweight/verdict/headline.py`
- [X] T034 [US1] Implement tiered-depth control with a pre-run time/cost estimate and CPU-fallback recording in `src/proseweight/verdict/runconfig.py`
- [X] T035 [P] [US1] Implement the inline-SVG chart builder (weight bars + CI whiskers, one float formatter, content-derived ids) in `src/proseweight/report/svg_charts.py`
- [X] T036 [US1] Implement the verdict Jinja2 view + CSS-only tabs with attention demoted to "how it works" in `src/proseweight/report/templates/verdict.html.jinja` and `report/render.py` — depends on T035
- [ ] T037 [US1] Implement the web flow (paste → segment review gate → configure → live progress → verdict) in `src/proseweight/web/app.py` (Gradio); a run cannot start on unreviewed segmentation — depends on T036

**Checkpoint**: User Story 1 is fully functional and independently testable — the MVP verdict.

---

## Phase 4: User Story 2 - Dead-weight and conflict findings (Priority: P1)

**Goal**: From the same run, an actionable cut list (below-noise instructions + token cost) and mutually-reducing instruction pairs.

**Independent Test**: A prompt with planted dead sentences and a contradictory pair yields the dead sentences in the cut list with token cost and the pair surfaced as a conflict — no rewrite.

### Tests for User Story 2

- [ ] T038 [P] [US2] Integration test in `tests/integration/test_dead_weight_conflict.py` (planted dead sentences + contradictory pair)

### Implementation for User Story 2

- [X] T039 [P] [US2] Implement the dead-weight cut list (below-noise + token cost per call) in `src/proseweight/verdict/dead_weight.py`
- [X] T040 [US2] Implement candidate pairwise ablation → conflict detection in `src/proseweight/verdict/conflict.py` (candidates flagged by the single-ablation pass only) — depends on T021, T032
- [X] T041 [US2] Wire dead-weight + conflicts into the verdict report and enforce the no-rewrite guarantee (cut list is an artefact) in `src/proseweight/verdict/orchestrator.py`

**Checkpoint**: US1 + US2 both work independently.

---

## Phase 5: User Story 3 - Famous-prompt teardowns, pre-loaded (Priority: P1)

**Goal**: A first-time visitor reads full verdicts on recognisable published prompts with no run started.

**Independent Test**: Load the read-only demo with no run; ≥2 teardowns of published, source-cited prompts render in full with weights, classifications, intervals, and scoping.

### Tests for User Story 3

- [ ] T042 [P] [US3] Test that pre-computed teardown reports validate against the report schema and cite a source, in `tests/integration/test_teardowns.py`

### Implementation for User Story 3

- [ ] T043 [US3] Pre-compute ≥2 teardown reports (published Claude system prompt + one other public prompt) into `data/teardowns/` with source citations — depends on T030
- [ ] T044 [US3] Implement read-only teardown rendering in the web surface (no execution, no GPU worker) in `src/proseweight/web/teardowns.py` — depends on T036, T043

**Checkpoint**: US1–US3 independently functional.

---

## Phase 6: User Story 4 - Command-line scan (Priority: P1)

**Goal**: `proseweight scan <file>` produces the same verdict as web, as JSON + terminal summary.

**Independent Test**: CLI JSON verdict matches the web verdict for the same prompt/settings/seed; terminal summary shows the same headline, suite version, and model.

### Tests for User Story 4

- [ ] T045 [P] [US4] CLI/web parity test in `tests/integration/test_cli_parity.py`
- [X] T046 [P] [US4] Contract test for the CLI surface (commands, flags, exit codes) in `tests/contract/test_cli.py`

### Implementation for User Story 4

- [X] T047 [US4] Implement the CLI app + `scan` command (Typer/Click) → JSON (`--json`) + terminal summary, `--segments` review gate, per [contracts/cli.md](./contracts/cli.md) in `src/proseweight/cli/main.py` — depends on T030
- [X] T048 [P] [US4] Implement the stable terminal-summary formatter (ranked columns, `◊` noise marker) in `src/proseweight/cli/render.py`

**Checkpoint**: Release 1 complete — verdict + dead-weight/conflict + teardowns + CLI.

---

## Phase 7: User Story 5 - Phrasing duel (Priority: P2)

**Goal**: A/B two phrasings of one instruction with ROPE significance and side-by-side attention, exportable.

**Independent Test**: Duelling two phrasings known to differ names a winner only when `P(|diff|>ROPE)` clears the threshold; reports effect size + posterior in every case; exports a shareable artefact.

### Tests for User Story 5

- [X] T049 [P] [US5] Integration test in `tests/integration/test_duel.py` (winner only past ROPE; null result reported, not a winner)

### Implementation for User Story 5

- [X] T050 [US5] Implement duel orchestration (paired probe runs, `composite_A−composite_B`, ROPE decision) in `src/proseweight/duel/duel.py` — depends on T023, T025
- [ ] T051 [P] [US5] Implement side-by-side attention heatmap view + `duel` CLI command in `src/proseweight/duel/render.py` and `cli/main.py`

**Checkpoint**: US5 independently functional.

---

## Phase 8: User Story 6 - Emphasis audit (Priority: P2)

**Goal**: Auto-generate emphasis variants (CAPS/bold/IMPORTANT/exclamation/repetition/list-position) and report which devices move weight, per model.

**Independent Test**: Each device is measured as its own variant; the report states, per device and model, whether it moved weight beyond the noise floor.

- [X] T052 [P] [US6] Integration test in `tests/integration/test_emphasis.py`
- [X] T053 [US6] Implement emphasis-variant generation + matrix run (reuses duel machinery) in `src/proseweight/duel/emphasis.py` — depends on T050

**Checkpoint**: US6 independently functional.

---

## Phase 9: User Story 7 - Position sensitivity (Priority: P2)

**Goal**: Move an instruction through prompt positions and re-measure weight per position, per model.

**Independent Test**: A weight with interval is reported for each position; positions shown side by side for the same model.

- [X] T054 [P] [US7] Integration test in `tests/integration/test_position.py`
- [X] T055 [US7] Implement position-sweep measurement in `src/proseweight/duel/position.py` (+ `position` CLI command) — depends on T021, T023

**Checkpoint**: US7 independently functional.

---

## Phase 10: User Story 8 - Model comparison grid (Priority: P2)

**Goal**: One prompt across 3–4 local models, per-instruction weights side by side, never a single cross-model score.

**Independent Test**: Each instruction's weight is shown per model; no universal score is produced.

- [X] T056 [P] [US8] Integration test in `tests/integration/test_grid.py` (no universal score emitted)
- [X] T057 [US8] Implement the grid orchestration + per-model cell storage + `grid` CLI command in `src/proseweight/grid/grid.py` — depends on T008, T030

**Checkpoint**: US8 independently functional.

---

## Phase 11: User Story 9 - Prompt diff (Priority: P2)

**Goal**: Diff v1 vs v2 — weight deltas, added/removed instructions, flagged regressions of previously load-bearing lines.

**Independent Test**: Diffing a prompt vs an edited copy with a weakened load-bearing instruction flags that regression and lists added/removed instructions.

- [X] T058 [P] [US9] Integration test in `tests/integration/test_diff.py`
- [X] T059 [US9] Implement diff (instruction matching, weight deltas, regression flag, `blend_config_changed` confound flag) + `diff` CLI command in `src/proseweight/diff/diff.py`; a previously load-bearing instruction is flagged as a regression when its weight drops beyond the shared `load_bearing_drop` threshold (same one CI mode uses, FR-031) — configurable, default documented — depends on T030

**Checkpoint**: US9 independently functional.

---

## Phase 12: User Story 10 - Shareable report export (Priority: P2)

**Goal**: Export any verdict/duel/diff as a self-contained HTML page (no server) + a compact PNG summary card.

**Independent Test**: Export a verdict; open the HTML with no server running → renders fully; a PNG card is produced.

### Tests for User Story 10

- [X] T060 [P] [US10] Golden/snapshot tests in `tests/unit/test_export.py` (self-contained HTML determinism; PNG golden on decoded pixels; HTML size budget for N=100)

### Implementation for User Story 10

- [X] T061 [US10] Implement self-contained HTML export (inline all CSS/SVG, injectable timestamp, content-derived ids) in `src/proseweight/report/export_html.py` — depends on T035, T036
- [X] T062 [P] [US10] Implement the deterministic Pillow PNG summary card (checked-in font, no metadata chunks) in `src/proseweight/report/png_card.py` — depends on T004
- [X] T063 [US10] Wire `export` CLI command and duel/diff export in `src/proseweight/cli/main.py`

**Checkpoint**: Release 2 complete — duels, emphasis, position, grid, diff, export.

---

## Phase 13: User Story 11 - Decay curve (Priority: P3)

**Goal**: Sample instruction compliance at growing conversation lengths (turns 1/5/10/20) against controlled filler, per instruction and model (deep-audit only).

**Independent Test**: Compliance reported at each sampled turn with intervals; filler held controlled across turns.

- [ ] T064 [P] [US11] Integration test in `tests/integration/test_decay.py`
- [ ] T065 [US11] Implement decay measurement + controlled synthetic filler in `src/proseweight/decay/decay.py` — depends on T021, T023
- [ ] T066 [US11] Implement decay-curve line charts with confidence bands (matplotlib/Agg, deterministic) in `src/proseweight/decay/render.py`

**Checkpoint**: US11 independently functional.

---

## Phase 14: User Story 12 - CI mode (Priority: P3)

**Goal**: `proseweight lint <file> --baseline weights.json` fails the build on load-bearing regressions or dead-weight budget breaches; a GitHub Action wraps it.

**Independent Test**: An edit weakening a load-bearing instruction past threshold → non-zero exit + named regression; a benign edit → zero; a scoping mismatch → exit 3.

### Tests for User Story 12

- [X] T067 [P] [US12] Integration test for exit codes in `tests/integration/test_ci_lint.py` (regression=1, dead-weight budget=1, benign=0, scoping confound=3)

### Implementation for User Story 12

- [X] T068 [US12] Implement baseline compare + exit-code logic + `--update-baseline` in `src/proseweight/ci/lint.py` — depends on T059, T009
- [X] T069 [P] [US12] Author the GitHub Action wrapper in `src/proseweight/ci/action/` (+ `action.yml`)

**Checkpoint**: US12 independently functional.

---

## Phase 15: User Story 13 - Watch mode / local API (Priority: P3)

**Goal**: A local daemon exposes a small HTTP API so an editor/agent can query weights while editing.

**Independent Test**: Start the daemon; query an instruction's weight via the API → weight, components, interval returned.

### Tests for User Story 13

- [X] T070 [P] [US13] Contract test for the API in `tests/contract/test_api.py` per [contracts/api.md](./contracts/api.md) (health, segment, weight, scan, runs; key never in body)

### Implementation for User Story 13

- [X] T071 [US13] Implement the FastAPI daemon (health/segment/weight/scan/runs[/events]) + `serve` CLI command in `src/proseweight/api/server.py` — depends on T030, T009

**Checkpoint**: US13 independently functional.

---

## Phase 16: User Story 14 - Public methodology page (Priority: P3)

**Goal**: A published methodology describing how weights are computed, what they do and don't mean, the ablation-over-attention ordering, and known limitations.

**Independent Test**: The page exists and states the weight computation, the ablation-led ordering, and known limitations.

- [X] T072 [US14] Write the methodology page in `docs/methodology.md` (weight computation, Bayesian intervals + noise floor, ablation-over-attention ordering, suite/model scoping, embedder-truncation and API-judge caveats, known limitations) — depends on the R1–R3 mechanics

**Checkpoint**: All user stories independently functional.

---

## Phase 17: Polish & Cross-Cutting Concerns

- [ ] T073 [P] Complete comprehensive unit coverage of public contracts + edge cases (interrupted run, all-below-noise, interval-overlapping ties, empty prompt) in `tests/unit/`
- [ ] T074 [P] Enforce the ablation-led ordering structurally on every surface (web, CLI, export, methodology) — audit + test in `tests/integration/test_ablation_led_ordering.py`
- [ ] T074a [P] Enforce the no-jailbreak/no-bypass guardrail (FR-036): audit every public surface and marketing/methodology copy so duel mode reads as comparing legitimate-instruction phrasings and no copy implies bypass-finding — assertion test in `tests/integration/test_no_bypass_copy.py`
- [ ] T075 [US5] Run and publish the flagship BOIL-vs-beige duel with full data regardless of outcome (Gate C, SC-012) as the Release 2 article in `docs/` — depends on T050
- [ ] T076 [P] Add the HTML export size-budget regression guard and PNG determinism guard to CI
- [ ] T077 Run `npx @claude-flow/cli@latest security scan` and address findings; confirm no secrets/keys in source (API key env-only)
- [ ] T078 Execute `quickstart.md` end-to-end (all 7 R1 scenarios + R2/R3 spot-checks) and record results
- [ ] T079 Mirror the task list to the ADO board (project ProseWeightVisualizer): Epic → Feature (per release) → Story (US1–US14) → Task, and link commits by hash (Principle VII)
- [ ] T080 [P] Cost-sanity performance gate (SC-003): benchmark a quick scan of a representative 50-instruction prompt on a single consumer GPU and assert completion in ≤10 minutes (fail loudly otherwise, prompting a probe-suite or pre-screen-threshold trim) in `tests/gates/test_cost_sanity.py`

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)** → no dependencies.
- **Foundational (P2)** → depends on Setup; **blocks all user stories**.
- **User Stories (P3+)** → all depend on Foundational. Within Release 1, US1 is the MVP; US2/US3/US4 build on US1's orchestration (T030) but are independently testable. Releases are shipping order, not hard walls.
- **Polish (P17)** → depends on the targeted stories being complete.

### Critical path (MVP)

Setup → Foundational (T006–T026) → US1 (T027–T037). This is the smallest shippable, honest verdict.

### Story dependencies (beyond Foundational)

- US2, US3, US4 consume US1's orchestrator (T030). US3 also needs a computed teardown (T043←T030). US4 is parity with US1.
- US5 (duel) is consumed by US6 (emphasis, T053←T050) and the Gate C article (T075←T050).
- US10 (export) generalises the US1 renderer (T035/T036); US12 (CI) consumes US9 diff (T068←T059); US13 (API) and US11 (decay) consume the orchestrator/stats.

### Parallel opportunities

- Setup: T003, T004, T005 in parallel.
- Foundational: the `[P]` tasks split cleanly by subpackage — **T009/T010 (report schema), T011/T013 (segmentation model+tests), T014–T017 (probes), T018 (embedding), T022 (paraphrase), T023/T024 (stats), T026 (gate fixtures)** are independent workstreams once T006–T008 land. T012, T020, T020a, T021, T025, T026a are the join points (T020a needs T019; T026a needs T018+T025+T026).
- US1: T027/T028/T029 (tests) parallel; T031/T032/T033/T035 parallel before T036/T037.
- Across stories: once Foundational is done, US1→US4 (R1), then US5→US10 (R2), then US11→US14 (R3) — and within a release the `[P]` test tasks and independent modules fan out.

---

## Implementation Strategy

### MVP first (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational (the engine — the bulk of the work) → 3. Phase 3 US1 → **STOP and VALIDATE** against Gate A + Gate B + the quickstart scan scenario. This is a defensible, honest verdict tool on its own.

### Incremental delivery by release

- **Release 1** = US1 + US2 + US3 + US4 → public v1 (teardowns + web demo + CLI). Ship + article.
- **Release 2** = US5–US10 → duels/comparison/diff/export. Ship + the flagship duel article (Gate C).
- **Release 3** = US11–US14 → decay/CI/API/methodology. Ship + articles.

### Parallel-team strategy

After Foundational, the engine's clean subpackage boundaries (behind the shared report schema) let the R1 stories run concurrently: one workstream on the verdict/classification (US1), one on dead-weight/conflict (US2), one on teardowns (US3), one on the CLI (US4). The Gate A/B harness and the report schema are the integrating spine.

---

## Notes

- `[P]` = different files, no dependency on incomplete tasks.
- Story labels map tasks to spec.md user stories for traceability; `[US-shared]` marks Foundational tasks that are engine-wide join points.
- The engine is deliberately Foundational because every story consumes it; this keeps each story phase a thin, independently testable increment rather than a re-implementation.
- Commit after each task or logical group; keep commit messages plain (no AI attribution, per project rules) and link work items by hash.
- Deliberate R1 simplifications (no PPL, no learned combiner, no judge ensemble, no full pairwise) are recorded in research.md with their upgrade triggers — do not silently expand scope.
