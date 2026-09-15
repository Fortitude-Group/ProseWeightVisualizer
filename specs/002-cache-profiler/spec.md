# Feature Specification: Cache Profiler (CacheScope)

**Feature Branch**: `002-cache-profiler`

**Created**: 2026-09-14

**Status**: Draft

**Input**: User description: `docs/brainstorm-cache-profiler.md`

## Overview

CacheScope is the **empirical** prompt-cache profiler, a second measurement axis on the Prose Weight Visualiser bench. Where the weight linter (feature `001`) answers *"which of my instructions do anything?"*, CacheScope answers *"which of my bytes cost me money for nothing?"* It captures a user's real Claude traffic locally, byte-diffs why each prompt-cache miss happened, reconciles that against what Anthropic actually reported and charged, attributes the avoidable waste to a cause (CRLF drift, a volatile header, tool churn, a genuine edit), and prices it. The headline capability: *"your CRLF line endings cost you £4.12 this month, and here is the byte that did it."*

Everything in this space today is static linting — rules about what *probably* breaks the cache. CacheScope is the version that measures what *actually* happened. Static byte-hygiene rules are kept, but reframed as **predictions the profiler later confirms with measurement**.

The scope is sequenced into three releases mapped to priorities P1 (Release 1), P2 (Release 2), P3 (Release 3), matching the `001` convention: release boundaries are shipping order, and R1 design anticipates R2/R3. This is a **sibling feature** that shares `001` infrastructure (report/export, CI, design tokens, the Anthropic SDK path) without modifying it; it is not a standalone tool.

## Clarifications

### Session 2026-09-14

- Q: Working name — the brief proposed "cacheline". → A: Renamed **CacheScope** ("cache line" collides with the CPU-cache term). Package `cache/`; CLI command group `proseweight cache <sub>`.
- Q: What are the capture paths and which lands when? → A: Two paths. A local recording proxy for PAYG-API traffic (Release 1) and ingest of Claude Code's on-disk session transcripts for subscription users (basic ingest Release 1, high-fidelity byte reconstruction Release 3). The author runs a Claude Code subscription, not PAYG, so transcript ingest is his primary path and is pulled into Release 1.
- Q: Cost is in pounds — but a subscription has no per-token bill. → A: The cost meter forks by billing model. PAYG shows **measured pounds** (`usage` tokens × pricing). Subscription shows **quota consumption** as the primary meter, with pounds surviving only as an explicitly-labelled **shadow-price counterfactual**, never a bill.
- Q: Use the cache-diagnostics beta? → A: Yes, as an opt-in checkbox setting, passive by default. It functions only on the PAYG proxy path; it cannot be applied to Claude Code subscription traffic, where reconciliation is usage-fields-only.
- Q: How is the divergence mapped onto the cache? → A: Onto Anthropic's real unit — **cache breakpoints** (up to 4 explicit, or automatic), each caching the whole prefix up to and including its block — not fictional fixed-size blocks. A prefix below the model's **minimum cacheable length** (512 / 1,024 / 2,048 / 4,096 tokens per model) is never cached, a state rendered distinctly from "cached then recomputed".
- Q: Currency/pricing? → A: GBP default, static stamped USD→GBP FX rate, editable. Pricing table seeded with current published PAYG rates as defaults; every figure stamps the pricing version, effective date, and FX date.
- Q: Does the cost engine need to be reusable elsewhere? → A: Yes. Its cost-analysis half is a candidate to transplant into **OmnisVigil** (a separate money-saving / model-routing product) later. The engine must be a self-contained, one-way-dependent core behind a versioned data contract; work in this repo is **additive only** and must not modify or break the `001` weight linter.
- Q: Feature placement? → A: A sibling feature `specs/002-cache-profiler/` sharing `001` infrastructure, not new requirements bolted onto `001`.
- Q: What defines "consecutive turns" for divergence pairing? → A: Turns are paired within a **cache lineage** — same source and model, sharing a leading-prefix family, time-ordered and bounded by the cache TTL (5-minute / 1-hour) — the relationship the cache itself would have formed, never global timestamp order across unrelated prompts. A turn with no eligible predecessor in its lineage yields no divergence record (it is a new/first-seen prefix, not a miss).
- Q: How does PAYG traffic reach the recording proxy? → A: A **local base-URL reverse proxy**. The user points the SDK at `localhost:<port>` via `ANTHROPIC_BASE_URL` (or `base_url=`); the proxy forwards to the real API and records the exact on-wire request bytes and the response `usage` (confidence `exact`). No TLS interception / CA-trust (MITM) is used; the proxy only sees traffic it is explicitly pointed at.
- Q: What backs the capture / ledger store? → A: **SQLite** for the append-only capture ledger and metadata (turns, cache lineages, divergence records, pricing stamps, period/cause/model rollups), plus a **content-addressed blob directory** for the exact prefix bytes. Retention prunes a blob while keeping its row (hash + cost metadata) for the longitudinal ledger. Single-file, no running service, additive to and distinct from `001`'s per-run JSON storage; shares the storage idiom the sibling OmnisRouter already uses (SQLite).
- Q: Where do the three views (heatmap, ledger, prediction-vs-measured) render, given the core must not import `web/` and `001`'s faceplate must not be modified? → A: As a **self-contained HTML/PNG export** produced by a separate brand-neutral rendering adapter over the versioned result contract — no new running service. Interactivity (clicking a miss to open the byte diff) is inline JS in the exported HTML, reusing the `001` self-contained-export *pattern* without modifying its modules. Rendering is always an adapter, never the core.
- Q: Relationship to the sibling OmnisRouter product (it is already a drop-in Anthropic-Messages routing proxy with prompt-cache translation and a Claude Code transcript `collect` mode)? → A: Capture is a **versioned contract, not a bundled server**. CacheScope defines a capture-ingestion contract (rendered-prefix blob + usage + model + timestamp + source + confidence) and ships a **self-contained Python reference proxy** that writes it, so R1 runs standalone with **no dependency on OmnisRouter**. OmnisRouter is named the **intended production capture source**: it emits the same contract from an opt-in, local-only byte-capture sink and the user then runs no second proxy. That sink is OmnisRouter-repo work, separately tracked and **out of scope here** — symmetric with OmnisVigil on the cost-output side. Runtime boundary is a language-neutral on-disk contract (OmnisRouter is .NET; CacheScope is Python); CacheScope consumes OmnisRouter's output and never embeds it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture real sessions locally (Priority: P1)

