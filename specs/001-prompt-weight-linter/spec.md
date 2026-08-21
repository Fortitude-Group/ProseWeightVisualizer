# Feature Specification: Prompt Weight Linter (Prose Weight Visualiser)

**Feature Branch**: `001-prompt-weight-linter`

**Created**: 2026-08-20

**Status**: Draft

**Input**: User description: `docs/brainstorm-prose-weight.md`

## Overview

A measurement instrument and linter for prompts. A user pastes a system prompt, CLAUDE.md, or set of agent instructions and gets back, with numbers and confidence intervals, which instructions actually carry behavioural weight and which are decorative. Weight is measured empirically against local models, led by ablation (remove an instruction, re-run a fixed probe suite, measure the behavioural change), with token attention used only as a cheap pre-screen and an explainer, never as the verdict. The tool is deliberately honest: every score carries an interval, an explicit "not distinguishable from noise" state, the probe suite it was measured against, and the model it was measured on.

The full scope is sequenced into three releases, mapped here to priorities P1 (Release 1), P2 (Release 2), P3 (Release 3). All of it is in scope; the release boundaries are shipping order, not architectural walls.

## Clarifications

### Session 2026-08-20

- Q: Which statistical approach should the tool use for weights, the noise floor, and duel significance? → A: Bayesian throughout — posterior credible intervals per weight; the noise floor is the credible interval overlapping zero effect; duels judge significance with a posterior plus a region of practical equivalence (ROPE). No frequentist p-values or multiple-comparison corrections are used.
- Q: What can a visitor do on the hosted web demo? → A: Read-only. Pre-computed teardowns and published duels are viewable live; paste-your-own-prompt runs happen strictly locally via the CLI or a local instance. The hosted demo performs no prompt execution and hosts no GPU worker.
- Q: How is the behavioural-delta judge configured? → A: Default is a separate local judge model, distinct from the subject, with judge noise estimated and folded into the posterior. A frontier paid API model is selectable as the judge (judging needs no attention access, so a closed model is legitimate here even though closed models are excluded as the subject). When a frontier API judge is used, its results are flagged best-effort and the same-seed identical-verdict reproducibility guarantee (SC-002) does not apply.
- Q: What is the first model and the Release 2 comparison-grid roster? → A: Release 1 subject model is Qwen2.5-1.5B-Instruct (the predecessor tools already run the Qwen2.5 family). The Release 2 grid is Qwen2.5-0.5B / 1.5B / 3B-Instruct (a within-family size sweep) plus one other-family instruct model of comparable size (a Llama-3.x-1B/3B-Instruct or Phi-class model) for cross-family contrast. Exact fourth-model pick is confirmed at planning against the GPU budget.
- Q: How are the three divergence signals (embedding distance, judge rubric, programmatic checks) combined? → A: A fixed, documented set of blend weights applied across all probes, tuned once and frozen, and validated (not fitted) against the Gate A planted ground truth so SC-001 stays an honest external check. Per-probe weighting and a learned combiner are documented future refinements, not Release 1 requirements.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Verdict report for a pasted prompt (Priority: P1)

An engineer who owns a long system prompt pastes it in, reviews how the tool split it into discrete instructions (adjusting the split where needed), picks a run depth, watches progress, and receives a ranked report. Every instruction is scored 0-100 for behavioural weight, classified as load-bearing / contributing / decorative / contradicted, and shown with a confidence interval. Instructions whose effect cannot be told apart from run-to-run noise are rendered in a visually distinct "noise floor" state rather than as a low score. The report leads with the headline: "N% of this prompt is below the noise floor."

**Why this priority**: This is the product. Without a trustworthy, ablation-led verdict the rest has nothing to stand on. It is the minimum that delivers the core value ("tell me which lines do anything") and the honesty commitments that make the value defensible.

**Independent Test**: Paste a prompt containing a mix of clearly load-bearing instructions (ones the probe tasks directly test) and clearly inert filler; run a deep audit; confirm the load-bearing instructions rank above the filler, the filler lands in the noise-floor state, and every score shows an interval and the suite/model it was measured against.

