# Phase 0 Research: Cache Profiler (CacheScope)

**Date**: 2026-09-14 | **Feature**: `002-cache-profiler` | **Plan**: [plan.md](./plan.md)

This document pins the *mechanisms* behind the decisions already locked in the spec's Clarifications
(cache-lineage pairing, base-URL reverse proxy, capture-ingestion contract + OmnisRouter convergence,
self-contained HTML/PNG export, SQLite + content-addressed blob store). The eight original brainstorm
questions and these five clarification answers are **decisions** — they are not re-litigated here; what
follows is the concrete library/version/recipe layer, grounded against current reality (Anthropic
caching facts verified 2026-09-14 via the `claude-api` skill's `shared/prompt-caching.md`) and against
the existing `001` codebase this feature sits beside (`src/proseweight/`).

Version pins are starting points to lock at implementation; where a pin is load-bearing (the external
Anthropic contract, the reproducible byte-diff) that is called out. Every "verified" claim below states
its source; every "assumed" claim is marked so, per constitution Principle XI.

---

## R1. The external Anthropic cache contract (VERIFIED — the facts the cost engine depends on)

**Decision**: Treat these as an external, versioned contract seeded as editable defaults, never as
hardcoded constants. Verified against `claude-api` `shared/prompt-caching.md` (2026-09-14):

- **Breakpoints**: up to **4** explicit `cache_control` markers per request; render order is
  `tools → system → messages`; each breakpoint caches the whole prefix up to and including its block.
  Per-block TTL ordering rule: **a 1-hour entry must appear before any 5-minute entry** — a real
  constraint the breakpoint resolver must honour when reconstructing marker positions.
- **Per-model minimum cacheable prefix** (tokens), **non-monotonic across generations** — this is why
  the minimum belongs in a per-model table, not a heuristic:

  | Minimum | Models (as of 2026-09-14) |
  |---|---|
  | 512 | Claude Opus 5, Fable 5, Mythos 5, Fable 5.1, Mythos 5.1 |
  | 1024 | Opus 4.8, Sonnet 5, Sonnet 4.6, Sonnet 4.5, Opus 4.1/4, Sonnet 4 |
  | 2048 | Opus 4.7, Mythos Preview, Haiku 3.5 |
  | 4096 | Opus 4.6, Opus 4.5, Haiku 4.5 |

  A prefix below the model's minimum silently does not cache (`cache_creation_input_tokens: 0`, no
  error) — CacheScope's **never-cached** state (FR-011 / SC-010).
- **Multipliers**: 5-minute write **~1.25×** base input; 1-hour write **~2×** (well-published; not in
  the reference file — marked to confirm at implementation against the live pricing row); read **~0.1×**
  base input — but the read rate is **per-model** (Fable reads at $0.25/MTok = **0.025×** of its
  $10/MTok input). ⇒ multipliers are stored **per model**, not as one global constant.
- **`usage` fields**: `input_tokens` (uncached, full price), `cache_creation_input_tokens` (~1.25×
  write), `cache_read_input_tokens` (~0.1× read). The write total breaks down by TTL under
  `usage.cache_creation` → `ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`. All verified.
- **Silent invalidators** (the divergence causes CacheScope classifies): a `datetime.now()`/UUID in the
  prefix, unsorted `json.dumps()` of the tool set, a varying tool list, any prefix byte change — each
  drops `cache_read_input_tokens` to 0. This is the empirical ground truth the static-lint predictions
  (US2) are later confirmed against.

**Rationale**: the cost engine's correctness rests entirely on these figures (Principle XII — every
number must be explainable and right). Seeding them as an editable, versioned, per-model table (FR-016)
absorbs both drift and per-model quirks; stamping every figure with the pricing version + effective
date + FX date (FR-020) makes a later change a confound, not a silent error.

**Alternatives considered**: hardcoding 0.1×/1.25×/2× as constants (rejected — the 0.025× Fable read
rate alone refutes a global constant); deriving minimums by a rule of thumb (rejected — non-monotonic).

---

## R2. Capture path — base-URL reverse proxy (Release 1)

**Decision**: A small local **ASGI reverse proxy** (Starlette/`uvicorn`, already in the `web`/`api`
extras) exposing the Anthropic Messages route. The user sets `ANTHROPIC_BASE_URL=http://127.0.0.1:<port>`;
the proxy streams the request upstream unchanged, tees the exact request body bytes and the response
`usage` (and, when opted in, injects the diagnostics beta — R8) into the capture-ingestion contract
(R3), and returns the upstream response untouched. `httpx` (already transitively present) does the
upstream call with streaming pass-through so SSE is not buffered.

