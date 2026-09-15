# Phase 1 Data Model: Cache Profiler (CacheScope)

**Date**: 2026-09-14 | **Feature**: `002-cache-profiler` | **Plan**: [plan.md](./plan.md)

The durable domain objects CacheScope captures, derives, prices, and renders. Field types are
language-agnostic. "Stored as" names the on-disk home: the **SQLite ledger** (`cache.db`), the
**content-addressed blob dir** (`blobs/`), or the **editable config** (`pricing.json` /
`settings.json`). All serialise through the two versioned contracts in
[contracts/](./contracts/): the **capture-ingestion contract** (input, [capture-ingestion.md](./contracts/capture-ingestion.md))
and the **CacheScope result contract** (output, [result-contract.md](./contracts/result-contract.md)).
Everything under `cache/core/` — including these entities — imports nothing from `001` (FR-027, R11).

Legend: `?` nullable · `[]` list · types are `string | int | float | bool | enum | hash | ts`.

---

## CaptureSource

Where captures originate. A row per configured source; carries retention + confidence policy.

| Field | Type | Notes |
|---|---|---|
| `id` | string | stable id |
| `kind` | enum | `api_proxy \| claude_code_transcript \| external_contract` (external = OmnisRouter et al.) |
| `confidence_grade` | enum | `exact` (proxy) \| `reconstructed_high \| reconstructed_low` (transcript) |
| `retention_days` | int? | prune raw prefix bytes older than N days; null = keep |
| `label` | string? | human name |

**Relationships**: owns many `CapturedTurn`. **Validation**: `api_proxy ⇒ confidence_grade = exact`;
a transcript source may never be `exact` (FR-004).

---

## CapturedTurn

One request/response observation. The atomic unit of capture; append-only (FR-003).

