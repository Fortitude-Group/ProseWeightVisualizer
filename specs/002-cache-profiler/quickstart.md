# Quickstart & Validation: Cache Profiler (CacheScope)

**Date**: 2026-09-14 | **Feature**: `002-cache-profiler` | **Plan**: [plan.md](./plan.md)

Runnable scenarios that prove each release end-to-end. Each maps to a spec Independent Test / Success
Criterion. This is a **validation guide** — command shapes and expected outcomes — not implementation;
bodies live in `tasks.md` and the implementation phase. Contracts referenced:
[capture-ingestion](./contracts/capture-ingestion.md), [result](./contracts/result-contract.md),
[cli](./contracts/cli.md).

## Prerequisites

```bash
pip install -e .            # core deps only (no runtime/model extra needed — CacheScope core is deterministic)
pip install -e ".[api,dev]" # proxy (uvicorn/starlette/httpx) + pytest for the proxy & tests
```

No GPU, no model runtime, no API key required for the core, the static lint, analysis, or the render
adapter. An API key (env only) is needed **only** to exercise the live proxy against the real API or the
opt-in diagnostics beta.

---

## Scenario 1 — Static lint with zero captured data (US2 · SC-004)

```bash
printf 'ok line\r\ntrailing   \nupdated: 2026-09-14\n' > /tmp/CLAUDE.md
proseweight cache lint /tmp/CLAUDE.md --json -
```

**Expect**: three findings — `crlf_drift` (line 1), `trailing_whitespace` (line 2), `volatile_header`
(line 3) — each with a rule id, file, line/offset, an `estimated_monthly_gbp`, and `framing:
"prediction"`. No API, no model, no capture touched. (SC-004 instant proof.)

## Scenario 2 — Capture two turns through the reference proxy (US1 · SC-005)

```bash
proseweight cache serve --port 8790 &                 # binds 127.0.0.1 only
ANTHROPIC_BASE_URL=http://127.0.0.1:8790 <run your app twice, same prefix, one CRLF change>
```

**Expect**: two `CapturedTurn` rows in `cache.db`, `source_kind: api_proxy`, `confidence_grade: exact`,
each with the exact rendered prefix blob, the `usage` cache fields, model, timestamp, and
`response_message_id`. Verify **no off-machine egress** except the upstream API call the app itself made
(SC-005) — e.g. the proxy opens no socket other than to `--upstream`.

## Scenario 3 — Ingest a Claude Code transcript (US1)

```bash
proseweight cache ingest "<claude-code-session-transcript>"
```

**Expect**: turns stored `source_kind: claude_code_transcript` at a `reconstructed_*` grade (**never**
`exact`), with `usage` fields where the transcript exposes them.

## Scenario 4 — Divergence on a single CRLF (US3 · SC-001)

```bash
proseweight cache analyse --json result.json
```

**Expect** in `result.json`: a `DivergenceRecord` for the Scenario-2 pair with the **exact**
`first_divergent_offset`, its `line`, `cause: "crlf_drift"`, the `invalidated_breakpoints`, and — for a
prefix below the model minimum — a breakpoint `state: "never_cached"` rendered distinctly from
`recomputed` (SC-001, SC-010). Re-running yields byte-identical `divergences` (determinism).

## Scenario 5 — Prediction vs measured reconciliation (US4 · SC-003)

```bash
proseweight cache serve --port 8790 --diagnostics &    # opt-in beta (PAYG only)
# ... capture a diverging pair, then:
proseweight cache analyse --json result.json
```

**Expect**: each divergence's `reconciliation` shows predicted recomputed tokens beside the measured
`cache_read_input_tokens` drop; with the beta on, the predicted level beside the measured level and a
`level_mismatch` flagged when they differ. On a subscription/no-diagnostics turn: `agreement:
"no_measurement"` — **never** `agree` (SC-003).

## Scenario 6 — Cost ledger + meter fork (US5 · SC-002 / SC-006)

```bash
proseweight cache ledger --period month --json -
```

**Expect**: a headline figure by cause (e.g. `crlf_drift`), every figure stamped with pricing version +
effective date + FX date (SC-002 = 100%). A **PAYG** source shows measured £; a **subscription** source
shows quota tokens as primary with £ flagged `is_shadow_price: true` — no pound bill (SC-006).

## Scenario 7 — Self-contained export (US6)

```bash
proseweight cache export result.json --html cachescope.html --png cachescope.png
```

**Expect**: `cachescope.html` opens with no server; the heatmap y-axis is **cache breakpoints** with a
distinct never-cached state, clicking a miss opens the byte diff with the divergent byte highlighted, the
ledger shows a headline + per-cause drill-down, and the prediction-vs-measured view flags a seeded delta.
Brand-neutral by default (`--theme fortitude` for the teal theme).

## Scenario 8 — CI gate (US8 · SC-007)

```bash
proseweight cache lint ./CLAUDE.md --baseline .cachescope-baseline.json ; echo "exit=$?"
# convert CLAUDE.md to CRLF, re-run → exit 1 with the £ of the regression in the message
# benign edit → exit 0 ; different pricing_version/model → exit 3 (confound)
```

**Expect**: exit `1` + estimated monthly cost on a cache-hostile edit, exit `0` on benign, exit `3` on a
pricing/model mismatch (confound, not a regression) — SC-007.

---

## Guarantee checks (run in CI)

| Check | Proves | How |
|---|---|---|
| Import-lint: `cache/core/` imports none of `proseweight.{verdict,stats,report.brand,web,engine,segmentation}` | Transplantable core (SC-008 / FR-027) | AST/import scan test — fails the build on a forbidden import |
| `001` suite unchanged & green after this feature | Additive / non-breaking (SC-009 / FR-029) | run the full `001` test set; zero edits to `001` modules |
| Golden `CacheScopeResult` for a fixed capture set + `pricing.json` | Determinism (Principle IV) | snapshot compare (modulo `generated_at`) |
| Every figure carries pricing/effective/FX stamps and measured-vs-attributed flag | SC-002 / FR-030 | schema-guarantee test over the result contract |
| No `never_cached` breakpoint appears in any attribution/rollup | SC-010 | assertion over derived rollups |

## Notes / known caveats surfaced to the user (not hidden)

- Diagnostics-beta payload sub-fields are **unverified** (research R8) — the reconciliation view degrades
  to "no measurement" if a field is absent, never fabricating agreement.
- Transcript byte reconstruction (R3) always carries a confidence band; a figure is never shown as exact.
- A pruned prefix (retention) still contributes to the longitudinal ledger from its metadata; its
  byte-diff view states the bytes are gone.