**Rationale**: base-URL override is a one-line, no-privilege change for the user (the Anthropic SDK
honours `ANTHROPIC_BASE_URL` / `base_url=` natively — verified in `claude-api` README), needs no CA
trust, and yields `exact`-confidence bytes (FR-004). Streaming pass-through preserves the on-wire
prefix exactly (SC-001 byte precision) and does not alter the user's latency materially. Bound to
`127.0.0.1` so nothing is exposed off-machine (FR-005 / SC-005).

**Alternatives considered**: transparent MITM forward proxy with a local CA (rejected in clarify —
invasive, captures unrelated HTTPS); in-process SDK wrapper (kept as a *possible* future source behind
the same contract, not R1 — it can't capture non-Python clients like Claude Code). **OmnisRouter is the
intended production source** and already implements this proxy in .NET; the reference proxy here exists
so CacheScope runs standalone (FR-001a), and both write the same contract (R3).

**Pins to lock**: `uvicorn>=0.30` + `starlette` (via FastAPI, already an extra), `httpx>=0.27` (dev
extra) — reuse the `001` `api`/`web` extras rather than add new top-level deps.

---

## R3. Capture-ingestion contract + store (SQLite + content-addressed blobs)

**Decision**: A versioned, serialisable **capture-ingestion contract** (JSON record) any producer writes
(reference proxy, transcript ingester, or OmnisRouter). Persisted in a **SQLite** ledger (`cache.db`)
plus a **content-addressed blob directory** (`blobs/<sha256[:2]>/<sha256>`) for the raw prefix bytes.
The ledger holds turns, lineages, breakpoints, divergence records, pricing stamps, and rollups; a
prefix blob is referenced by hash so retention can delete the blob while the row (hash + cost metadata)
survives for the longitudinal ledger (FR-003).

**Rationale**: the ledger's core queries are relational rollups — waste grouped by period × cause ×
model, headline per cause (FR-018) — which SQLite serves directly and `001`'s per-run JSON cannot
aggregate across turns. Content-addressing deduplicates identical prefixes (common across near-miss
turns) and makes retention pruning a blob-delete, not a row rewrite. SQLite is single-file, needs no
service (FR-005, offline), ships in the Python stdlib (`sqlite3`), and is **the same storage idiom
OmnisRouter uses** — so a future merged capture story shares the shape. Additive: a new `cache.db`,
never touching `001`'s JSON tree (FR-029 / SC-009).

**Schema discipline**: migrations via `PRAGMA user_version`; the JSON contract carries a
`contract_version` (SemVer). WAL mode for concurrent proxy-write + analysis-read.

**Alternatives considered**: JSON/JSONL only like `001` (rejected — cross-turn rollups become O(n)
in-memory scans every read); DuckDB (rejected for R1 — extra heavy dependency; SQLite's analytics are
sufficient at single-tenant scale; revisit only if ledgers reach millions of turns).

---

## R4. Divergence detection, lineage pairing, cause classification

**Decision**: Pair turns **within a cache lineage** (Q1: same source + model + shared leading-prefix
family, time-ordered, TTL-bounded). Lineage key = `(source, model, prefix_family_fp)`, where `prefix_family_fp` = **sha256 of the first
4096 bytes** of the rendered prefix (configurable `lineage_prefix_window`, default 4096 — sized to cover
the stable `tools` + leading `system` region that the cache prefix-matches on). When present, Anthropic's
own `previous_message_id` linkage (R8) is the **authoritative** pairing edge and overrides the fingerprint;
the transcript path (no message id) relies solely on the fingerprint window. Byte-diff a consecutive pair with a
**deterministic** first-divergence scan over raw bytes (not `difflib` opcodes — we need the exact first
divergent offset, not a minimal edit script): compare byte-by-byte to the first mismatch, then classify
its cause by inspecting a small window around the offset and the line it falls on.

Cause classes (FR-009), each a small deterministic detector: `crlf_drift`, `trailing_whitespace`,
`volatile_header`, `concat_order_change`, `timestamp_injection`, `tool_definition_churn`,
`model_change`, `system_prompt_change`, `genuine_edit`. `genuine_edit` and intended `model_change` are
marked **non-avoidable** and excluded from waste (FR-012 / edge cases).

**Rationale**: the "here is the byte that did it" claim (SC-001) requires the true first divergent
offset, which is a linear byte scan, not an LCS/edit-distance minimisation. Determinism (same inputs →
same offset + class) is required for golden tests (Principle IV) and is trivial for a byte scan.
`previous_message_id` is a stronger lineage edge than a prefix heuristic and is free when the proxy
records the response id.

**Alternatives considered**: `difflib.SequenceMatcher` (rejected as the primary — it optimises for a
readable diff, can place the "change" at a non-first offset, and is not guaranteed minimal; keep it only
to *render* the surrounding hunk once the first offset is found). Token-level diff (rejected — the cache
invalidates on bytes, not tokens; a byte offset is the ground truth, tokens are a derived view).

---

## R5. Breakpoint resolution and block-survival

**Decision**: Resolve up to 4 breakpoints per captured request from the on-wire `cache_control` markers
(exact on the proxy path) or reconstruct them (transcript path, R7). Map the first divergent offset onto
the ordered breakpoints (`tools → system → messages`, honouring the 1h-before-5m ordering rule from R1):
breakpoints whose capped prefix ends **at or after** the divergence offset are **recomputed**; earlier
ones **survive**; a breakpoint whose prefix is below the model minimum is **never-cached** (a third
state, FR-011). Predicted recomputed tokens = tokens in the invalidated span, reconciled against
measured `usage` (R8).

**Rationale**: this is the real Anthropic unit (R1), not fixed-size blocks (FR-010 explicitly forbids
the fixed-block model). The three-state colouring (hit / recomputed / never-cached, plus new) is the
heatmap's semantics (FR-021) and the guarantee behind SC-010 (never attribute waste to a never-cached
prefix).

