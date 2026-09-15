# BRAINSTORM — CacheScope: the empirical cache profiler (module of Prose Weight Visualiser)

Folder: `ProseWeightVisualiser` | Status: R&D BUILD — folds into the existing three-release plan, nothing dropped
Companion to: [`brainstorm-prose-weight.md`](./brainstorm-prose-weight.md) (the linter/attnscope/attnduel brainstorm). Read that first.
Use with: `/speckit-specify` — this is the pre-spec brainstorm for a **second feature** (`specs/002-cache-profiler/`) that shares the `001` engine, report, CI and design infrastructure. It is not a standalone tool.

---

## One-liner

Everything in the prompt-cache space today is **static linting**: rules about what *probably* breaks Anthropic's prefix cache. CacheScope is the **empirical** version. It captures your real API traffic, byte-diffs why each cache miss happened, reconciles that against what Anthropic actually charged and actually reported, and prices the avoidable waste in pounds. The headline capability: *"your CRLF line endings cost you £4.12 this month, and here is the byte that did it."*

Where the weight linter answers *"which of my instructions do anything?"*, CacheScope answers *"which of my bytes cost me money for nothing?"* — same bench, same honesty discipline, different instrument.

## Working-name decision (the brief asked for alternatives)

**Recommendation: rename "cacheline" → `CacheScope`.** "Cache line" is an established CPU-architecture term (the 64-byte unit of a CPU cache) — it collides head-on with an unrelated, famous concept and will mislead every engineer who reads it. `CacheScope` instead sits in the project's existing instrument family (`attnscope`, and the "scope = measurement instrument" register the whole tool leans on), and reads as *scan/measure*, which is what it does.

- **Package**: `src/proseweight/cache/` (short, obvious, no collision inside the tree).
- **CLI**: a command *group* `proseweight cache <sub>` (`capture` / `analyse` / `ledger` / `lint`), matching the existing single-verb command surface (`scan`, `duel`, `diff`, `lint`, `export`, `serve`, `web`) without overloading the bare `lint` (which is the *weight* CI gate).
- **Product/marketing name**: **CacheScope**. The cost view is branded the **ledger**; the byte view the **diff**; the survival view the **heatmap**.
- Alternatives, if the cost story should lead over the measurement story: **CacheLedger** (leans into pounds), **PrefixMeter** (leans into the instrument). I'd keep CacheScope and let "ledger" be the sub-view.

---

## How it folds into the existing three releases

CacheScope is a **new measurement axis on the existing bench**, not a parallel tool. It displaces nothing in the `001` plan; it *extends* shared infrastructure. The fold below states, per capability, which release it lands in and what it extends.

| Capability (from brief) | Lands in | Extends / reuses | Displaces |
|---|---|---|---|
| **1a. Capture — API recording proxy** (PAYG-API users) | **R1** | New `cache/` package + SQLite store; the Anthropic SDK + usage-reporting already wired for frontier subjects (`engine/anthropic_backend.py`) | nothing |
| **1b. Capture — Claude Code transcript ingest** (subscription users, incl. Rob) | **R1 basic / R3 high-fidelity** | The R1 capture store; JSONL transcripts under `~/.claude/projects/<slug>/` | nothing |
| **2. Divergence analysis** | **R2** | A **copied** byte-offset/round-trip contract (not a `segmentation/` import — see *Portability*); its own result schema | nothing |
| **3. Cost attribution** | **R2** | The report schema; the token-cost framing the linter already uses for dead weight | nothing |
| **4. Visualisation** | **R2** | The report/export infra (self-contained HTML + PNG), the duel-style **side-by-side** visual language, the teal instrument-faceplate design tokens | nothing |
| **5a. Static lint pass** | **R1** | Pure byte analysis, dependency-free — the CacheScope analogue of the linter's *famous-prompt teardowns* (instant proof, zero capture) | nothing |
| **5b. CI gate + GitHub Action** | **R3** | **The visualiser's R3 CI infrastructure (FR-031, `ci/lint.py`, `ci/action/action.yml`)** — the brief explicitly asks to share this | nothing |
| Methodology (cache-cost section) | **R3** | The R3 methodology page (FR-033) | nothing |