**Acceptance Scenarios**:

1. **Given** a pasted multi-line prompt, **When** the user requests segmentation, **Then** the prompt is split into discrete, individually listed instructions that respect markdown structure, lists, headers, and XML tags, and each segment can be merged or split before a run.
2. **Given** a reviewed set of segments, **When** the user starts a quick scan, **Then** a time/cost estimate is shown before the run begins and the run completes with an attention pre-screen plus ablation of the top-ranked candidate instructions.
3. **Given** a reviewed set of segments, **When** the user starts a deep audit, **Then** the full ablation matrix runs N times per condition and each instruction receives a weight score with a confidence interval.
4. **Given** a completed run, **When** the report renders, **Then** each instruction shows its 0-100 weight, its per-component contributions (ablation delta, attention mass, paraphrase sensitivity), its classification, and its confidence interval.
5. **Given** an instruction whose ablation delta is within the run-to-run variance, **When** the report renders, **Then** that instruction is shown in an explicit "not distinguishable from noise" state that is visually distinct from a genuinely low weight.
6. **Given** an instruction whose removal improves compliance with another instruction, **When** the report renders, **Then** it is classified "contradicted" and the instruction it conflicts with is named.
7. **Given** the same prompt and the same seed run twice as deep audits, **When** both complete, **Then** the two verdicts are identical.

---

### User Story 2 - Dead-weight and conflict findings (Priority: P1)

From the same run, the user gets an actionable shortlist: the instructions below the noise floor, each with the token cost the user is paying per call to keep it ("you are paying X tokens per call for sentences that do nothing"), and the pairs of instructions that fight each other. This is the "what do I cut, and what do I fix" layer the reviewer takes into a prompt review.

**Why this priority**: The ranked report answers "what has weight"; this answers "what do I do about it", which is why the engineer opened the tool. It is a distinct, demonstrable deliverable built on the same measurement.

**Independent Test**: Run a prompt seeded with known dead sentences and a known contradictory pair; confirm the dead sentences appear in the cut list with a token cost, and the contradictory pair is surfaced as a conflict, without either being asserted as a rewrite.

**Acceptance Scenarios**:

1. **Given** a completed run, **When** the dead-weight view opens, **Then** every instruction below the noise floor is listed with its token cost per call.
2. **Given** single-ablation results that flag candidate interacting instructions, **When** pairwise ablation runs on those candidates, **Then** instruction pairs that reduce each other's effect are surfaced as conflicts.
3. **Given** the dead-weight and conflict findings, **When** they are presented, **Then** they are framed as measured findings and a suggested cut list, and the tool never rewrites or generates replacement prompt text.

---

### User Story 3 - Famous-prompt teardowns, pre-loaded (Priority: P1)

A first-time visitor who has run nothing sees complete verdict reports on recognisable, published public prompts. They read the verdict on a prompt they already know, understand what the tool claims, and see the honesty framing before deciding to run their own.

**Why this priority**: This is the instant proof and the marketing. It lets the value land with zero setup and zero compute on the visitor's part, and it demonstrates the honesty framing on prompts people recognise.

**Independent Test**: Load the demo with no run started; confirm at least two teardowns of published prompts are viewable in full, each citing its source, each showing weights, classifications, intervals, and the suite/model scoping.

**Acceptance Scenarios**:

1. **Given** a fresh visit with no run started, **When** the teardown section loads, **Then** at least two full verdict reports on recognisable published prompts are viewable.
2. **Given** a teardown, **When** it is viewed, **Then** it cites the published source of the prompt and shows the same weights, classifications, intervals, and suite/model scoping as a live run.
3. **Given** the teardown prompts, **When** they are selected for inclusion, **Then** each uses only officially published or released material, with no leaked content of ambiguous provenance.

---

### User Story 4 - Command-line scan (Priority: P1)

An engineer runs `proseweight scan <file>` against a prompt file and gets the same verdict as the web report, as machine-readable JSON plus a readable terminal summary, so the tool fits into scripts and their own tooling.