**Assumed / to verify at implementation**: exact token counts per span use the model tokenizer;
`client.messages.count_tokens` is the authoritative counter (per `claude-api` `shared/token-counting.md`)
— but it is a network call. R1 uses a local byte→token estimate with a stated confidence band and
calibrates against measured `usage` (R8); exact `count_tokens` is an opt-in refinement, never a
silent hard figure.

---

## R6. Cost engine — measured pounds vs shadow-price fork

**Decision**: `wasted_spend = recomputed_tokens × base_input_rate × (write_multiplier − read_multiplier)`
(FR-017), all rates from the per-model table (R1), grounded in measured `usage` where present. The meter
**forks by billing model** (FR-019): PAYG → measured GBP; subscription → quota-token consumption as the
primary meter with a GBP figure surviving only as an explicitly-labelled **shadow-price counterfactual**.
GBP via a static stamped USD→GBP FX rate (FR-020); every figure stamps pricing version + effective date
+ FX date. An amortisation caveat flag rides any per-event figure that a later reuse would offset (edge
case).

**Rationale**: the fork is a first-class correctness constraint, not a display toggle — the author runs
a subscription, where a "£ bill" would be a lie (SC-002 / SC-006). Grounding in measured tokens keeps
the headline figure defensible (Principle XII).

**Transplant note (FR-027)**: this engine — the store schema, detectors, pricing table, attribution,
rollups, static-lint rules — is the unit destined for OmnisVigil. It lives in `cache/core/` and imports
**nothing** from `001` (`verdict`, `stats`, `report/brand`, `web`, `engine`). See R11.

---

## R7. Claude Code transcript ingest (basic R1, high-fidelity R3)

**Decision**: R1 ingests Claude Code's on-disk session transcripts for the `usage`-level meter
(source `claude_code_transcript`, confidence below `exact`). R3 reconstructs the effective byte prefix
(tools + system + `CLAUDE.md`/memory + history) and breakpoints as faithfully as the transcript allows,
attaches an explicit **confidence grade**, calibrates predicted recomputed tokens against the turn's
measured `usage`, and — on disagreement — **lowers the confidence, never adjusts the figure**, showing a
band (FR-024 / SC-006).

**Rationale**: this is the author's primary path (subscription), so basic ingest is pulled into R1 to
make the tool useful to him day one; byte-level reconstruction is fidelity-risky and depends on a mature
divergence/cost engine, so it lands R3. Never presenting a reconstructed figure as exact is the honesty
guarantee (FR-030).

**Assumed / to verify**: the on-disk transcript location and schema for the installed Claude Code build
are read from the system at implementation, not assumed here (Principle XI) — a transcript-format probe
is the first R3 task, and the reconstruction confidence grades are defined against what the format
actually exposes.

---

## R8. Reconciliation and the diagnostics beta (VERIFIED wiring, partial payload)

**Decision**: Where `usage` cache fields are present, reconcile predicted recomputed tokens against the
measured drop in `cache_read_input_tokens` / rise in `cache_creation_input_tokens` (FR-013) as a
first-class view. On the PAYG proxy path only, support the **opt-in** cache-diagnostics beta, passive by
default (FR-014): the proxy uses `client.beta.messages.*` with beta header **`cache-diagnosis-2026-04-07`**
and threads `diagnostics: {previous_message_id: <prior response id | null>}`; the result arrives on
`response.diagnostics`. On subscription traffic (no diagnostics), reconcile on `usage` alone and record
**"no measurement"**, never treating absence as agreement (FR-015).

**VERIFIED (2026-09-14)**: the beta header string, the `client.beta.messages.*` requirement, the
`diagnostics: {previous_message_id}` request shape, and `response.diagnostics` as the result location
(source: `claude-api` skill, Common Pitfalls → "Cache diagnostics is beta").