| Field | Type | Notes |
|---|---|---|
| `id` | string | stable id |
| `source_id` | string | → CaptureSource |
| `lineage_id` | string | → CacheLineage (assigned on ingest, R4) |
| `prefix_hash` | hash | sha256 of the rendered prefix bytes → RenderedPrefix |
| `model_id` | string | e.g. `claude-opus-5` |
| `timestamp` | ts | request time |
| `input_tokens` | int | uncached tokens (full price) |
| `cache_creation_input_tokens` | int | write tokens (~1.25×) |
| `cache_read_input_tokens` | int | read tokens (~0.1×) |
| `ephemeral_5m_input_tokens` | int? | TTL split, where present (R1) |
| `ephemeral_1h_input_tokens` | int? | TTL split, where present |
| `response_message_id` | string? | Anthropic message id — the authoritative lineage edge (R4/R8) |
| `previous_message_id` | string? | threaded for the diagnostics beta |
| `diagnostics` | json? | raw `response.diagnostics` payload when the beta was enabled (PAYG only) |
| `source_confidence` | enum | copied from the source at ingest (a turn's own grade) |

**Relationships**: belongs to one CaptureSource and one CacheLineage; references one RenderedPrefix by
hash; is the left/right of `DivergenceRecord` pairs. **Validation**: `diagnostics` non-null ⇒
`source.kind = api_proxy` (FR-014); the three `usage` token fields are ≥ 0.

**State**: `bytes_present → bytes_pruned` (retention deletes the blob; the row and its `prefix_hash` +
token/cost metadata persist for the ledger, FR-003).

---

## RenderedPrefix

The content-addressed store of exact prefix bytes. Deduplicated by hash; prunable.

| Field | Type | Notes |
|---|---|---|
| `hash` | hash | sha256, primary key; blob path `blobs/<hash[:2]>/<hash>` |
| `byte_len` | int | length in bytes (survives pruning) |
| `token_estimate` | int? | local byte→token estimate (R5), with `estimate_confidence` |
| `estimate_confidence` | enum? | `exact \| banded` — `exact` only if calibrated via `count_tokens` |
| `present` | bool | false once the blob is pruned |

**Validation**: offsets in a DivergenceRecord are always into `byte_len` of the *stored* bytes; a diff
view on a pruned prefix states the bytes are unavailable (edge case), never fabricates them.

---

## CacheLineage

The grouping that makes two turns comparable (Q1 clarification). Divergence and reuse are computed only
within a lineage — never across.

| Field | Type | Notes |
|---|---|---|
| `id` | string | stable id |
| `source_id` | string | → CaptureSource (a lineage never spans sources) |
| `model_id` | string | a lineage never spans models |
| `prefix_family_fp` | hash | sha256 of the **first 4096 bytes** of the rendered prefix (configurable `lineage_prefix_window`, default 4096) — the leading-window fingerprint that groups a family |
| `first_seen`, `last_seen` | ts | bounds |

**Relationships**: owns an ordered `CapturedTurn[]` (by timestamp). **Validation**: a turn joins a
lineage iff same `source_id` + `model_id` + matching `prefix_family_fp` (sha256 of the first
`lineage_prefix_window` = 4096 bytes) **and** within the cache TTL of the lineage's `last_seen`; when a
turn carries `previous_message_id` matching a stored `response_message_id`, that linkage is authoritative
and overrides the fingerprint (R4). The transcript path (no message id) relies solely on the fingerprint
window. A turn with no eligible predecessor is the lineage's **new/first-seen** head — no
DivergenceRecord (FR-008).

---

## Breakpoint

A resolved cache-control position for one captured request (exact on proxy, reconstructed on transcript).

| Field | Type | Notes |
|---|---|---|
| `id` | string | stable id |
| `turn_id` | string | → CapturedTurn |
| `index` | int | 0–3 (≤ 4 per request, FR-010) |
| `level` | enum | `tools \| system \| messages` (render order) |
| `capped_byte_offset` | int | last byte of the prefix this breakpoint caches |
| `capped_tokens` | int | tokens cached up to this breakpoint |
| `ttl` | enum | `5m \| 1h` (1h entries ordered before 5m, R1) |
| `state` | enum | `hit \| recomputed \| new \| never_cached` (never_cached ⇒ below model minimum) |

**Validation**: `never_cached` iff `capped_tokens < model minimum` for `turn.model_id` (from
ModelPricing); waste is never attributed to a `never_cached` breakpoint (FR-011 / SC-010). `state` is
derived by mapping the DivergenceRecord offset onto `capped_byte_offset` (R5).

---

## DivergenceRecord

A consecutive-turn comparison *within a lineage* (R4). The source of "here is the byte that did it".

| Field | Type | Notes |
|---|---|---|
| `id` | string | stable id |
| `lineage_id` | string | → CacheLineage |
| `prev_turn_id`, `turn_id` | string | the pair (prev = predecessor) |
| `first_divergent_offset` | int | exact first mismatching byte (SC-001); `-1` if identical |
| `line` | int | 1-indexed line the offset falls on |
| `cause` | enum | `crlf_drift \| trailing_whitespace \| volatile_header \| concat_order_change \| timestamp_injection \| tool_definition_churn \| model_change \| system_prompt_change \| genuine_edit` |
| `avoidable` | bool | false for `genuine_edit` and intended `model_change` (FR-012) |
| `predicted_recomputed_tokens` | int | tokens in the invalidated span (R5) |
| `invalidated_breakpoints` | int[] | breakpoint indices forced to recompute |
| `reconciliation` | Reconciliation? | predicted-vs-measured (below), null if no measurement |

**Validation**: `cause = crlf_drift` requires the diverging bytes be exactly `\r\n` vs `\n` (SC-001);
`avoidable = false ⇒` excluded from all CostAttribution/LedgerRollup sums (FR-012).

### Reconciliation (embedded)

| Field | Type | Notes |
|---|---|---|
| `measured_read_drop` | int? | drop in `cache_read_input_tokens` vs predecessor |
| `measured_cause_level` | string? | from `response.diagnostics` (PAYG beta) — **field name unverified, R8** |
| `measured_missed_tokens` | int? | from diagnostics — **unverified, R8** |
| `agreement` | enum | `agree \| level_mismatch \| token_mismatch \| no_measurement` |

**Validation**: absence of diagnostics ⇒ `no_measurement`, **never** `agree` (FR-015 / SC-003).

---

## ModelPricing

The editable per-model rate table (FR-016). Seeded with published defaults (R1); every figure that uses
it is stamped with its version.

| Field | Type | Notes |
|---|---|---|
| `model_id` | string | key |
| `base_input_rate_usd_per_mtok` | float | full-price input |
| `write_mult_5m` | float | ~1.25 |
| `write_mult_1h` | float | ~2.0 (confirm live, R1) |
| `read_mult` | float | ~0.1 (0.025 for Fable-class — per-model, R1) |
| `min_cacheable_tokens` | int | 512 / 1024 / 2048 / 4096 (non-monotonic, R1) |
| `pricing_version` | string | SemVer of the table |
| `effective_date` | ts | when these rates took effect |

**Stored as**: `pricing.json` (editable, "prices change — edit me"). **Validation**: a run whose
`pricing_version`/`model_id` differs from a CI baseline is a **confound**, not a regression (FR-025 edge).

---

## CostAttribution

Per-divergence priced waste. Forks by billing model (FR-019).

| Field | Type | Notes |
|---|---|---|
| `divergence_id` | string | → DivergenceRecord (only `avoidable = true`) |
| `billing_model` | enum | `payg \| subscription` |
| `wasted_tokens` | int | = `predicted_recomputed_tokens` (grounded in measured usage where present) |
| `wasted_gbp` | float | `wasted_tokens × base_input_rate × (write_mult − read_mult)` → GBP; a **shadow-price** if subscription |
| `quota_tokens` | int? | subscription primary meter |
| `is_shadow_price` | bool | true ⇒ `wasted_gbp` is a counterfactual, never a bill (SC-002/006) |
| `amortisation_caveat` | bool | a later reuse may offset this event (edge case) |
| `pricing_version`, `effective_date`, `fx_date` | string/ts | provenance stamp on every figure (FR-020 / SC-002) |

**Validation**: `billing_model = subscription ⇒ is_shadow_price = true` and `quota_tokens` present;
every row carries all three provenance stamps (SC-002 = 100%).

---

## LedgerRollup

Aggregated waste driving the headline figure (FR-018). Derived (a SQL view / materialised rollup).

| Field | Type | Notes |
|---|---|---|
| `period` | enum | `day \| week \| month` |
| `period_key` | string | e.g. `2026-09` |
| `cause` | enum | cause class (or `all`) |
| `model_id` | string? | null = all models |
| `billing_model` | enum | `payg \| subscription` |
| `wasted_gbp` | float | summed (shadow-price if subscription) |
| `wasted_quota_tokens` | int? | subscription meter |
| `headline` | bool | the top-line figure for the period |

**Validation**: excludes non-avoidable divergences and never-cached breakpoints; a filtered headline
states what it excludes (Principle XII).

---

## LintFinding

A static prediction (US2 / FR-006/007), computable with **no captured data**.

| Field | Type | Notes |
|---|---|---|
| `id` | string | stable id |
| `rule_id` | string | `crlf_drift \| trailing_whitespace \| concat_order \| volatile_header` (extensible) |
| `file` | string | target (`CLAUDE.md`, `~/.claude/CLAUDE.md`, `.kb/*.md`) |
| `line`, `offset` | int | location |
| `estimated_monthly_gbp` | float | predicted cost (stamped like CostAttribution) |
| `framing` | enum | always `prediction` — never a measured verdict (FR-007 / US2 AC3) |
| `confirmed_by_measurement` | enum? | `confirmed \| refuted \| pending` — set later when a capture matches |

**Validation**: `framing = prediction` invariant; a finding may be *linked* to a later
DivergenceRecord that confirms/refutes it (the prediction-vs-measured thesis, US4).

---

## Contract objects (serialisation surfaces)

- **CaptureIngestionRecord** — the input contract any producer writes (proxy, ingester, OmnisRouter):
  `{contract_version, source_kind, model_id, timestamp, prefix_bytes|prefix_ref, usage{...},
  response_message_id?, previous_message_id?, diagnostics?, confidence_grade}`. See
  [contracts/capture-ingestion.md](./contracts/capture-ingestion.md).
- **CacheScopeResult** — the output contract the render adapter and OmnisVigil consume: a versioned,
  brand-neutral projection of lineages, divergences, breakpoint states, attributions, rollups, and lint
  findings. See [contracts/result-contract.md](./contracts/result-contract.md). This is the SemVer'd
  surface behind `cache.core.api` (R11).

**Cross-cutting invariant (FR-030 / Principle XI)**: every figure records whether it is **measured** or
**attributed/predicted**, and every reconstructed input records its source + confidence — measured and
assumed are never rendered in the same voice.
