# Implementation Plan: Prompt Weight Linter (Prose Weight Visualiser)

**Branch**: `001-prompt-weight-linter` | **Date**: 2026-08-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-prompt-weight-linter/spec.md`

## Summary

A measurement instrument and linter for prompts. A user pastes a system prompt (or CLAUDE.md, or agent instructions); the tool segments it into discrete instructions, then measures each instruction's behavioural weight empirically against a local model by ablation (remove the instruction, re-run a fixed probe suite N times, measure the behavioural delta), led by ablation with token attention used only as a cheap pre-screen and explainer. Every number carries a Bayesian posterior credible interval, an explicit noise-floor state, the probe-suite version, and the model it was measured on.

The engine is a single core library consumed by four thin surfaces: a CLI (`proseweight`), a local/self-hosted web app, a local HTTP daemon, and a CI linter. Scope is the full three-release mandate sequenced by priority (R1 linter core + teardowns + CLI; R2 duels/emphasis/position/grid/diff/export; R3 decay/CI/watch/methodology). The predecessor code (`prose_weight_visualiser.py`) already implements token-level KL-divergence ablation and attention extraction on Qwen2.5/Llama local models; that becomes the token-level core the instruction-level engine aggregates over.

## Technical Context

**Language/Version**: Python 3.11+ (single language across engine, CLI, web, API, CI).

**Primary Dependencies** (pins from `research.md`, to lock at implementation): PyTorch + `transformers` + `accelerate` (subject/judge runtime, eager attention, bf16 on CUDA) with `bitsandbytes`/`autoawq` for the 4-bit local judge and `outlines` (or a logits processor) for grammar-constrained judge scoring; `sentence-transformers>=3.0,<4.0` (bge-small-en-v1.5 embedder + NLI cross-encoder, models pinned to exact HF revision SHAs); `markdown-it-py==4.2.0` + `mdit-py-plugins==0.4.2` + `pysbd==0.3.4` + `llama-cpp-python` (segmentation/paraphrase); `numpy==2.3.3` + `scipy==1.16.3` (Bayesian posteriors — no PyMC/NumPyro/JAX); `Jinja2==3.1.6` + inline SVG + `Pillow==12.3.0` + a checked-in OFL font (self-contained HTML + PNG export); `anthropic` SDK (opt-in `claude-haiku-4-5` judge, key from env); Gradio (local web surface); Typer/Click (CLI); FastAPI/uvicorn (watch-mode daemon); promptfoo `0.122.0` config schema (probe-suite format).

**Storage**: Local files only (single-tenant, no database service). Per-model run results and per-instruction posteriors stored as structured files (JSON, plus columnar files for large ablation matrices) under a per-model results tree; probe suites are versioned files; famous-prompt teardowns are pre-computed report files; CI baselines are JSON files checked into the user's repo like a lockfile.

**Testing**: pytest, with unit / integration / contract layers plus a dedicated gates harness for the honesty kill-criteria (Gate A instrument validity, Gate B reproducibility, Gate C flagship-duel publication). Golden/snapshot tests for the deterministic report schema and HTML/PNG exports.

**Target Platform**: Local developer machines (Windows/Linux/macOS). CUDA GPU used when present; degraded-but-functional CPU mode for small models. No hosted execution — the public web demo is read-only pre-computed content.

**Project Type**: Single Python repository — one core engine library plus multiple thin entry-point surfaces (CLI, web, API daemon, CI). Not a frontend/backend split (the web surface is Python/Gradio).

**Performance Goals**: Quick scan of a 50-instruction prompt completes in ≤10 minutes on a single consumer GPU (SC-003 / cost-sanity gate). Deep audit is the overnight-capable full ablation matrix × N runs. Attention pre-screen ranks instructions so quick scan only ablates top candidates.

**Constraints**: Deterministic and seedable — fully-local runs reproduce identical verdicts for the same seed (FR-017 / SC-002); nondeterminism (frontier API judge) is opt-in, isolated, and flags the run best-effort. Ablation-led ordering is structural on every surface (FR-034). Every number is scoped to suite version + model (FR-035). Single-command install/run without hand-managed environments. No API keys in source (frontier judge key from env only).

**Scale/Scope**: A prompt is tens to a few hundred instructions. Probe suite is 10–15 tasks. N runs per condition (deep audit) is the dominant compute cost. R2 grid runs 3–4 local models. 33 functional requirements, 14 user stories across 3 releases.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against the project constitution v1.5.0. Initial gate (pre-research): **PASS**. Post-design re-check (after Phase 1 artifacts): **PASS** — `research.md`, `data-model.md`, `contracts/*`, and `quickstart.md` introduce no new violations. The design actively strengthens Principles I (one versioned report schema shared by all surfaces), II (report/CLI/suite/API contracts all SemVer'd), III (Gates A/B/C are executable tests; edge cases enumerated), IV (seed determinism proven in quickstart Scenario 2, nondeterminism isolated to the opt-in API judge and flagged), and XII (every report field answers what/why/what-follows; attention is transparency-only, never a verdict). No Complexity Tracking entries required at either gate.

- **Prime Directive (Boil the Ocean)**: The plan carries the full three-release scope with nothing dropped; release boundaries are shipping order, and R1 design anticipates R2/R3 (per-model storage, suite versioning, stable report schema). ✅
- **I. Modular & Composable**: One core engine library (segmentation, probes, ablation, attention, paraphrase, stats, judge, models, report) consumed by thin CLI/web/API/CI surfaces. Shared logic lives once behind explicit interfaces; surfaces never own measurement logic. ✅
- **II. Contract Stability & SemVer**: Three public contracts are versioned — the report/verdict JSON schema, the CLI command surface, and the probe-suite format. Each is pinned and SemVer'd; the report schema version is stamped into every artefact. ✅
- **III. Comprehensive Tests for Public Contracts**: The report schema, CLI, engine outputs, and honesty guarantees get comprehensive tests including edge cases (noise-floor state, interrupted run, CPU fallback, all-below-noise, interval-overlapping ties). Gates A/B/C are executable tests. Test-first is encouraged, not mandated. ✅
- **IV. Deterministic & Observable Behaviour**: Seed control yields identical fully-local verdicts; nondeterminism (API judge) is opt-in, isolated, documented, and flagged. Structured logs/telemetry on every run; a result traces to the exact model, suite version, seed, and N. ✅
- **V. Simplicity & Justified Complexity**: The multi-surface, multi-package layout is driven by explicit spec requirements (CLI + web + API + CI are all required deliverables), not gratuitous. R1 deliberately avoids the heavier options (no full PPL/MCMC, no learned combiner, no ensemble judge, no pairwise-full ablation) — these are documented future refinements. No Complexity Tracking entry needed. ✅
- **VI. Complete the Scope**: Each release ships its items together (R1 items 1–14 as one public v1), and each release's article is part of its definition of done. Known in-scope work is not deferred within a release. ✅
- **VII. Tracker Is the Project of Record**: An ADO mirror exists (project ProseWeightVisualizer). Work items and commit↔work-item linkage are handled at `/speckit-tasks` and implementation time; this plan flags that the board must be populated from the task breakdown. ✅ (enforced downstream)
- **VIII. Start From a Fresh Base**: Work is on branch `001-prompt-weight-linter` cut from `master`. ✅
- **IX. Ask, Then Wait**: The five gating design decisions were resolved via `/speckit-clarify` before planning. ✅
- **X. Production Changes Wait for a Human**: N/A — a local, single-tenant tool with no production environment. The public web demo is read-only static content; publishing it is a normal deploy, not a data-bearing prod mutation. ✅
- **XI. Establish the Mechanism Before Changing Code**: Phase 0 research grounds each open approach in current library reality (pinned versions) rather than assumption; the predecessor code is read, not guessed at. ✅
- **XII. Explain Every Number**: The tool's reason for existing. Every displayed figure answers what/why/what-follows (weight, interval, classification, token cost, headline noise-floor %), attention is never a standalone verdict, and filtered counts (dead-weight list) state what they exclude. ✅

## Project Structure

### Documentation (this feature)

```text
specs/001-prompt-weight-linter/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (report schema, CLI, suite format, API)
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/proseweight/
├── segmentation/     # prompt -> instructions (markdown-AST + sentence split + local-model refine); merge/split; source char-span mapping
├── probes/           # probe-suite loading, versioning, promptfoo-compatible BYO suites, per-probe checks, suite self-quality
├── models/           # model abstraction + loaders; per-model result storage; CPU/GPU selection (absorbs predecessor get_model)
├── engine/           # token-level ablation (absorbs predecessor ablation_scores), attention pre-screen, instruction-level aggregation, paraphrase sensitivity, weight blend
├── judge/            # judge backend interface; local judge (default) + frontier API judge adapter (opt-in, best-effort); rubric scoring; judge-noise estimation
├── stats/            # Bayesian posteriors, credible intervals, noise-floor test, ROPE duels, 0-100 weight scale
├── verdict/          # orchestration: quick scan / deep audit; classification (load-bearing/contributing/decorative/contradicted); dead-weight + conflict (candidate pairwise); headline
├── duel/             # R2 phrasing duels, emphasis audit, position sensitivity
├── grid/             # R2 model comparison grid
├── diff/             # R2 prompt diff (v1 vs v2)
├── decay/            # R3 decay curve (deep-audit-only)
├── report/           # verdict/duel/diff schema (versioned), classification rendering, self-contained HTML export + PNG summary card
├── ci/               # R3 lint against baseline, exit codes, dead-weight budget; GitHub Action wrapper
├── api/              # R3 watch-mode local daemon (HTTP)
├── web/              # local/self-hosted Gradio surface (paste -> segment -> configure -> progress -> verdict; attention demoted to "how it works")
├── cli/              # `proseweight` (scan / duel / diff / lint / serve) -> JSON + terminal summary
└── methodology/      # R3 published methodology content source

data/
├── suites/           # versioned probe suites (shipped default suite vX)
├── teardowns/        # pre-computed famous-prompt verdict reports (published prompts, each source-cited)
└── fixtures/         # planted-ground-truth synthetic prompts for Gate A

tests/
├── unit/
├── integration/
├── contract/         # report schema, CLI, suite-format, API contract tests
└── gates/            # Gate A (instrument validity), Gate B (reproducibility), Gate C (flagship duel publication)

docs/
├── brainstorm-prose-weight.md   # existing source brainstorm
└── methodology.md               # R3 public methodology page (ships in draft with v1)
```

**Structure Decision**: Single Python project. The measurement engine is a library (`src/proseweight/`, Principle I) with the token-level ablation/attention core absorbed from the existing `prose_weight_visualiser.py`. The four required surfaces (CLI, web, API, CI) are thin consumers under their own packages. Release-2/3 analyses (`duel`, `grid`, `diff`, `decay`, `ci`, `api`) are separate packages layered on the R1 engine, so R1 storage/schema decisions can anticipate them without R1 building them. Data (suites, teardowns, fixtures) lives outside the package tree so suites and teardowns version independently of code.

## Complexity Tracking

> No Constitution Check violations — this section intentionally left empty.

Deliberate R1 simplifications (documented as future refinements, not deferred in-scope work): no full PPL/MCMC (analytic Bayesian posteriors instead), no learned divergence combiner (fixed documented blend), no judge ensemble (single separate local judge), no full pairwise ablation (candidate pairs only). Each is recorded in `research.md` with the trigger that would justify adopting it later.