**UNVERIFIED — flagged**: the spec names payload sub-fields `cache_miss_reason.type`,
`cache_missed_input_tokens`, and a `previous_message_not_found` state. These are **not** in the reference
and must be confirmed against the live diagnostics response schema at implementation before any code
reads them; the reconciliation view must degrade gracefully if a field is absent (treat as "no
measurement", per FR-015). The `previous_message_id` linkage doubles as the authoritative lineage edge
(R4).

**Rationale**: diagnostics is a best-effort corroborator, never a dependency (spec Assumptions) — it is
Claude-API-only and unavailable on subscription traffic, so the tool must be fully useful without it.

---

## R9. Rendering — self-contained HTML/PNG export adapter

**Decision**: A `cache/report/` **adapter** (a consumer of the versioned result contract, never part of
the core) renders three views (FR-021/022/023) as a **self-contained HTML** document with inline
CSS/SVG/JS (click-a-miss → byte diff works offline) plus optional **PNG** summary via `Pillow` (already
a core dep). Brand-neutral, token-themed by default; a Fortitude teal theme is an opt-in adapter setting
(FR-023a / FR-028). Reuses the `001` self-contained-export *pattern* (`report/export_html.py`,
`report/svg_charts.py`) without importing or modifying `001` modules.

**Rationale**: the output is inherently a shareable artefact, so a static self-contained file beats a
running service (no server, works on the read-only demo). Keeping rendering out of the core preserves
transplantability (R11) and honours "rendering is an adapter, never the core" (transplant memory).

**Alternatives considered**: a new interactive Gradio/FastAPI surface (rejected in clarify — more
surface, a running process, no need); modifying `001`'s faceplate (forbidden, Out of Scope).

---

## R10. CI cache-lint gate (Release 3)

**Decision**: `proseweight cache lint <file> --baseline <file>` exits non-zero when a commit introduces a
cache-hostile change to a `CLAUDE.md`/`.kb` file, printing the estimated monthly cost of the regression
(FR-025); exits zero for benign edits; reports a pricing/model mismatch vs the baseline as a **confound**,
not a regression (edge case). Shares the `001` CI lint infrastructure (`ci/lint.py`, `ci/action/`) as a
sibling command and is wrappable by the same GitHub Action pattern.

**Rationale**: prevention is the product wedge (block the cost before it is incurred); the static-lint
rules (US2) already compute the estimated monthly cost, so the gate is a thin exit-code + baseline-diff
wrapper over them. Depends on cost attribution (R6) and the shared `001` R3 CI infra, so it lands R3.

---

## R11. Transplant boundary and package layout

**Decision**: One-way dependency. `cache/core/` (store schema, detectors, breakpoint resolver, pricing
table, cost attribution, rollups, static-lint rules, the two versioned contracts) imports **nothing**
from `001` and nothing from CacheScope's own adapters. Everything else — `cache/proxy/`, `cache/ingest/`,
`cache/report/`, the CLI `cache` subcommand — is a consumer of the core's contracts. The byte-offset idea
shared with `001`'s `segmentation/` is reused by a small **copied contract**, never an import (transplant
memory). A `cache.core.api` façade (SemVer'd) is the only surface OmnisVigil imports.

**Rationale**: FR-027/028 and the OmnisVigil transplant memory require the core to be liftable without
modification behind a versioned data contract. An import-lint test (SC-008) asserts `cache/core/` has no
`proseweight.{verdict,stats,report.brand,web,engine,segmentation}` import — making the boundary
executable, not aspirational.

**Alternatives considered**: sharing `001`'s `report/schema.py` types (rejected — couples the core to
`001`'s contract and breaks transplantability); a separate repo now (rejected — premature; additive
in-repo package keeps R1 shippable and the transplant is a later exercise, spec Assumptions).

---

## Summary of pins to lock at implementation

| Area | Pin / choice | Load-bearing? |
|---|---|---|
| Cache facts (rates, minimums, fields, beta) | Per-model editable table seeded from R1; beta `cache-diagnosis-2026-04-07` | **Yes** — cost correctness |
| Proxy | `uvicorn`+`starlette`+`httpx` (reuse `001` extras) | No |
| Store | stdlib `sqlite3` (WAL, `user_version`) + blob dir | Yes — schema/migrations |
| Byte diff | linear first-divergence byte scan; `difflib` for hunk rendering only | **Yes** — SC-001 determinism |
| Tokenisation | local estimate + band in R1; `count_tokens` opt-in refine | Yes — honesty band |
| Diagnostics payload fields | `cache_miss_reason.type` / `cache_missed_input_tokens` | **UNVERIFIED — confirm before use** |
| Render | inline HTML/SVG/JS + `Pillow` PNG (reuse `001` pattern) | No |
| FX/pricing stamping | pricing version + effective date + FX date on every figure | Yes — SC-002 |