**Why this priority**: The CLI is half of Release 1's definition of done and the seed of the later CI wedge. Parity between CLI and web output is what makes the tool trustworthy across surfaces.

**Independent Test**: Run the CLI against a prompt file and against the same prompt in the web UI with the same settings and seed; confirm the JSON verdict matches the web verdict and the terminal summary reports the same headline number, suite version, and model.

**Acceptance Scenarios**:

1. **Given** a prompt file, **When** `proseweight scan` runs, **Then** it emits a JSON report containing per-instruction weights, components, classifications, intervals, the suite version, the seed, and the model.
2. **Given** the same prompt, settings, and seed, **When** run through the CLI and the web UI, **Then** the two verdicts agree.
3. **Given** a machine with no GPU, **When** the CLI runs against a small local model, **Then** it completes in a degraded-but-functional mode and the report records that it ran on CPU.

---

### User Story 5 - Phrasing duel (Priority: P2)

A user pits two phrasings of the same instruction against each other across the probe suite and gets a winner with a significance verdict (effect size plus a p-value or Bayesian equivalent), backed by side-by-side attention heatmaps, exportable to share. The flagship published duel is a vivid directive versus a beige equivalent on a deferral-prone task.

**Why this priority**: Duels are the headline of Release 2 and the flagship article. They turn the measurement engine into a persuasion tool for the "does wording matter" argument.

**Independent Test**: Duel two phrasings known to differ in effect; confirm the report names a winner only when the difference clears the significance threshold, reports effect size and the significance measure, and can be exported as a shareable artefact.

**Acceptance Scenarios**:

1. **Given** two phrasings of one instruction, **When** a duel runs, **Then** both are measured across the probe suite over N runs and the result reports effect size and a significance measure.
2. **Given** a duel whose difference does not clear the significance threshold, **When** the result renders, **Then** it reports "no significant difference" rather than declaring a winner.
3. **Given** a completed duel, **When** the user exports it, **Then** a shareable artefact of the result is produced.

---

### User Story 6 - Emphasis audit (Priority: P2)

For a chosen instruction, the tool auto-generates emphasis variants (CAPS, bold, "IMPORTANT:", exclamation marks, repetition, list position), runs the matrix, and reports which devices actually move weight on which model.

**Why this priority**: A standalone publishable finding and a direct test of common prompt folklore, built on the duel machinery.

**Independent Test**: Run the emphasis audit on one instruction; confirm each formatting device is measured as its own variant and the report states, per device and per model, whether it moved weight beyond the noise floor.

**Acceptance Scenarios**:

1. **Given** a selected instruction, **When** the emphasis audit runs, **Then** the tool generates variants for each supported formatting device and measures each.
2. **Given** audit results, **When** the report renders, **Then** each device is reported as moving weight or not, per model, with intervals.

---

### User Story 7 - Position sensitivity (Priority: P2)

The user moves an instruction through positions in the prompt (top / middle / bottom, before / after related sections) and the tool re-measures its weight at each position, giving a per-model empirical answer to "does putting it first matter?"

**Why this priority**: Another publishable, model-specific finding reusing the measurement engine.

**Independent Test**: Measure one instruction at several positions in the same prompt; confirm a weight with interval is reported for each position and the positions are directly comparable.

**Acceptance Scenarios**:

1. **Given** an instruction and a set of positions, **When** position sensitivity runs, **Then** the instruction's weight is measured at each position with a confidence interval.
2. **Given** the results, **When** rendered, **Then** the positions are shown side by side for the same model.

---

### User Story 8 - Model comparison grid (Priority: P2)

The user runs one prompt across several local models and sees the weight scores side by side, demonstrating that prompt advice is model-specific. This is the honest stand-in for a universal prompt score, which the tool refuses to provide.

**Why this priority**: The comparison grid is the structural answer to "why not one score", and it depends on the per-model result storage designed into Release 1.

**Independent Test**: Run one prompt across three or more local models; confirm each instruction's weight is shown per model and the grid never collapses to a single cross-model score.

**Acceptance Scenarios**:

1. **Given** a prompt and a roster of local models, **When** the grid runs, **Then** each instruction's weight is stored and shown separately per model.
2. **Given** the grid, **When** it renders, **Then** no universal cross-model "prompt quality score" is produced or implied.

---

### User Story 9 - Prompt diff (Priority: P2)

The user pastes v1 and v2 of a prompt and sees which instruction weights shifted, which instructions appeared or vanished, and whether any previously load-bearing instruction was accidentally neutered by the edit.

**Why this priority**: Turns a one-shot audit into something a team re-runs on every prompt change, and is the conceptual bridge to CI mode.

**Independent Test**: Diff a prompt against an edited copy in which one load-bearing instruction was weakened; confirm the diff flags that instruction's weight drop and lists any added or removed instructions.

**Acceptance Scenarios**:

1. **Given** two versions of a prompt, **When** a diff runs, **Then** the report lists per-instruction weight changes and any instructions added or removed.
2. **Given** a previously load-bearing instruction whose weight dropped materially in v2, **When** the diff renders, **Then** that regression is flagged distinctly.

---

### User Story 10 - Shareable report export (Priority: P2)

Any verdict, duel, or diff can be exported as a self-contained HTML page that needs no server to view, plus a compact PNG summary card for social and Slack embedding.

**Why this priority**: These results get pasted into team channels; a portable, server-free artefact is what makes the tool spread.

**Independent Test**: Export a verdict; open the resulting HTML file with no server running and confirm it renders fully, and confirm a PNG summary card is produced alongside it.

**Acceptance Scenarios**:

1. **Given** any completed verdict, duel, or diff, **When** the user exports it, **Then** a single self-contained HTML file is produced that renders without a server.
2. **Given** an export, **When** it completes, **Then** a compact PNG summary card is produced for embedding.

---

### User Story 11 - Decay curve (Priority: P3)

The user measures how a system-prompt instruction's compliance changes as a conversation grows, with compliance sampled at turns 1, 5, 10, and 20 against controlled synthetic filler, producing the "your system prompt evaporates" chart per instruction and per model.

**Why this priority**: The most compute-hungry feature and the best chart in the project, but deep-audit-only and dependent on the mature measurement engine, so it lands last.

**Independent Test**: Run the decay measurement on one instruction; confirm compliance is reported at each sampled turn with intervals and the filler content is held controlled across turns.

**Acceptance Scenarios**:

1. **Given** an instruction and a conversation-length schedule, **When** the decay run executes, **Then** compliance is measured at each sampled turn with a confidence interval, using controlled synthetic filler.
2. **Given** decay results, **When** rendered, **Then** the curve is shown per instruction and per model.

---

### User Story 12 - CI mode (Priority: P3)

A team checks a baseline weights file into their repo and runs `proseweight lint CLAUDE.md --baseline weights.json` in CI. The build fails if a load-bearing instruction's weight drops beyond a threshold after an edit, or if new dead weight exceeds a budget. A GitHub Action wraps it.

**Why this priority**: The product wedge beyond the demo, and the reason the report schema and baselines were designed early, but it depends on diff and the stable schema.

**Independent Test**: Run the CI command against a prompt edited to weaken a load-bearing instruction past the threshold; confirm a non-zero exit code and a report naming the regression; run it against a benign edit and confirm a zero exit code.

**Acceptance Scenarios**:

1. **Given** a baseline weights file and an edited prompt that drops a load-bearing instruction beyond threshold, **When** the lint runs, **Then** it exits non-zero and reports the regression.
2. **Given** an edit that adds dead weight beyond the configured budget, **When** the lint runs, **Then** it exits non-zero and reports the added dead weight.
3. **Given** a benign edit within thresholds, **When** the lint runs, **Then** it exits zero.

---

### User Story 13 - Watch mode / local API (Priority: P3)

A local daemon exposes a small HTTP API so an editor or agent can query instruction weights while a prompt is being edited.

**Why this priority**: A minimal enabler for integrations, not a platform, and it sits on top of the finished engine, so it is last.

**Independent Test**: Start the daemon and query the weight of an instruction via the API; confirm a weight with interval is returned for a known prompt.