**Why this sequencing.** It mirrors the `001` logic exactly: *ship the data substrate first so real data accumulates while the analysis layers are built* (the same reason `001` puts per-model result storage in R1 to anticipate the R2 grid). Capture + static lint in R1 give an immediate, honest, zero-cost demo surface. The headline — divergence, pounds, heatmap — is the R2 payload, shipping alongside the visualiser's own R2 *diff/comparison/export* work, which is the same visual family. The prevention/CI story and the *high-fidelity* Claude Code reconstruction land in R3 on top of a mature engine, sharing the CI infrastructure already planned there.

**Subscription vs PAYG (settled 2026-09-14 — this reshapes R1).** The author runs a Claude Code **subscription**, not PAYG API calls. That has three consequences the design must honour, not paper over:
1. **The proxy is inert for subscription users.** A recording proxy taps PAYG `api.anthropic.com` traffic; a subscription has none to intercept. The only supported local record of subscription traffic is the **Claude Code transcripts on disk** (`~/.claude/projects/<slug>/*.jsonl`, which carry per-message `usage`). So a **basic transcript ingest moves into R1** (so the author can dogfood day one); the proxy stays R1 for the PAYG audience the `001` spec targets; the *high-fidelity reconstruction + confidence grading* stays R3.
2. **Cost forks.** PAYG users get **measured pounds** (`usage` tokens × pricing). Subscription users' real meter is **quota consumption** (tokens against the 5-hour/weekly limits — "a cache miss makes you hit your limit sooner"), with pounds surviving as a clearly-labelled **PAYG shadow-price counterfactual**, never presented as a bill.
3. **The diagnostics beta is PAYG-only.** The `cache-diagnosis-2026-04-07` header can't be injected into Claude Code's own requests, so on transcript ingest the reconciliation is **usage-fields-only**; the diagnostics corroboration applies only to the proxy path.

### Release 1 — Capture + static lint

