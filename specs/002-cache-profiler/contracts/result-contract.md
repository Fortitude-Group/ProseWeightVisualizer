# Contract: CacheScope Result (output) + `cache.core.api` façade

**Stability**: public, SemVer'd. `result_version` is stamped into every artefact; a breaking field
change is a MAJOR bump with a migration note. This is the **output** boundary (FR-028): the versioned,
brand-neutral, serialisable projection the render adapter, the CLI, and — later — **OmnisVigil** consume.
It is the only surface `cache.core.api` exposes; consumers import the contract, never core internals
(FR-027 / R11). Rendering (HTML/PNG, any Fortitude theme) is a separate consumer, never part of this
core (FR-023a).

## `cache.core.api` façade (the SemVer'd surface)

```
ingest(record: CaptureIngestionRecord) -> CapturedTurn        # append a capture (input contract)
analyse(scope) -> CacheScopeResult                            # lineages → divergences → breakpoints → cost
ledger(period, filters) -> LedgerRollup[]                     # aggregated waste (FR-018)
lint(target_files, pricing) -> LintFinding[]                  # static prediction, no captured data (US2)
```

OmnisVigil imports exactly this. Every method returns contract objects below; none returns a core
internal type, and the core imports nothing from `001` (asserted by the import-lint test, SC-008).

## CacheScopeResult object

```jsonc
{
  "result_version": "1.0.0",
  "generated_at": "2026-09-14T10:05:00Z",
  "pricing": { "pricing_version": "2026-09", "effective_date": "2026-09-01", "fx_date": "2026-09-01",
               "usd_gbp": 0.79 },       // provenance stamped on the result and on every figure (SC-002)

  "lineages": [
    { "id": "lin_1", "source_kind": "api_proxy", "model_id": "claude-opus-5",
      "turns": ["turn_1", "turn_2"] }
  ],

  "divergences": [
    { "id": "div_1", "lineage_id": "lin_1", "prev_turn_id": "turn_1", "turn_id": "turn_2",
      "first_divergent_offset": 40012, "line": 3, "cause": "crlf_drift",
      "avoidable": true, "predicted_recomputed_tokens": 8000,
      "invalidated_breakpoints": [0],
      "reconciliation": { "measured_read_drop": 8000, "measured_cause_level": null,
                          "measured_missed_tokens": null, "agreement": "no_measurement" } }
  ],

  "breakpoints": [
    { "turn_id": "turn_2", "index": 0, "level": "system", "capped_tokens": 40000,
      "ttl": "5m", "state": "recomputed" }   // hit | recomputed | new | never_cached
  ],

  "attributions": [
    { "divergence_id": "div_1", "billing_model": "subscription",
      "wasted_tokens": 8000, "wasted_gbp": 4.12, "is_shadow_price": true,
      "quota_tokens": 8000, "amortisation_caveat": false,
      "pricing_version": "2026-09", "effective_date": "2026-09-01", "fx_date": "2026-09-01" }
  ],

  "rollups": [
    { "period": "month", "period_key": "2026-09", "cause": "crlf_drift", "model_id": null,
      "billing_model": "subscription", "wasted_gbp": 4.12, "wasted_quota_tokens": 8000,
      "headline": true }
  ],

  "lint_findings": [
    { "id": "lf_1", "rule_id": "crlf_drift", "file": "CLAUDE.md", "line": 3, "offset": 12,
      "estimated_monthly_gbp": 4.12, "framing": "prediction",
      "confirmed_by_measurement": "confirmed" }
  ],

  "validity": {                          // aggregate prediction-vs-measured agreement (SC-003)
    "diverging_turns_with_measurement": 42,
    "level_agreements": 39,
    "agreement_rate": 0.929,             // level_agreements / diverging_turns_with_measurement
    "disagreements": [ "div_7", "div_18", "div_31" ]   // surfaced, never hidden (SC-003)
  }
}
```

## Guarantees (enforced in code + tested)

- **Every figure is stamped** with `pricing_version` + `effective_date` + `fx_date`, and marked
  measured vs attributed/predicted (SC-002 = 100%; FR-020/030).
- **Subscription figures are shadow-prices**: `billing_model = subscription ⇒ is_shadow_price = true`
  and `quota_tokens` present; no field presents a subscription pound value as a bill (SC-006).
- **`never_cached` never carries waste** (SC-010); breakpoint `state` distinguishes it from
  `recomputed`.
- **`agreement = no_measurement`** whenever diagnostics/usage are absent — never `agree` (SC-003).
- **`validity.agreement_rate`** is the aggregate of per-turn level agreements over diverging turns that
  had a measurement, with the disagreeing divergence ids listed — the measurable form of SC-003's ≥90%
  claim (computed only over `diverging_turns_with_measurement`, so it states what it excludes).
- **`framing` is always `prediction`** on lint findings (US2 AC3); `confirmed_by_measurement` is the
  only field that later ties a prediction to a measured divergence.
- **Brand-neutral**: the contract carries no colour/theme/brand; presentation is the adapter's job
  (FR-028 / FR-023a).
- **Determinism** (Principle IV): identical captures + identical `pricing.json` ⇒ byte-identical
  `CacheScopeResult` (modulo `generated_at`), so the result is golden-testable.