**Acceptance Scenarios**:

1. **Given** the daemon running, **When** a client queries an instruction's weight over the local API, **Then** it receives the weight, its components, and its interval.

---

### User Story 14 - Public methodology page (Priority: P3)

Alongside the tool, a full written methodology is published: how weights are computed, what they mean, what they do not mean, and the known limitations.

**Why this priority**: Honesty and citation-bait; it ships with v1 in draft and is completed as the releases mature, so its full form is a Release 3 deliverable.

**Independent Test**: Confirm the methodology page exists, describes the weight computation and its components, and states the ablation-led ordering and the known limitations.

**Acceptance Scenarios**:

1. **Given** the published methodology, **When** it is read, **Then** it states how weights are computed, what they do and do not mean, the ablation-over-attention ordering, and known limitations.

---

### Edge Cases

- **Segmentation is wrong**: the user can always merge and split segments manually before a run, and a run cannot start on a segmentation the user has not been given the chance to review.
- **Prompt too large for the depth chosen**: the pre-run estimate warns when a deep audit would exceed the cost-sanity budget, and the user can drop to quick scan or trim the probe suite.
- **No GPU present**: runs degrade to CPU with small models and the report records that it ran on CPU; large-model runs that cannot complete on the hardware are refused before starting, not left to hang.
- **Every instruction is below the noise floor**: the report says so honestly rather than manufacturing a ranking, and the headline number reflects it.
- **Two instructions are near-identical**: they are measured independently and their intervals are allowed to overlap; the tool does not force an artificial ordering between interval-overlapping scores.
- **A run is interrupted**: partial results are marked as incomplete and are never presented as a finished verdict.
- **A probe task never differentiates any instruction**: it is itself flagged as dead weight in the instrument (the tool's own logic applied to its suite).

## Requirements *(mandatory)*

### Functional Requirements

**Segmentation and input**

- **FR-001**: The system MUST split a pasted or supplied prompt into discrete instructions at sentence/clause level, respecting markdown structure, lists, headers, and XML tags.
- **FR-002**: Users MUST be able to merge and split segments before a run, and no run may start on segmentation the user has not had the opportunity to review.

**Probe suite**

- **FR-003**: The system MUST ship a fixed, versioned probe suite of 10-15 small, discriminating instruction-following tasks, visible in the UI and docs and never implicit.
- **FR-004**: Users MUST be able to supply their own probe suite (a bring-your-own-suite format, promptfoo-compatible preferred) so that weights are explicitly "weight against these tasks".
- **FR-005**: Every result MUST record the probe suite version it was measured against, and every report MUST state that version.

**Measurement engine**

- **FR-006**: For each instruction, the system MUST measure a behavioural delta by removing it, re-running the probe suite, and comparing the output to the full-prompt output; deltas MUST be measured by a blend of embedding distance, judge scoring against per-probe rubrics, and task-specific programmatic checks, never by string diffs.
- **FR-006a**: The judge that scores outputs against per-probe rubrics MUST default to a separate local model, distinct from the subject model (never the subject judging itself), with judge noise estimated (e.g. by re-scoring identical outputs) and folded into the reported posterior.
- **FR-006b**: The judge backend MUST be configurable to a frontier paid API model as an opt-in alternative. When a frontier API judge is used, the run MUST be labelled best-effort and the reproducibility guarantee (FR-017 / SC-002) is explicitly waived for that run, since API judges are not seed-deterministic. The subject model remains local regardless of judge choice (closed API models are excluded as the subject per the out-of-scope list).
- **FR-006c**: The three divergence signals MUST be combined with a fixed, documented set of blend weights applied uniformly across probes, frozen after an initial tuning and validated (not fitted) against the Gate A planted ground truth. Per-probe weighting and a learned combiner are out of scope for Release 1.
- **FR-007**: The system MUST compute token attention mass over prompt tokens during probe runs, aggregated per instruction, and use it ONLY as a pre-screen to prioritise ablation and as an explainer layer. Attention MUST NEVER be presented as a verdict on its own, on any surface.
- **FR-008**: For each instruction, the system MUST generate K paraphrases of the same intent and measure output variance across them (paraphrase sensitivity).
- **FR-009**: The system MUST compute a 0-100 behavioural weight per instruction blending ablation delta (dominant), attention mass, and paraphrase sensitivity, and MUST show the per-component contributions on every instruction. The blend weights MUST be configurable, with the default documented and justified.

**Verdict and findings**

- **FR-010**: The system MUST classify each instruction as load-bearing, contributing, decorative, or contradicted, where "contradicted" means an instruction whose removal improves compliance with another instruction, and it MUST name the instruction it conflicts with.
- **FR-011**: The report MUST lead with the headline proportion of the prompt that falls below the noise floor.
- **FR-012**: The system MUST list dead-weight instructions (below the noise floor) with the token cost per call of keeping each.
- **FR-013**: The system MUST run pairwise ablation on candidate interacting pairs flagged by the single-ablation pass and surface pairs that reduce each other's effect as conflicts. Full pairwise ablation is NOT required; candidates only.
- **FR-014**: The system MUST NOT generate, rewrite, or auto-edit prompt text; a suggested cut list is a report artefact only.

**Statistical honesty (non-negotiable)**

- **FR-015**: The system MUST run N runs per condition and report a Bayesian posterior credible interval on every score. Frequentist p-values and multiple-comparison corrections MUST NOT be used.
- **FR-016**: The system MUST render an explicit "not distinguishable from noise" state, defined as an instruction whose credible interval overlaps zero effect, and it MUST be visually distinct from a genuinely low score.
- **FR-017**: The system MUST accept a seed and MUST produce identical verdicts for the same prompt, settings, suite, model, and seed.
- **FR-018**: The system MUST report run-to-run variance, and MUST NOT ship a verdict without intervals.

**Run control and runtime**

- **FR-019**: The system MUST offer at least two run depths: a quick scan (attention pre-screen plus ablation of top-ranked candidates) and a deep audit (full ablation matrix over N runs), and MUST show a time/cost estimate before a run starts.
- **FR-020**: The system MUST run against local models, store results per model from the first release, and function in a degraded-but-functional CPU mode for small models when no GPU is present, recording in the report when a run used CPU.

**Surfaces**

- **FR-021**: The web experience (running as a local or self-hosted instance, not the read-only public demo) MUST support the flow paste prompt -> review segments -> configure run -> live progress -> verdict report, with the attention heatmap demoted to a "how it works" view rather than the headline.
- **FR-022**: The system MUST provide a CLI `proseweight scan <file>` that produces the same verdict as the web report, as JSON plus a terminal summary, with parity between CLI and web output for the same inputs and seed.
- **FR-023**: The system MUST ship at least two pre-loaded teardowns of recognisable published prompts, viewable in full with no run started, each citing its published source and using only officially published material.

**Release 2 capabilities**

- **FR-024**: The system MUST support duelling two phrasings of the same instruction across the probe suite, reporting effect size and Bayesian significance (posterior probability the difference lies outside the region of practical equivalence), and MUST NOT declare a winner when the posterior does not clear the difference beyond the ROPE. Duel results MUST be exportable.
- **FR-025**: The system MUST support an emphasis audit that auto-generates formatting variants (CAPS, bold, "IMPORTANT:", exclamation, repetition, list position) for an instruction and reports which devices move weight, per model.
- **FR-026**: The system MUST support measuring an instruction's weight across positions in the prompt and reporting the results side by side for the same model.
- **FR-027**: The system MUST support a model comparison grid showing per-instruction weights across three or more local models side by side, and MUST NOT produce or imply a universal cross-model score.
- **FR-028**: The system MUST support diffing two prompt versions, reporting per-instruction weight changes, added/removed instructions, and distinctly flagging any previously load-bearing instruction whose weight dropped beyond the configurable `load_bearing_drop` threshold (the same threshold CI mode uses in FR-031; default documented). "Materially" is defined by that threshold, not left to judgement.
- **FR-029**: The system MUST export any verdict, duel, or diff as a self-contained HTML page that renders with no server, plus a compact PNG summary card.

**Release 3 capabilities**

- **FR-030**: The system MUST support a decay measurement sampling instruction compliance at growing conversation lengths (turns 1, 5, 10, 20) against controlled synthetic filler, reported per instruction and per model, as a deep-audit-only feature.
- **FR-031**: The system MUST provide a CI command `proseweight lint <file> --baseline <file>` that exits non-zero when a load-bearing instruction's weight drops beyond a threshold or new dead weight exceeds a budget, and exits zero otherwise, wrapped by a GitHub Action, with baseline files intended to be checked into the repo.
- **FR-032**: The system MUST provide a local daemon exposing a small HTTP API that returns an instruction's weight, components, and interval on request.
- **FR-033**: The system MUST publish a methodology document describing how weights are computed, what they mean and do not mean, the ablation-over-attention ordering, and known limitations.

**Cross-cutting honesty and scope guardrails**

- **FR-034**: Every public surface (UI, report, CLI output, exported artefact, methodology) MUST state the ablation-led ordering (attention is pre-screen and explainer only) structurally, not as a footnote disclaimer.
- **FR-035**: Every number shown MUST be scoped on its surface to the probe suite version and the model it was measured against.
- **FR-036**: The system MUST NOT act as jailbreak or red-team tooling; duel mode compares phrasings of legitimate instructions only, and no surface may imply bypass-finding.
- **FR-037**: The system MUST remain single-tenant and run on the user's own hardware; no accounts, billing, or hosted multi-tenant service is in scope. The hosted web demo is read-only: it serves pre-computed teardowns and published duels for viewing and MUST NOT execute visitor-supplied prompts or host a GPU worker. Paste-your-own runs happen locally via the CLI or a local instance.

### Key Entities *(include if feature involves data)*

- **Prompt**: the text under test; has one or more versions (for diffing) and is decomposed into instructions.
- **Instruction (segment)**: a discrete unit of the prompt; carries a weight score, per-component contributions, a classification, a confidence interval, and a token cost.
- **Probe Task**: a small task used to elicit instruction-following behaviour; can itself be flagged as non-discriminating (dead weight in the instrument).
- **Probe Suite**: a versioned collection of probe tasks; either the shipped suite or a user-supplied one; recorded on every result.
- **Run**: an execution against a specific model, suite version, seed, depth (quick/deep), and N; produces per-instruction results with intervals; may be marked incomplete.
- **Weight Score**: a 0-100 value with its component breakdown (ablation delta, attention mass, paraphrase sensitivity) and interval.
- **Verdict / Classification**: load-bearing / contributing / decorative / contradicted, plus the noise-floor state.
- **Conflict**: a pair of instructions that reduce each other's effect, with the pair identified.
- **Duel**: a comparison of two phrasings of one instruction with effect size and a significance measure.
- **Diff**: a comparison of two prompt versions with per-instruction weight deltas and add/remove lists.
- **Model**: a local model the prompt is measured against; results are stored per model.
- **Baseline**: a stored weights file used by CI mode to detect regressions.
- **Report / Export**: a rendered verdict, duel, or diff, exportable as self-contained HTML plus a PNG summary card.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001** (instrument validity): On a synthetic prompt with planted ground truth (instructions known to be load-bearing because probes directly test them, plus planted no-op sentences), the verdict ranks all planted load-bearing instructions above all planted no-ops in at least 90% of deep-audit runs, and the noise-floor state correctly captures the no-ops.
- **SC-002** (reproducibility): For fully-local runs (local subject and local judge), two deep audits of the same prompt with the same seed produce identical verdicts; with different seeds, classification agreement on load-bearing/decorative is at least 85%, with disagreements confined to interval-overlapping scores. Runs using a frontier API judge are exempt from the identical-verdict guarantee and are labelled best-effort.
- **SC-003** (cost sanity): A quick scan of a 50-instruction prompt completes in 10 minutes or less on a single consumer GPU.
- **SC-004** (honesty on every score): 100% of scores shown carry a posterior credible interval, and instructions whose interval overlaps zero effect are shown in the distinct noise-floor state rather than as a low score.
- **SC-005** (scoping on every number): 100% of reports and exported artefacts state the probe suite version and the model the numbers were measured on.
- **SC-006** (instant proof): A first-time visitor can read a full verdict on a recognisable published prompt with no run started and no compute on their part.
- **SC-007** (CLI/web parity): For the same prompt, settings, and seed, the CLI JSON verdict and the web verdict agree.
- **SC-008** (attention is never the verdict): On every surface, attention appears only as pre-screen or explainer; no surface presents an attention-only score as a verdict.
- **SC-009** (duel significance): Duel mode declares a winner only when the posterior probability of a difference outside the ROPE clears the configured threshold, and reports effect size and that posterior probability in every case, including null results.
- **SC-010** (comparison grid, no universal score): The model comparison grid shows per-model weights and never emits or implies a single cross-model prompt score.
- **SC-011** (CI gate works): CI mode exits non-zero for an edit that drops a load-bearing instruction past threshold or adds dead weight beyond budget, and exits zero for benign edits.
- **SC-012** (flagship published in full): The flagship vivid-versus-beige duel is published with full data regardless of outcome, including a null result.

## Assumptions

- **Release-to-priority mapping**: P1 stories are Release 1 (linter core, teardowns, CLI), P2 stories are Release 2 (duels, emphasis, position, comparison grid, diff, export), P3 stories are Release 3 (decay, CI, watch/API, methodology). Release boundaries are shipping order; Release 1 design (per-model result storage, suite versioning, report schema) anticipates the later releases.
- **Statistical machinery**: Bayesian throughout (see Clarifications 2026-08-20). Every weight carries a posterior credible interval; the noise-floor state is a credible interval overlapping zero effect; duel significance is a posterior probability outside a region of practical equivalence. This one approach is used for weights, duels, and many-instruction comparisons alike, which is why no multiple-comparison correction is needed.
- **Judge model for behavioural deltas**: resolved (see Clarifications 2026-08-20). Default judge is a separate local model, distinct from the subject, with judge noise folded into the posterior; a frontier paid API judge is an opt-in alternative that marks the run best-effort and waives same-seed reproducibility. An ensemble of judges remains an allowed future upgrade, not a Release 1 requirement. The subject model is always local.
- **Divergence blend**: resolved (see Clarifications 2026-08-20). A fixed, documented blend applied uniformly across probes, frozen after initial tuning and validated (not fitted) against the Gate A planted ground truth. Per-probe weighting and a learned combiner are documented future refinements only.
- **Segmentation model and fallback**: segmentation is performed by a small local model with a rules-plus-model hybrid, and manual merge/split is always available as the fallback when the model segments wrongly.
- **Model roster**: resolved (see Clarifications 2026-08-20). Release 1 subject model is Qwen2.5-1.5B-Instruct behind a model abstraction; the Release 2 grid is Qwen2.5-0.5B/1.5B/3B-Instruct (size sweep) plus one other-family instruct model (Llama-3.x-1B/3B-Instruct or Phi-class) for cross-family contrast, with the fourth pick confirmed at planning against the GPU budget.
- **Web demo compute**: resolved (see Clarifications 2026-08-20) to read-only. The public web demo serves pre-computed teardowns and published duels live; it never executes visitor prompts or hosts a GPU worker. Paste-your-own runs are local via the CLI or a local instance.
- **Runtime**: the model runtime is realistically Python (HuggingFace / PyTorch), but the CLI and report tooling install and run as a single command without the user hand-managing environments.
- **Openness**: the repository is public from day one and the methodology page ships with v1 (completed through Release 3); each release is accompanied by its article as part of that release's definition of done.
- **Teardown sourcing**: teardowns use only officially published or released prompts (the published Claude system prompt is fair game, plus a second well-known public one), each citing its source.
- **Reconsideration trigger**: if a credible open-source ablation-based prompt linter with published methodology ships first, the project pivots toward the CI/diff/decay layers and interoperates rather than duplicating.