- **Cap 1a — API recording proxy** (PAYG-API users). A local recording proxy (loopback) that sits in front of `api.anthropic.com`, logging each request's **exact on-wire rendered bytes** (post-serialisation — the bytes the cache actually hashes) plus the response `usage` fields (`cache_creation_input_tokens`, `cache_read_input_tokens`, `input_tokens`, `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`, `output_tokens`), the `model`, the `id`, and a timestamp. Append-only SQLite; retention setting; **nothing leaves the machine**. An optional SDK-wrapper path is offered as a convenience but flagged lower-fidelity for byte-level claims (it may see pre-serialisation objects, not on-wire bytes).
- **Cap 1b (basic) — Claude Code transcript ingest** (subscription users — the author's own path). Read the JSONL transcripts Claude Code writes under `~/.claude/projects/<slug>/`, pulling each turn's `usage` (including `cache_read`/`cache_creation` tokens) and as much of the effective prefix as the transcript exposes. R1 ships the *basic* ingest — enough to build a real ledger from real sessions on day one; the *high-fidelity* reconstruction (exact byte prefix + breakpoints + confidence grading) is R3. Reconciliation here is **usage-fields-only** (no diagnostics beta on subscription traffic).
- **Cap 5a — static lint pass.** The Substack rules, absorbed and **reframed as predictions**: CRLF/LF drift, trailing whitespace, `LC_ALL=C` concatenation order, volatile headers (`date:` / `version:` / `updated:` / timestamps in early lines), file-order instability. Runs with **no captured data**, so it works offline on any target: the project `CLAUDE.md`, the **machine-wide `~/.claude/CLAUDE.md`** (the global user instructions — a large, high-value dogfood target), and `.kb/*.md`. It's also the natural CacheScope **teardown** for the read-only public demo (lint a well-known public `CLAUDE.md`, show predicted shadow-price/month, no execution, no API — consistent with FR-037). Every rule is explicitly *"a prediction the profiler will later confirm with measurement,"* not a verdict.

### Release 2 — Divergence analysis + cost attribution + visualisation (the headline)

- **Cap 2 — divergence analysis.** For each consecutive `(prev, curr)` captured turn pair: byte-diff the two rendered prefixes, find the **first divergent byte offset**, classify the cause (detectors below), and — corrected to the real mechanism — map that offset onto Anthropic's **cache breakpoints** (not fictional fixed blocks): compute which breakpoints' prefixes *contain* the offset and were therefore forced to recompute, versus which survived, versus which never cached at all because the prefix fell below the model's **minimum cacheable length**.
- **Cap 2 (reconciliation) — prediction vs measured, first-class.** Reconcile our byte-level *prediction* against Anthropic's *measurement*: the `usage` split (the real money) and, where the user opts into it, the `cache-diagnosis-2026-04-07` beta's `cache_miss_reason.type` + `cache_missed_input_tokens`. Agreements and — especially — **disagreements** are a headline view, not a debug tab.
- **Cap 3 — cost attribution.** A user-editable pricing table per model; wasted spend per avoidable divergence; aggregation by day/week/month by cause class; GBP default, configurable.
- **Cap 4 — visualisation.** Three views (heatmap / ledger / prediction-vs-measured), detailed below, reusing the R2 report + export + side-by-side visual language.

### Release 3 — Claude Code ingest + CI gate + methodology

- **Cap 1b (high-fidelity) — Claude Code reconstruction.** Building on the R1 basic ingest, reconstruct the effective *byte* prefix per turn (tools + system + `CLAUDE.md`/memory + history) and its breakpoints as faithfully as the data allows — with **reconstruction confidence surfaced explicitly** in the UI, never priced as a hard figure without a confidence band. Calibrated against the transcript's own `usage` fields. (The exact transcript schema is an implementation-time *verify-first* item, not an assumption.)
- **Cap 5b — CI gate.** `proseweight cache lint <file> --baseline <file>` sharing the FR-031 CI infrastructure: exit non-zero when a commit introduces a cache-hostile change to `CLAUDE.md`/`.kb`, with the **estimated monthly cost of the regression in the failure message**. A GitHub Action wraps it, alongside the weight-CI action.
- **Methodology.** Extend the R3 methodology page with the cache-cost measurement method, the measured-vs-attributed split, and the honesty limits.

---

## The spine: measured cost, attributed cause (and why the byte can only come from us)

This is the design's load-bearing idea, and it comes straight from the mechanism, so state it plainly.

- **Anthropic tells you the cost, not the byte.** The `usage` fields give the *real* token split — `cache_read_input_tokens` vs `cache_creation_input_tokens` vs `input_tokens` — i.e. the actual money. The `cache-diagnosis` beta adds the *level* of the first divergence (`system` / `tools` / `messages` / `model`) and a *magnitude* estimate (`cache_missed_input_tokens`, byte-derived, "magnitude not billing"). But its fingerprints are **hashes and token-count estimates only — never raw content**. So Anthropic *structurally cannot* show you the offending byte.
- **We hold the bytes, so we can point at the byte.** Because Cap 1 captured the exact rendered prefix locally, only CacheScope can byte-diff two turns and say *"offset 4,193, a `\r\n` where turn N had `\n`, inside `CLAUDE.md` line 12."* This is why local capture is load-bearing and not merely convenient.
- **Therefore: the cost is measured, the blame is attributed.** The cost comes from *measured* `usage` tokens × the pricing table (grounded, not modelled). The *cause* attribution — which byte, which class, which file — is our local prediction. The two are shown as distinct provenance, exactly matching the project's "say what you verified vs what you assumed" ethos. The reconciliation view is where the two meet: our predicted level should equal `cache_miss_reason.type`; our predicted recomputed tokens should track `cache_missed_input_tokens` and the drop in `cache_read_input_tokens`. When they don't, that disagreement is the interesting finding.

**The cost meter forks by billing model — and the tool must say which it is showing.**
- **PAYG API:** the meter is literal **pounds** — `recomputed_tokens × base_input_rate × (write_mult − read_mult)`, converted USD→GBP. This is the `001` prod-system-prompt audience.
- **Subscription (Claude Code Max/Pro — the author):** there is no per-token bill, so the primary meter is **quota consumption** — recomputed tokens spent against the 5-hour/weekly limits ("this cache miss burns X% of your window; you hit the wall sooner"). Pounds still appear as a **shadow-price counterfactual** ("≈ £4.12 of API-equivalent waste this month"), which is vivid and true but is **labelled a counterfactual, never a bill**. The tool detects the source (`CaptureSource.kind`) and renders the correct meter with the correct framing; it never shows a subscription user a pound *bill* they didn't incur.

### Divergence cause detectors (Cap 2)

Byte/line detectors, each emitting a cause class and a confidence:

`crlf_drift` · `trailing_whitespace` · `volatile_header` (date/version/updated/timestamp in early lines) · `concat_order_change` (file-ordering instability) · `timestamp_injection` · `tool_definition_churn` (added/removed/reordered tools, or non-deterministic `input_schema` serialisation) · `model_change` · `system_prompt_change` · `genuine_content_edit` (the residual: a real, intended edit — never flagged as waste).

The first four-plus map cleanly onto Anthropic's four `*_changed` levels for reconciliation: our `system_prompt_change` / `volatile_header` / `timestamp_injection` should surface as `system_changed`; `tool_definition_churn` as `tools_changed`; edits to earlier history as `messages_changed`; a router/fallback swap as `model_changed`.

### Corrected mechanism model (challenging the brief)

The brief's "cache blocks" language must be re-modelled to Anthropic's actual unit, or the arithmetic will be wrong:

- **Breakpoints, not fixed blocks.** Up to **4** explicit `cache_control` breakpoints (or automatic placement, 20-block lookback). A cached entry is *the whole prefix up to and including a breakpoint block*. A divergence at offset *X* invalidates **every breakpoint whose prefix reaches offset *X* or beyond** — i.e. that breakpoint and all later ones. The heatmap's y-axis is therefore **breakpoints** (tools-breakpoint, system-breakpoint, history-breakpoints), not synthetic 1024-token rows.
- **Minimum cacheable prefix is per-model** — 512 tokens (Fable 5.1 / Mythos 5.1 / Opus 5 / Fable 5 / Mythos 5), 1,024 (Opus 4.8 / Sonnet 5 / Sonnet 4.6 / …), 4,096 (Opus 4.6 / 4.5 / Haiku 4.5), 2,048 (Haiku 3.5). A prefix below the threshold is **never cached** ("no error is returned") — that's a distinct state from "cached then recomputed," and must render distinctly (it echoes the linter's noise-floor honesty: *don't dress up "never eligible" as "lost"*).
- **Read/write multipliers**: cache read `0.1×` base input (`0.025×` for Fable 5.1 / Mythos 5.1); 5-minute write `1.25×`; 1-hour write `2.0×`. These, and the per-model min-threshold and base rates, live in the editable pricing table — never in logic.

---

## Portability & the OmnisVigil transplant boundary (settled 2026-09-14)

The cost-analysis half of CacheScope is a candidate to lift into **OmnisVigil** later — that product is about saving money and routing to cheaper models, and CacheScope's divergence/cost/ledger data is a natural routing input. So design for transplant **now**, but **additively — nothing in the existing `proseweight` app changes or breaks**, and no OmnisVigil-specific refactor happens in this project (Rob does that on the OmnisVigil side later).

**The transplant unit** (lifts out clean) vs **the proseweight glue** (stays behind):

| Lifts out (portable core) | Stays behind (proseweight glue) |
|---|---|
| The capture **store schema** + the SQLite/blob layer | The `proseweight cache …` CLI wiring |
| The **divergence detectors** (byte-diff → offset → cause class) | The FastAPI faceplate + teal Fortitude chrome |
| The **pricing table** + **cost attribution** + **ledger rollups** | The self-contained-HTML/PNG proseweight report renderer |
| The **static-lint rule engine** | The read-only public-demo teardown page |
| A **stable serialisable result contract** (dataclasses → JSON) | The `001` weight-linter entirely |

**Rules that keep it transplantable:**

1. **One-way dependency, no back-reference to the linter.** The portable core (`src/proseweight/cache/core/`) imports only stdlib + its own store + a numeric helper. It **must not import** `verdict/`, `stats/`, `report/brand`, `web/`, or the weight `engine/`. The transplant is then `cp -r cache/core` + wire two adapters — not an untangling job.
2. **Reuse the byte-offset idea by a *small copied contract*, not a package import.** The design earlier said CacheScope "extends" the `001` segmentation offset machinery. Tightened: the core defines its own tiny `ByteSpan`/offset protocol (a few fields) and **copies** the round-trip helper rather than importing `segmentation/`. Reusing a 20-line helper is cheap; importing the whole segmentation package would chain the transplant to Qwen/markdown-it/pysbd it doesn't need. (Where a shared contract is genuinely stable and small, a thin `proseweight`-side adapter maps to it — the coupling lives in the adapter, never the core.)
3. **Rendering is an adapter, not the core.** The cost engine emits a **stable serialisable result** (versioned dataclasses → JSON — the ledger, the divergence records, the attribution). proseweight renders it to HTML/PNG; OmnisVigil consumes the same JSON into its own dashboard components. The core produces *data*, never HTML.
4. **A single façade / port.** Expose the whole core behind one module (`cache.core.api`: `ingest()`, `analyse()`, `ledger()`, `lint()`), SemVer'd like the other `001` contracts (Principle II). OmnisVigil imports that one surface; it never reaches into internals.
5. **Brand-neutral, token-themed views.** The proseweight views theme via CSS tokens and the existing render-time `brand=True` toggle (`report/brand.py`) — the cost views default to brand-neutral so OmnisVigil restyles without forking. No teal-faceplate hardcoding in the cost templates.
6. **Additive-only in this repo.** New `cache/` package, new `proseweight cache` subcommand group, new SQLite file, new tests. **Zero edits** to existing weight-linter modules, the report schema types they own, or their tests. If a genuine shared seam is ever needed, it's introduced as a *new* interface both sides implement, not a change to existing behaviour.

This costs nothing here (it's just where the import arrows point and what the core returns) and turns the later OmnisVigil integration from a rewrite into a copy-plus-two-adapters.

## Data model (captures, divergence, cost)

SQLite, append-only, local only. Field types language-agnostic, in the style of [`specs/001-.../data-model.md`](../specs/001-prompt-weight-linter/data-model.md). **Storage-choice note:** the `001` engine stores weight runs as per-run JSON; CacheScope stores *time-series across many turns*, which is append-heavy and query-by-period — SQLite is the justified-complexity choice (Principle V) and is additive, not a replacement. Rendered prefixes are big and sensitive, so they live in a **content-addressed blob store** (sha256-keyed, gzipped) that the retention policy can prune independently of the metadata.

### CaptureSource
| Field | Type | Notes |
|---|---|---|
| `source_id` | string | |
| `kind` | enum | `api_proxy \| sdk_wrapper \| claude_code_transcript` |
| `reconstruction_confidence` | enum | `exact` (proxy, on-wire bytes) `\| high \| medium \| low` (reconstructed) — drives UI framing |
| `label` | string? | e.g. "prod agent", "my CC sessions" |
| `retention_days` | int | per-source retention for raw blobs |

### CapturedTurn
One captured API request + its response usage. The reproducibility/analysis unit.
| Field | Type | Notes |
|---|---|---|
| `turn_id` | string | |
| `source_id` | string | → CaptureSource |
| `session_id` | string? | groups a conversation |
| `turn_index` | int | order within session |
| `ts` | timestamp | request-start (cache lifetime is measured from here) |
| `model` | string | e.g. `claude-opus-4-8` |
| `prefix_blob_hash` | string | sha256 of the exact rendered prefix bytes → PrefixBlob |
| `breakpoints` | Breakpoint[] | resolved `cache_control` positions (byte offset + level) |
| `usage_cache_creation` | int | `cache_creation_input_tokens` |
| `usage_cache_read` | int | `cache_read_input_tokens` |
| `usage_input` | int | `input_tokens` (only tokens **after the last breakpoint**) |
| `usage_5m` / `usage_1h` | int? | `cache_creation.ephemeral_5m/1h_input_tokens` |
| `usage_output` | int | |
| `response_id` | string | the API `id`, keys the diagnostics fingerprint |
| `diag_previous_id` | string? | `diagnostics.previous_message_id` sent (if opted in) |
| `diag_miss_type` | enum? | `model_changed \| system_changed \| tools_changed \| messages_changed \| previous_message_not_found \| unavailable \| null` |
| `diag_missed_tokens` | int? | `cache_missed_input_tokens` (magnitude, byte-derived) |
| `reconstruction_confidence` | enum | copied/refined from source; per-turn |

### PrefixBlob (content-addressed)
| Field | Type | Notes |
|---|---|---|
| `blob_hash` | string | sha256, primary key — dedupes identical prefixes across turns |
| `bytes_gz` | blob | gzipped exact rendered prefix |
| `byte_len` | int | |
| `captured_ts` | timestamp | |
| `pruned` | bool | true once retention drops the bytes; hash + metadata survive for longitudinal cost |

### Breakpoint
| Field | Type | Notes |
|---|---|---|
| `turn_id` | string | |
| `index` | int | 0–3 |
| `level` | enum | `tools \| system \| messages` (creation order) |
| `end_offset` | int | byte offset of the block it caps |
| `prefix_tokens` | int | tokens in the prefix it caches |
| `below_min_threshold` | bool | prefix shorter than the model minimum → never cached |

### DivergenceRecord
One consecutive `(prev_turn, curr_turn)` comparison — the core analytical object.
| Field | Type | Notes |
|---|---|---|
| `div_id` | string | |
| `prev_turn_id` / `curr_turn_id` | string | |
| `first_divergent_offset` | int? | byte offset of the first differing byte (null if identical) |
| `first_divergent_line` | int? | line in the reconstructed prefix, for the UI |
| `level` | enum | `tools \| system \| messages \| model` — our predicted level |
| `cause_class` | enum | the detector output (see list above) |
| `context_before` / `context_after` | string | snippet around the byte, for the diff view |
| `predicted_breakpoints_invalidated` | int[] | breakpoint indices whose prefix reaches the offset |
| `predicted_recomputed_tokens` | int | tokens that were reads last turn and are recomputed this turn |
| `avoidable` | bool | false for `genuine_content_edit` / `model_change` you intended |
| `confidence` | float | detector confidence |
| **reconciliation** | | |
| `measured_cache_read_delta` | int | `prev.usage_cache_read − curr.usage_cache_read` |
| `measured_diag_type` | enum? | `curr.diag_miss_type` |
| `measured_missed_tokens` | int? | `curr.diag_missed_tokens` |
| `agreement` | enum | `agree \| level_mismatch \| magnitude_mismatch \| no_measurement` |

### ModelPricing (editable table — "prices change, edit me")
| Field | Type | Notes |
|---|---|---|
| `model` | string | |
| `base_input_rate` | float | currency per 1M input tokens (source currency, USD) |
| `cache_read_mult` | float | `0.1` default (`0.025` Fable 5.1 / Mythos 5.1) |
| `cache_write_5m_mult` | float | `1.25` |
| `cache_write_1h_mult` | float | `2.0` |
| `min_cache_tokens` | int | 512 / 1024 / 2048 / 4096 per model |
| `effective_date` | date | stamped onto every £ figure |
| `pricing_version` | string | so a rate change is a detectable confound, like `blend_config` in `001` |
| `source_note` | string | default: "Prices change — edit me. Verified <date>." |

**Seeded defaults (settled 2026-09-14):** ship the *current published PAYG rates* as the shadow-price table (e.g. Opus 5 base input $5 / read $0.50 / 5m-write $6.25 / 1h-write $10 / output $25 per MTok; Sonnet, Haiku, Fable per their published rates) — the author's call is "take the current default rate, it doesn't change much." Still fully editable; the "edit me" note and `effective_date` stamp remain.

### CostAttribution
Derived from a DivergenceRecord + measured usage + pricing. **Cost from measurement, cause from attribution.**
| Field | Type | Notes |
|---|---|---|
| `div_id` | string | |
| `model` | string | |
| `recomputed_tokens` | int | grounded in measured `cache_creation`/`input` where present, else predicted |
| `write_multiplier_used` | float | `1.25`/`2.0` picked from the *measured* 5m/1h split, not assumed |
| `billing_model` | enum | `payg \| subscription` — from `CaptureSource.kind`; decides which meter is primary |
| `wasted_spend_src` | float | `recomputed_tokens × base_input_rate × (write_mult − cache_read_mult)` (source currency) |
| `wasted_spend_gbp` | float | converted at `fx_rate`; for `subscription` this is the **shadow-price counterfactual**, flagged as such in the UI |
| `wasted_quota_tokens` | int | primary meter for `subscription`: recomputed tokens spent against the rate-limit window |
| `fx_rate` / `fx_date` | float / date | USD→GBP, stamped |
| `cause_class` | enum | attribution |
| `period_day` / `period_week` / `period_month` | date | rollup buckets |
| `amortisation_caveat` | bool | true when a write may be reused later (see risk 6) |

### LedgerRollup
`(period, cause_class, model)` → `SUM(wasted_spend_gbp)`; drives the headline figure and the stacked bars.

### LintFinding (static, no capture)
The prediction→confirmation bridge.
| Field | Type | Notes |
|---|---|---|
| `finding_id` | string | |
| `rule_id` | enum | `crlf \| trailing_ws \| sort_order \| volatile_header \| concat_order` |
| `file` / `line` / `offset` | string / int / int | |
| `predicted_monthly_cost_gbp` | float? | estimate for the CI failure message |
| `confidence` | float | |
| `confirmed_by_measurement` | enum | `null \| confirmed \| refuted` — set once a matching DivergenceRecord is measured |

---

## Risk register (one page)

| # | Risk | Severity | Mitigation / decision |
|---|---|---|---|
| 1 | **Reconstruction fidelity (Claude Code path).** We cannot perfectly reproduce the exact bytes/breakpoints Claude Code sent — hidden system content, tool-schema serialisation, memory-injection order. **This is now the author's *primary* path (subscription), so it carries more weight than first assumed.** | High | For **PAYG** the proxy is the ground-truth path (`reconstruction_confidence = exact`). For **subscription** the transcript is all there is, so: grade every reconstruction, **never show a hard figure without a confidence band**, calibrate predicted-recomputed against the transcript's own `usage`, and lower the confidence when they disagree rather than fudging the number. The subscription meter is *quota*, and pounds are shadow-priced with an explicit band — which absorbs reconstruction error honestly. **Accept** the residual as a labelled limitation. |
| 2 | **Cache-diagnostics beta instability *and PAYG-only availability*.** `cache-diagnosis-2026-04-07` — "field names and semantics may change"; Claude API only (not Bedrock/Vertex/Foundry); short fingerprint retention; best-effort (`unavailable`, `cache_miss_reason: null`). **Cannot be used on Claude Code subscription traffic at all** (no header injection), i.e. unavailable to the author's own path. | Medium | Diagnostics is an **optional corroborator, never a dependency**. The core (byte-diff + `usage` fields) works without it, and the subscription path relies on `usage` fields alone by design. Expose it as a **checkbox setting** (per Q4) that only functions on the proxy path; isolate it behind an adapter keyed on the pinned beta header; treat `unavailable`/`previous_message_not_found` as "no measurement," not "agreement." |
| 3 | **Pricing drift.** Rates, multipliers (Fable/Mythos read `0.025×`), and per-model min-thresholds change. | Medium | Pricing is a **user-editable table** with `effective_date` + `pricing_version` + "edit me" note; ship dated defaults; **every £ figure stamps the pricing version and FX date** (same "scope every number" rule as suite/model stamping); never hardcode a rate in logic. A pricing-version mismatch between a baseline and a run is flagged a **confound**, not a regression (mirrors `blend_config_changed`). |
| 4 | **Anthropic absorbs the feature** (a future `/doctor`, dashboard, or extended diagnostics). The beta already does *level* divergence detection. | Medium | Moat is fourfold and structural: **(a) byte-level localisation + content** — Anthropic's fingerprints are content-free hashes, so they *cannot* show the byte; **(b) a persistent local £ ledger across months** — the API is per-request, not longitudinal; **(c) CI prevention** — fail the commit *before* the cost is incurred; **(d) provider-agnostic** byte-hygiene lint. **Partial-accept:** if Anthropic ships longitudinal cost attribution, pivot to the CI/prevention + cross-provider layers (the same "reconsideration trigger" pattern the `001` brainstorm already uses). |
| 5 | **Breakpoint-model mismatch.** The brief's "fixed cache blocks" model overcounts: sub-threshold prefixes never cache; caching is at ≤4 breakpoints, not per-1024-token rows. | Medium | Re-model to real **breakpoints + per-model min-threshold**, with a distinct **"never cached (below minimum)"** state rendered apart from "recomputed." Corrected in the design above; called out here so it isn't silently reintroduced. |
| 6 | **Attribution honesty / amortisation.** The simple `(write − read)` per-event figure can over/understate true waste: a write amortises over later reuse; a miss you'd have paid a read for anyway. | Medium | Ground the £ in **measured** `usage` tokens; present the simple per-event figure as the headline **with an explicit amortisation caveat flag**; keep "measured cost" and "attributed cause" as separate provenance. Document the counterfactual (stable-prefix) baseline in the methodology page. |
| 7 | **Captured-prompt privacy.** Captures contain full rendered prompts — secrets, proprietary code. | High | **Local SQLite only, append-only, nothing leaves the machine** (already the project's core guarantee). Content-addressed blobs pruned on retention expiry (hashes + cost metadata survive for the longitudinal ledger after raw bytes are dropped). Opt-in redaction rules; capture is opt-in per source. |
| 8 | **Proxy correctness.** The byte-diff is only right if we capture the exact **on-wire** bytes the cache hashes; an SDK wrapper may see pre-serialisation objects. | Low | Capture at the **HTTP layer** (post-serialisation) for the `exact` grade; the SDK wrapper is a convenience path flagged lower-fidelity for byte claims. |

---

## What I'm challenging in the brief (conflicts to resolve, not duplicate)

1. **"Cache blocks" → breakpoints + min-threshold.** Corrected above. The heatmap y-axis is breakpoints, and there's a distinct "never cached" state. This is a mechanism correction, not a preference.
2. **"Here is the byte that did it" is *our* claim, not the API's.** The diagnostics beta gives level + magnitude + hashes, never the byte or the content. The tagline stays true only because *we* captured the bytes locally. The UI must attribute the byte to our diff and the level/magnitude/cost to Anthropic — conflating them would be dishonest by the project's own standard.
3. **Two different "diff" features.** `001` already ships a **prompt *weight* diff** (FR-028 / US9, R2): which instruction *weights* shifted. CacheScope ships a **byte/cache divergence diff**: which bytes broke the cache. Same word, orthogonal meaning. They must be distinct commands and distinct schema types (`proseweight diff` vs `proseweight cache analyse`), never merged in the UI. Flagging so the R2 work doesn't collide.
4. **Local-first vs an inherently-API feature.** The project's stance is "local models are the instrument; nothing leaves the machine." Prefix caching is an Anthropic-API concept — there is no local cache to profile. Resolution: CacheScope profiles **traffic you already send**; it adds no new API calls (the diagnostics beta only annotates your real calls, and only if you opt in). "Nothing leaves the machine" holds for the *analysis* — all captures and the ledger are local SQLite. State this explicitly in the methodology so the two philosophies are reconciled, not quietly contradicted.
5. **Own Speckit feature, not new FRs on `001`.** Recommend `specs/002-cache-profiler/` sharing the `001` engine/report/CI/design, rather than appending FRs to `001` (which would renumber the existing spec and muddle two measurement axes). Each release still ships its CacheScope article as part of its definition of done, matching the `001` convention.

---

## Decisions (resolved 2026-09-14)

All eight open questions are answered; recorded here so the spec inherits them.

1. **Name** — **CacheScope**, CLI group `proseweight cache <sub>`. ✅
2. **Capture priority** — API proxy is R1 for PAYG; **and** a basic Claude Code transcript ingest is pulled **into R1** (revised from the original R3, because the author is on a subscription and the proxy captures none of his traffic — see *Subscription vs PAYG* above). High-fidelity reconstruction stays R3. ✅ *(one item for confirmation below)*
3. **Tap point** — no gateway; author is on a **Claude Code subscription, not PAYG**. Proxy serves the PAYG audience; the author's path is transcript ingest. ✅
4. **Diagnostics beta** — expose as a **checkbox setting**, passive by default, opt-in corroboration — and it only functions on the PAYG proxy path (can't touch subscription traffic). ✅
5. **Cost model** — measured meter (pounds for PAYG, quota + shadow-price for subscription) with *simple* per-event `(write − read)` attribution and an amortisation caveat. ✅
6. **Currency / FX** — static, stamped FX rate; seed the pricing table with the **current published PAYG rates** as defaults ("doesn't change much"), still editable. ✅
7. **Public-demo teardown** — yes; and the static lint also targets the **machine-wide `~/.claude/CLAUDE.md`** (global user instructions), not just project files. ✅
8. **Feature folder** — sibling **`specs/002-cache-profiler/`** sharing `001` infra. ✅

### One item to confirm

Q2's original answer ("proxy R1, CC ingest R3") predated the subscription implication surfacing in Q3. My recommended revision — **basic Claude Code transcript ingest in R1** so you can dogfood immediately, high-fidelity reconstruction in R3 — is written into the plan above. Say the word if you'd rather keep all Claude Code work in R3 and accept that R1 gives *you* nothing to run against your own sessions.

---

### Deliverable status for this session

Per the brief: this document is the **updated brainstorm section** (fold table + per-release placement + extends/displaces), the **data model** (captures / divergence / cost), the **one-page risk register**, and the **batched questions** (now resolved). No implementation code written. Next Speckit step is `/speckit-specify docs/brainstorm-cache-profiler.md` to create `specs/002-cache-profiler/spec.md`, carrying the mechanism corrections (breakpoints not blocks; measured-cost/attributed-cause; the PAYG↔subscription cost fork) into the spec.