An engineer points CacheScope at their real Claude traffic and it accumulates an append-only local record of each request's rendered prompt and the cache-usage the response reported. A PAYG-API user runs their traffic through a local recording proxy; a Claude Code subscription user has their on-disk session transcripts ingested. Every capture stays on the machine, is labelled with its source and a reconstruction-confidence grade, and honours a retention setting.

**Why this priority**: Capture is the substrate every later capability consumes. Shipping it first means real data accumulates while the analysis layers are built (the same logic that puts per-model result storage in `001` Release 1). Without it there is nothing empirical to measure.

**Independent Test**: Route (or replay) two consecutive requests through the proxy, and separately ingest a Claude Code transcript; confirm each turn is stored with its rendered prefix, the `cache_creation_input_tokens` / `cache_read_input_tokens` / `input_tokens` it reported, its model, timestamp, source, and confidence grade, and that nothing was transmitted off the machine.

**Acceptance Scenarios**:

1. **Given** the recording proxy is running in front of the API, **When** a request and response pass through, **Then** the exact on-wire rendered prefix bytes and the response `usage` fields are stored append-only in the local capture store, tagged source `api_proxy`, confidence `exact`.
2. **Given** a Claude Code session transcript on disk, **When** it is ingested, **Then** each turn's available prefix content and `usage` are stored, tagged source `claude_code_transcript` with an explicit reconstruction-confidence grade below `exact`.
3. **Given** a retention setting of N days, **When** captures age past N days, **Then** their raw prefix bytes are pruned while their hashes and cost metadata are retained for the longitudinal ledger.
4. **Given** any capture or analysis operation, **When** it runs, **Then** no prompt content leaves the machine.

---

### User Story 2 - Static cache-hygiene lint without captured data (Priority: P1)

An engineer runs a fast lint over a `CLAUDE.md`, the machine-wide `~/.claude/CLAUDE.md`, or a set of `.kb/*.md` files and gets a list of predicted cache-hostility findings — CRLF/LF drift, trailing whitespace, non-`LC_ALL=C` concatenation order, volatile headers (`date:` / `version:` / `updated:` / timestamps in early lines) — each framed explicitly as a prediction the profiler will later confirm, with an estimated monthly cost. No captured data, no API, no model runtime required.

**Why this priority**: This is the zero-cost instant-proof surface and the CacheScope analogue of the linter's famous-prompt teardowns. It works offline on any file, including the read-only public demo, and gives the tool value on day one before any capture has accumulated.

**Independent Test**: Run the static lint on a `CLAUDE.md` seeded with a CRLF line, a trailing-whitespace line, and a `updated:` header in line 2; confirm each is reported as a distinct predicted finding with a rule id, file, line, and an estimated monthly cost, and that each is labelled a prediction rather than a measured fact.

**Acceptance Scenarios**:

1. **Given** a target file with known cache-hostile patterns, **When** the static lint runs with no captured data, **Then** each pattern is reported with its rule id, file, line/offset, and an estimated monthly cost.
2. **Given** the machine-wide `~/.claude/CLAUDE.md`, **When** it is passed as a target, **Then** it is linted the same as a project file.
3. **Given** any static finding, **When** it is presented, **Then** it is framed as a prediction ("the profiler will confirm this with measurement"), never as a measured verdict.

---

### User Story 3 - Divergence analysis of consecutive turns (Priority: P2)

For each consecutive pair of captured turns, CacheScope byte-diffs the two rendered prefixes, finds the first divergent byte offset, classifies the cause, and maps the offset onto the request's cache breakpoints to compute which breakpoints were forced to recompute, which survived, and which never cached because the prefix was below the model's minimum cacheable length. Clicking a miss opens the byte diff with the offending byte highlighted in context and the cause labelled.

**Why this priority**: This is the mechanism that turns raw captures into an explanation. It is the direct source of the "here is the byte that did it" claim, which only the local capture can supply (Anthropic's own diagnostics are content-free).

**Independent Test**: Feed two prefixes differing only by a single `\r\n` where the prior had `\n`; confirm the tool reports the exact first divergent byte offset, its line, the cause class `crlf_drift`, the set of breakpoints whose prefix reaches that offset, and a byte-diff view highlighting the byte.

**Acceptance Scenarios**:

1. **Given** two consecutive captured prefixes that differ, **When** divergence analysis runs, **Then** it reports the first divergent byte offset, the line, a cause classification, and the breakpoints invalidated.
2. **Given** a divergence, **When** its cause is classified, **Then** it is one of: CRLF/LF drift, trailing whitespace, volatile header, concatenation-order change, timestamp injection, tool-definition churn, model change, system-prompt change, or genuine content edit.
3. **Given** a prefix shorter than the subject model's minimum cacheable length, **When** it is analysed, **Then** it is reported as "never cached (below minimum)", visually distinct from "cached then recomputed".
4. **Given** a divergence caused by a genuine intended edit, **When** it is classified, **Then** it is marked non-avoidable and excluded from waste attribution.

---

### User Story 4 - Prediction versus measured reconciliation (Priority: P2)

Where the API reported actual cache numbers, CacheScope reconciles its own byte-level prediction against the measurement: the `usage` split (`cache_read_input_tokens` vs `cache_creation_input_tokens`), and, where the user opted into the cache-diagnostics beta, the reported `cache_miss_reason.type` and `cache_missed_input_tokens`. Agreements and disagreements between predicted and measured are a first-class view, not a debug tab.

**Why this priority**: The prediction-vs-measured comparison is what makes the tool trustworthy and is explicitly a headline feature, not a diagnostic aside. It is also the validity check on the whole instrument.

**Independent Test**: For a captured turn with a divergence and present `usage`/diagnostics, confirm the reconciliation view shows the predicted cause level beside the measured `cache_miss_reason.type` and the predicted recomputed tokens beside the measured missed tokens, and flags any mismatch distinctly.

**Acceptance Scenarios**:

1. **Given** a turn whose response carried `usage` cache fields, **When** reconciliation runs, **Then** predicted recomputed tokens are shown against the measured drop in `cache_read_input_tokens`.
2. **Given** the diagnostics beta was enabled on a PAYG turn, **When** reconciliation runs, **Then** the predicted divergence level is shown against the measured `cache_miss_reason.type`, and a level mismatch is flagged.
3. **Given** a subscription-sourced turn (no diagnostics available), **When** reconciliation runs, **Then** it proceeds on `usage` fields alone and states that diagnostics were unavailable, never treating "no measurement" as agreement.

---

### User Story 5 - Cost attribution and ledger (Priority: P2)

CacheScope prices each avoidable divergence and aggregates the waste by day/week/month and by cause class. Cost is grounded in measured tokens times a configurable per-model pricing table. The meter forks by billing model: a PAYG user sees measured pounds; a subscription user sees quota consumption as the primary meter with pounds shown as a labelled shadow-price counterfactual. Every figure is scoped to the pricing version, effective date, and FX date.

**Why this priority**: Pricing the waste is the reason the engineer opened the tool and the headline the whole product is built around. It depends on divergence analysis but is a distinct, demonstrable deliverable.

**Independent Test**: Given a month of captures with a recurring CRLF divergence, confirm the ledger reports a headline waste figure for that cause class, that a PAYG source shows it as measured pounds and a subscription source shows quota tokens plus a labelled shadow-price, and that each figure carries its pricing version, effective date, and FX date.

**Acceptance Scenarios**:

1. **Given** avoidable divergences over a period, **When** the ledger aggregates them, **Then** waste is summed by cause class and by day/week/month with a headline figure per cause.
2. **Given** a PAYG-sourced divergence, **When** its cost is computed, **Then** it is `recomputed_tokens × base_input_rate × (write_multiplier − read_multiplier)`, converted to GBP, presented as a measured cost.
3. **Given** a subscription-sourced divergence, **When** its cost is shown, **Then** quota consumption is the primary figure and any pound value is labelled a shadow-price counterfactual, never a bill.
4. **Given** any cost figure, **When** it renders, **Then** it states the pricing version, the effective date, and the FX date it was computed under.

---

### User Story 6 - Visualisation (Priority: P2)

CacheScope reuses the established visual language for three views: a **block-survival heatmap** (x = turns, y = cache breakpoints; cells coloured hit / recomputed / new / never-cached; clicking a miss opens the byte diff); a **cost ledger** (monthly stacked bars of waste by cause class, a headline figure, per-cause drill-down to the offending files/turns); and a **prediction-vs-measured** view (predicted breakpoint survival against actual cache-read tokens, with deltas flagged).

**Why this priority**: The views are what make the measurement legible and shareable, and they reuse the `001` report/export and side-by-side visual family shipping in the same release.

**Independent Test**: Render each of the three views from a captured dataset; confirm the heatmap y-axis is cache breakpoints with a distinct never-cached state, the ledger shows a headline figure with per-cause drill-down, and the prediction-vs-measured view flags a seeded delta.

**Acceptance Scenarios**:

1. **Given** a captured multi-turn dataset, **When** the heatmap renders, **Then** each cell is coloured hit / recomputed / new / never-cached and a miss cell opens the byte diff with the divergent byte highlighted and the cause labelled.
2. **Given** a month of attributed waste, **When** the ledger renders, **Then** it shows a stacked bar by cause class, a headline figure, and a drill-down to the offending files/turns.
3. **Given** turns with both predicted and measured data, **When** the prediction-vs-measured view renders, **Then** predicted survival is shown against actual cache-read tokens and deltas are flagged.

---

### User Story 7 - High-fidelity Claude Code reconstruction (Priority: P3)

Building on the Release 1 basic transcript ingest, CacheScope reconstructs the effective byte prefix per Claude Code turn (tools + system + `CLAUDE.md`/memory + history) and its breakpoints as faithfully as the transcript allows, surfacing reconstruction confidence explicitly and never presenting a hard figure without a confidence band. It calibrates the reconstruction against the transcript's own `usage`.

**Why this priority**: This is fidelity-risky and depends on a mature divergence/cost engine to be worth surfacing, so it lands last — but it upgrades the author's own primary path from usage-only to byte-level.

**Independent Test**: Reconstruct a Claude Code turn's prefix, confirm a confidence grade is attached, confirm predicted recomputed tokens are calibrated against the turn's measured `usage`, and confirm no figure is shown as exact.

**Acceptance Scenarios**:

1. **Given** a Claude Code transcript turn, **When** high-fidelity reconstruction runs, **Then** the reconstructed prefix and breakpoints carry an explicit confidence grade.
2. **Given** a reconstruction whose predicted recomputed tokens disagree with the measured `usage`, **When** it is presented, **Then** its confidence is lowered rather than the figure adjusted, and the figure is shown with a band.

---

### User Story 8 - CI cache-lint gate (Priority: P3)

A team runs `proseweight cache lint <file> --baseline <file>` in CI. The build fails when a commit introduces a cache-hostile change to a `CLAUDE.md` / `.kb` file, and the failure message states the estimated monthly cost of the regression. A GitHub Action wraps it, sharing the `001` CI lint infrastructure.

**Why this priority**: Prevention is the product wedge — failing the commit before the cost is incurred — but it depends on cost attribution and the shared `001` Release 3 CI infrastructure.

**Independent Test**: Commit a change that converts a file's line endings to CRLF and run the CI gate against a clean baseline; confirm a non-zero exit and a failure message naming the regression and its estimated monthly cost; run against a benign edit and confirm a zero exit.

**Acceptance Scenarios**:

1. **Given** a baseline and an edit that introduces a cache-hostile change, **When** the CI gate runs, **Then** it exits non-zero and reports the regression with its estimated monthly cost.
2. **Given** a benign edit within tolerance, **When** the CI gate runs, **Then** it exits zero.
3. **Given** a baseline whose pricing version or model differs from the current run, **When** the gate runs, **Then** the mismatch is reported as a confound, not a regression.

---

### User Story 9 - Methodology (Priority: P3)

Alongside the tool, the published methodology page gains a cache-cost section: how divergence is detected, how cost is measured versus attributed, the PAYG-versus-subscription meter fork, the breakpoint model and per-model minimums, and the known limitations (reconstruction fidelity, diagnostics-beta availability, pricing drift, amortisation).

**Why this priority**: Honesty and citation-bait; it ships in draft and completes as the releases mature, so its full form is a Release 3 deliverable.

**Independent Test**: Confirm the methodology page describes the divergence detection, the measured-cost/attributed-cause split, the meter fork, the breakpoint model, and the stated limitations.

**Acceptance Scenarios**:

1. **Given** the published methodology, **When** the cache-cost section is read, **Then** it states how cost is measured versus attributed, the meter fork, the breakpoint model, and the known limitations.

---

### Edge Cases

- **A subscription user has no proxy-able traffic**: capture falls to transcript ingest; the proxy path is inert and the tool says so rather than reporting an empty capture as an error.
- **The diagnostics beta returns `unavailable` or `previous_message_not_found`**: reconciliation proceeds on `usage` fields and records "no measurement", never counting it as agreement.
- **A prefix is below the model minimum**: reported as never-cached, distinct from recomputed; no waste is attributed to a block that was never eligible to cache.
- **Pricing or FX has drifted since a baseline**: a pricing-version or model mismatch is flagged as a confound, not a regression or a false cost change.
- **A divergence is a genuine intended edit**: classified non-avoidable and excluded from the waste ledger.
- **Raw prefix bytes pruned by retention**: longitudinal cost is still computed from retained metadata; the byte-diff view states the bytes are no longer available.
- **A write amortises over later reuse**: the per-event cost figure carries an amortisation caveat flag so it is not read as a precise net loss.
- **Reconstruction confidence is low**: the figure is shown with a band and never as exact; a subscription figure is never presented as a pound bill.

## Requirements *(mandatory)*

### Functional Requirements

**Capture**

- **FR-001**: The system MUST capture Claude traffic through at least two paths — a **local base-URL reverse proxy** for PAYG-API traffic (the SDK is pointed at `localhost:<port>` via `ANTHROPIC_BASE_URL`; the proxy forwards to the real API and records exact on-wire bytes; no TLS interception) and ingest of Claude Code on-disk session transcripts for subscription traffic — and MUST be designed so further capture sources can be added behind the capture-ingestion contract (FR-001a).
- **FR-001a**: Capture MUST be defined by a **stable, versioned, serialisable capture-ingestion contract** (the rendered-prefix reference, the `usage` fields, model, timestamp, source, and confidence grade) that any producer can write. CacheScope MUST ship a self-contained reference proxy (in this repository) that writes this contract and MUST NOT depend at runtime on any external product to capture. The sibling **OmnisRouter** product is the intended production capture source, emitting this contract from an opt-in local-only byte-capture sink; that sink lives in the OmnisRouter repository and is out of scope here (see Out of Scope).
- **FR-002**: Each capture MUST record the rendered prompt prefix (exact on-wire bytes on the proxy path; the best available reconstruction on the transcript path), the response cache-usage fields (`cache_creation_input_tokens`, `cache_read_input_tokens`, `input_tokens`, and the ephemeral 5-minute / 1-hour split where present), the model, and a timestamp.
- **FR-003**: Captures MUST be stored locally, append-only, and MUST honour a configurable retention setting that can prune raw prefix bytes while retaining hashes and cost metadata for the longitudinal ledger.
- **FR-004**: Every capture MUST be tagged with its source and a reconstruction-confidence grade (`exact` for the proxy path; a lower grade for reconstructed transcript data).
- **FR-005**: No captured prompt content or analysis MUST leave the machine.

**Static lint (prediction layer)**

- **FR-006**: The system MUST provide a static cache-hygiene lint that runs with no captured data over a `CLAUDE.md`, the machine-wide `~/.claude/CLAUDE.md`, or `.kb/*.md` files, detecting at least: CRLF/LF drift, trailing whitespace, non-`LC_ALL=C` concatenation order, and volatile headers (`date:` / `version:` / `updated:` / timestamps in early lines).
- **FR-007**: Every static finding MUST be framed as a prediction the profiler can later confirm with measurement, MUST carry a rule id, file, and line/offset, and MUST carry an estimated monthly cost.

**Divergence analysis**

- **FR-008**: The system MUST group captures into **cache lineages** (same source and model, sharing a leading-prefix family, time-ordered, bounded by the cache TTL) and, for each consecutive pair within a lineage, byte-diff the two rendered prefixes and report the first divergent byte offset and its line. Turns are never paired across lineages or by global timestamp order; a turn with no eligible predecessor in its lineage produces a new/first-seen state rather than a divergence.
- **FR-009**: The system MUST classify each divergence cause into at least: CRLF/LF drift, trailing whitespace, volatile header, concatenation-order change, timestamp injection, tool-definition churn, model change, system-prompt change, and genuine content edit.
- **FR-010**: The system MUST map a divergence offset onto the request's cache breakpoints (up to four explicit or automatic breakpoints, each caching the whole prefix up to its block) and compute which breakpoints were forced to recompute versus which survived. It MUST NOT model caching as fixed-size blocks.
- **FR-011**: The system MUST treat a prefix below the subject model's minimum cacheable length (per-model: 512 / 1,024 / 2,048 / 4,096 tokens) as never-cached, a state rendered distinctly from cached-then-recomputed.
- **FR-012**: The system MUST mark divergences caused by genuine intended edits (and intended model changes) as non-avoidable and exclude them from waste attribution.

**Reconciliation**

- **FR-013**: Where the API reported cache-usage numbers, the system MUST reconcile its predicted recomputed tokens against the measured change in `cache_read_input_tokens` / `cache_creation_input_tokens`, and surface the prediction-versus-measured comparison as a first-class view.
- **FR-014**: The system MUST support the cache-diagnostics beta (`cache-diagnosis-2026-04-07`) as an opt-in checkbox setting, passive by default, used only on the PAYG proxy path; when enabled it MUST reconcile the predicted divergence level against the measured `cache_miss_reason.type` and flag a level mismatch.
- **FR-015**: On subscription traffic (no diagnostics available), the system MUST reconcile on `usage` fields alone and MUST record "no measurement" rather than treating an absent diagnostic as agreement.

**Cost attribution**

- **FR-016**: The system MUST provide a configurable per-model pricing table carrying the base input rate, the cache write multipliers (5-minute and 1-hour), the cache read multiplier, the per-model minimum cacheable length, an effective date, a pricing version, and a "prices change, edit me" note, seeded with current published defaults.
- **FR-017**: For each avoidable divergence, the system MUST compute the wasted spend as the recomputed tokens (that would otherwise have been cache reads) times the difference between the write and read rates, grounded in measured usage where present.
- **FR-018**: The system MUST aggregate waste by cause class and by day / week / month, with a headline figure per cause.
- **FR-019**: The cost meter MUST fork by billing model: PAYG shows measured pounds; subscription shows quota consumption as the primary meter with pounds shown only as an explicitly-labelled shadow-price counterfactual, never as a bill.
- **FR-020**: Currency MUST default to GBP, configurable, using a static stamped USD→GBP FX rate; every cost figure MUST state its pricing version, effective date, and FX date.

**Visualisation**

- **FR-021**: The system MUST provide a block-survival heatmap with turns on the x-axis and cache breakpoints on the y-axis, cells coloured hit / recomputed / new / never-cached, where clicking a miss opens the byte diff with the divergent byte highlighted in context and the cause labelled.
- **FR-022**: The system MUST provide a cost ledger view: monthly stacked bars of waste by cause class, a headline figure, and per-cause drill-down to the offending files/turns.
- **FR-023**: The system MUST provide a prediction-versus-measured view showing predicted breakpoint survival against actual cache-read tokens, with deltas flagged.
- **FR-023a**: All three views MUST be delivered as a **self-contained HTML/PNG export** produced by a rendering adapter that consumes the versioned result contract, with any interactivity (click-a-miss to open the byte diff) inlined so no running service is required. The adapter MUST default to brand-neutral, themeable output (a Fortitude-branded theme is an optional adapter setting), MUST NOT be part of the transplantable core, and MUST NOT modify the `001` report/web modules (it may reuse their self-contained-export pattern).

**Claude Code reconstruction (high-fidelity)**

- **FR-024**: The system MUST reconstruct the effective byte prefix and breakpoints for Claude Code transcript turns as faithfully as the data allows, surface reconstruction confidence explicitly, and never present a reconstructed figure as exact or without a confidence band.

**CI gate**

- **FR-025**: The system MUST provide a CI command `proseweight cache lint <file> --baseline <file>` that exits non-zero when a commit introduces a cache-hostile change to a `CLAUDE.md`/`.kb` file, with the estimated monthly cost of the regression in the failure message, exits zero for benign edits, and reports a pricing/model mismatch against the baseline as a confound rather than a regression. It MUST share the `001` CI lint infrastructure and be wrappable by a GitHub Action.

**Methodology**

- **FR-026**: The system MUST publish a cache-cost methodology section describing divergence detection, the measured-cost/attributed-cause split, the PAYG-versus-subscription meter fork, the breakpoint model with per-model minimums, and the known limitations.

**Modularity and non-regression (transplant boundary)**

- **FR-027**: The cost-analysis core (capture store schema, divergence detectors, pricing table, cost attribution, ledger rollups, static-lint rules) MUST be a self-contained unit that does not depend on the `001` weight linter (its verdict, statistics, brand, web, or weight-measurement modules), so it can be reused by another product without modification.
- **FR-028**: The cost core MUST expose its results as a stable, versioned, serialisable data contract; rendering to any specific presentation MUST be a separate consumer of that contract, and the presentation MUST default to brand-neutral, themeable output.
- **FR-029**: All work for this feature MUST be additive to the repository — a new package, a new command group, new storage, and new tests — and MUST NOT modify or break the existing `001` weight-linter modules or their tests.

**Cross-cutting honesty**

- **FR-030**: Every figure MUST distinguish measured cost from attributed cause in its provenance, and MUST state the source and confidence of any reconstructed input, consistent with the project's "say what you verified versus what you assumed" standard.

### Key Entities *(include if feature involves data)*

- **CaptureSource**: where captures come from — the built-in reference reverse proxy, a Claude Code transcript, or an external producer (OmnisRouter) writing the capture-ingestion contract — with a reconstruction-confidence grade and a retention setting.
- **CapturedTurn**: one request/response — the rendered-prefix reference, the model, the timestamp, the cache-usage fields, any diagnostics result, and the source/confidence.
- **RenderedPrefix**: the content-addressed store of the exact prefix bytes, prunable by retention while its hash and metadata persist.
- **Breakpoint**: a resolved cache-control position — its level (tools / system / messages), the offset it caps, the tokens it caches, and whether it fell below the model minimum.
- **CacheLineage**: the grouping that makes two turns comparable — same source and model, a shared leading-prefix family, time-ordered and bounded by the cache TTL; divergence pairs and reuse are computed within a lineage, never across lineages.
- **DivergenceRecord**: a consecutive-turn comparison *within a lineage* — the first divergent offset, the cause class, the invalidated breakpoints, the predicted recomputed tokens, avoidability, and the reconciliation against measurement.
- **ModelPricing**: the editable per-model rate table (base input, write/read multipliers, minimum cacheable length, effective date, pricing version).
- **CostAttribution**: per-divergence waste — the billing model, the wasted spend (measured pounds or quota plus shadow-price), the cause class, the period buckets, and the amortisation caveat.
- **LedgerRollup**: aggregated waste by period, cause class, and model, driving the headline figure.
- **LintFinding**: a static prediction — rule id, file, line/offset, estimated monthly cost, confidence, and whether measurement later confirmed or refuted it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001** (byte precision): Given two captured prefixes differing by a single line-ending change, the tool identifies the exact first divergent byte offset and labels the cause CRLF/LF drift, in 100% of such cases.
- **SC-002** (measured versus attributed): 100% of cost figures state their pricing version, effective date, and FX date, and mark whether they are a measured cost (PAYG) or a shadow-price counterfactual (subscription).
- **SC-003** (prediction validity): On turns where measurement is present, the tool's predicted divergence level matches the measured `cache_miss_reason.type` in at least 90% of diverging turns; disagreements are surfaced, not hidden.
- **SC-004** (instant proof): A first-time user can run the static lint on a `CLAUDE.md` with no captured data, no API, and no model runtime, and receive predicted findings each carrying an estimated monthly cost.
- **SC-005** (nothing leaves the machine): No prompt content or analysis is transmitted off the machine during capture or analysis, verifiable by the absence of network egress from the analysis path.
- **SC-006** (subscription honesty): For subscription-sourced data, quota consumption is shown as the primary meter and no figure is presented as a pound bill; every reconstructed figure shows a confidence grade.
- **SC-007** (prevention gate): The CI gate exits non-zero on a cache-hostile edit with the estimated monthly cost in the message and exits zero on a benign edit, in 100% of the seeded test cases.
- **SC-008** (transplantable core): The cost core can be exercised by a consumer that imports only its versioned data contract and none of the `001` weight-linter modules, confirming the core is reusable without modification.
- **SC-009** (non-regression): The existing `001` weight-linter test suite passes unchanged after this feature is added, confirming the work is additive and non-breaking.
- **SC-010** (breakpoint fidelity): The tool never attributes waste to a prefix that was below the model minimum (never eligible to cache), and renders that state distinctly from cached-then-recomputed.

## Assumptions

- **Release-to-priority mapping**: P1 stories are Release 1 (capture + static lint), P2 stories are Release 2 (divergence, reconciliation, cost, visualisation), P3 stories are Release 3 (high-fidelity reconstruction, CI gate, methodology). Release boundaries are shipping order; Release 1 design (capture store schema, versioned result contract) anticipates the later releases.
- **Author's environment**: the author runs a Claude Code subscription, not PAYG, so Claude Code transcript ingest is his primary capture path and is pulled into Release 1; the recording proxy serves the PAYG audience. There is no gateway to tap.
- **Cost semantics**: on a subscription there is no per-token bill, so quota consumption is the real meter and pounds are a labelled counterfactual; on PAYG pounds are the measured cost. This fork is a first-class design constraint, not a display option.
- **Cache mechanism** (external facts CacheScope depends on): caching is at up to four breakpoints (or automatic placement) in tools → system → messages order; each breakpoint caches the whole prefix up to its block; the minimum cacheable prefix is per-model (512 / 1,024 / 2,048 / 4,096 tokens); cache reads price at 0.1× base input (0.025× for the lowest-latency models), 5-minute writes at 1.25×, 1-hour writes at 2×; the `usage` fields report the real token split.
- **Diagnostics beta**: `cache-diagnosis-2026-04-07` reports only the level of the first divergence and a byte-derived magnitude, never the content (fingerprints are hashes), is Claude-API-only, has short fingerprint retention, and is best-effort — so it is an optional corroborator, never a dependency, and is unavailable on subscription traffic.
- **Pricing/FX**: pricing and FX are user-editable, seeded with current published defaults, and every figure is stamped with the pricing version, effective date, and FX date; drift is treated as a confound, not a regression.
- **Storage**: captures live in a **local SQLite** append-only ledger (turns, cache lineages, divergence records, pricing stamps, period/cause/model rollups) with a **content-addressed blob directory** for prefix bytes; retention prunes a blob while retaining its row. Single-file, no running service, distinct from and additive to the `001` per-run JSON storage; nothing leaves the machine. SQLite is also the sibling OmnisRouter's storage idiom.
- **Transplant to OmnisVigil**: the cost-analysis core is designed to be lifted into OmnisVigil (a separate money-saving / model-routing product) later via its versioned data contract; the OmnisVigil-side refactor is out of scope here, and all work in this repo is additive and non-breaking to `001`.
- **Convergence with OmnisRouter (capture side)**: OmnisRouter is an existing Fortitude sibling product — a drop-in base-URL LLM routing proxy that already speaks Anthropic Messages with prompt-cache translation and already has a Claude Code transcript `collect` mode, single-process + SQLite, feeding OmnisVigil. It is the intended production capture source for CacheScope's PAYG path. The two are decoupled by the versioned capture-ingestion contract (FR-001a) and a language-neutral on-disk boundary (OmnisRouter is .NET 10; CacheScope is Python): CacheScope consumes OmnisRouter's emitted captures and never embeds it, and R1 ships a standalone reference proxy so it does not depend on OmnisRouter being present. The end-to-end Fortitude shape is **OmnisRouter (capture) → CacheScope cost core (analysis) → OmnisVigil (cost/routing)**.
- **Shared infrastructure**: CacheScope reuses the `001` report/export, CI lint, design tokens, and the already-wired Anthropic SDK path, consuming them as a sibling feature rather than modifying them.

## Out of Scope

- Any modification to the `001` weight linter, its report schema types, its web faceplate, or its tests (this feature is additive only).
- The OmnisVigil-side integration and any OmnisVigil-specific refactor (a later exercise in that product).
- The OmnisRouter-side byte-capture sink that emits the capture-ingestion contract (a later exercise in the OmnisRouter repository, separately tracked); this feature defines and consumes the contract and ships its own reference proxy, but does not build OmnisRouter's producer.
- Profiling caches of non-Anthropic providers as a primary path (the byte-hygiene static lint is provider-agnostic, but measured divergence/cost targets Anthropic caching); other providers may be a future extension.
- Modifying a user's live requests beyond the opt-in diagnostics beta header; the profiler is passive by default.
- Auto-fixing cache-hostile files; CacheScope reports and predicts, and the CI gate blocks, but it does not rewrite the user's prompts (mirroring the `001` no-rewrite stance).
- Hosted multi-tenant service, accounts, or billing; the profiler is single-tenant and local, and the public demo is read-only static content.
