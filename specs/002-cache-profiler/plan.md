# Implementation Plan: Cache Profiler (CacheScope)

**Branch**: `002-cache-profiler` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-cache-profiler/spec.md`

## Summary

CacheScope is the **empirical** prompt-cache profiler — a second measurement axis on the Prose Weight
bench beside the `001` weight linter. It captures a user's real Claude traffic locally (a base-URL
recording reverse proxy for PAYG; Claude Code transcript ingest for subscription), byte-diffs why each
cache miss happened *within a cache lineage*, maps the divergence onto Anthropic's real cache breakpoints,
reconciles the prediction against measured `usage` (and the opt-in diagnostics beta), attributes the
avoidable waste to a cause, and prices it — measured £ on PAYG, a labelled shadow-price on a subscription.
The headline: *"your CRLF line endings cost you £4.12 this month, and here is the byte that did it."*

The design is **additive and transplant-clean**: a new `cache/` package with a one-way-dependent
`cache/core/` (store, detectors, breakpoint resolver, pricing, attribution, static lint) behind two
SemVer'd contracts — a **capture-ingestion** input contract (the sibling **OmnisRouter** product is the
intended production source; a self-contained reference proxy ships here so R1 is standalone) and a
**CacheScope result** output contract (the unit destined to transplant into **OmnisVigil**). Storage is a
new SQLite ledger + content-addressed blob dir. Rendering is a brand-neutral self-contained HTML/PNG
adapter, never the core. Scope is three releases by priority (R1 capture + static lint; R2 divergence,
reconciliation, cost, visualisation; R3 high-fidelity reconstruction, CI gate, methodology). **Zero edits
to `001`.**

## Technical Context

**Language/Version**: Python 3.11+ (single language; matches `001` and the `proseweight` package).

**Primary Dependencies** (reuse `001`'s pins; no new heavy top-level deps): stdlib `sqlite3` (capture
ledger, WAL, `PRAGMA user_version` migrations) + a content-addressed blob dir; `uvicorn`/`starlette`
(via the existing `api` extra) + `httpx` (dev extra) for the base-URL recording reverse proxy with SSE
pass-through; `Jinja2` + inline SVG + `Pillow` (core deps) for the self-contained HTML/PNG export adapter;
`PyYAML`/`markdown-it-py` (core) for reading `CLAUDE.md`/`.kb` targets in the static lint; the `anthropic`
SDK (runtime extra, opt-in) only for the live proxy's diagnostics beta and any opt-in `count_tokens`
refinement — key from env, never a flag. The external Anthropic cache facts (rates, per-model minimums,
`usage` fields, beta `cache-diagnosis-2026-04-07`) are seeded as an **editable per-model table**, verified
2026-09-14 (research R1/R8).

**Storage**: Local **SQLite** (`cache.db`) append-only ledger — turns, cache lineages, breakpoints,
divergence records, pricing stamps, period/cause/model rollups — plus a **content-addressed blob dir**
(`blobs/<sha256>`) for raw prefix bytes, prunable by retention while rows persist. Editable `pricing.json`
/ `settings.json`. Distinct from and additive to `001`'s per-run JSON tree; single-file, no service,
offline. Same idiom as OmnisRouter (SQLite).

**Testing**: pytest — unit (detectors, breakpoint resolver, cost math, lineage pairing), integration
(proxy capture → analyse → ledger → export end-to-end), contract (capture-ingestion + result schema
guarantees), and a **gates** harness for the honesty/boundary kill-criteria (import-lint transplant
boundary SC-008; `001` suite unchanged SC-009; golden `CacheScopeResult` determinism; every-figure-stamped
SC-002; never-cached-carries-no-waste SC-010). Golden/snapshot tests for the deterministic result schema
and HTML/PNG export.

**Target Platform**: Local developer machines (Windows/Linux/macOS). No hosted execution; the public
demo is read-only pre-computed content. No GPU.

**Project Type**: Single Python repository — a new `cache/` library package (core + adapters) plus a
`cache` command group on the existing `proseweight` CLI. Sibling to `001`, sharing infrastructure by
*reuse of pattern*, never by modifying it.

**Performance Goals**: Proxy pass-through adds negligible latency and never buffers SSE (streaming
tee). Static lint of a `CLAUDE.md` is sub-second (SC-004 instant proof). Analysis is a local batch over
the SQLite store; rollups are relational and scale to single-tenant volumes without a service.

**Constraints**: Deterministic (Principle IV) — identical captures + identical `pricing.json` ⇒
byte-identical `CacheScopeResult` (modulo `generated_at`); nondeterminism (the live API) is isolated to
the proxy/diagnostics path and never enters analysis. Byte-exact first-divergence offset (SC-001). Every
figure stamped with pricing version + effective date + FX date and marked measured-vs-attributed (SC-002
/ FR-030). Nothing leaves the machine (FR-005 / SC-005). **Additive-only** to the repo; **transplant-clean**
`cache/core/` (FR-027/029). No API key in source (env only).

**Scale/Scope**: Tens to thousands of captured turns per user; ≤ 4 breakpoints/request; 9 cause classes;
30 functional requirements (incl. FR-001a), 9 user stories across 3 releases; the cost-analysis core is a
future OmnisVigil transplant.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against the project constitution v1.5.0. Initial gate (pre-research): **PASS**. Post-design
re-check (after `research.md`, `data-model.md`, `contracts/*`, `quickstart.md`): **PASS** — the design
introduces no new violations and actively strengthens Principles I (a one-way-dependent core behind two
SemVer'd contracts), II (both contracts + the CLI group SemVer'd and stamped), III (import-lint, `001`-
unchanged, determinism, every-figure-stamped, never-cached gates are executable tests), IV (determinism
proven in quickstart, nondeterminism isolated to the live proxy), XI (external cache facts verified against
the authoritative reference, unverified diagnostics sub-fields flagged not assumed), and XII (every figure
answers what/why/what-follows, forks the meter honestly, and states what a filtered count excludes). No
Complexity Tracking entries required at either gate.

- **Prime Directive (Boil the Ocean)**: full three-release scope carried, nothing dropped; R1 design
  (store schema, both versioned contracts, lineage model) anticipates R2/R3. ✅
- **I. Modular & Composable**: `cache/core/` is a self-contained unit; `proxy`/`ingest`/`report`/CLI are
  thin consumers of its contracts; the byte-offset idea shared with `001` is a copied contract, not an
  import. ✅
- **II. Contract Stability & SemVer**: three versioned public contracts — capture-ingestion (input),
  CacheScope result (output, = `cache.core.api`), and the `proseweight cache` CLI surface; each stamps its
  version; pricing figures stamp pricing version + effective + FX date. ✅
- **III. Comprehensive Tests for Public Contracts**: contract, unit, integration, and gates layers;
  edge cases enumerated (never-cached, pruned bytes, no-measurement, confound, amortisation, low
  confidence). Test-first encouraged, not mandated. ✅
- **IV. Deterministic & Observable Behaviour**: byte-exact offsets and byte-identical results under fixed
  inputs; the only nondeterminism (live API) is isolated to the proxy and flagged; every capture traces to
  source, model, timestamp, confidence. ✅
- **V. Simplicity & Justified Complexity**: SQLite over a service, a linear byte scan over an edit-distance
  library, a static export over a running web app, no new heavy deps (reuse `001` extras). Each simpler
  rejected alternative is recorded in `research.md`. No Complexity Tracking entry needed. ✅
- **VI. Complete the Scope**: each release ships its stories together; R1's contracts/store are part of its
  definition of done, not deferred scaffolding. ✅
- **VII. Tracker Is the Project of Record**: an ADO mirror exists (project ProseWeightVisualizer); work
  items + commit↔work-item linkage are handled at `/speckit-tasks` and implementation. This plan flags the
  board must be populated from the task breakdown. ✅ (enforced downstream)
- **VIII. Start From a Fresh Base**: work is on branch `002-cache-profiler`; resume re-syncs onto `master`
  before new commits. ✅
- **IX. Ask, Then Wait**: the five gating decisions were resolved via `/speckit-clarify` (incl. the
  OmnisRouter convergence) before planning. ✅
- **X. Production Changes Wait for a Human**: N/A — a local, single-tenant tool with no production
  environment; the demo is read-only static content. ✅
- **XI. Establish the Mechanism Before Changing Code**: cache facts verified against the `claude-api`
  reference (2026-09-14), OmnisRouter's real capabilities read from its README, unverified diagnostics
  payload sub-fields explicitly flagged rather than assumed, transcript format to be probed from the
  system at implementation. ✅
- **XII. Explain Every Number**: the tool's purpose — every figure answers what/why/what-follows, the
  meter forks measured £ vs shadow-price, filtered ledgers state exclusions, and a chart is used only
  where a heatmap/trend beats a list. ✅

## Project Structure

### Documentation (this feature)

```text
specs/002-cache-profiler/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output — mechanisms + verified cache facts
├── data-model.md        # Phase 1 output — entities → SQLite ledger + blob store
├── quickstart.md        # Phase 1 output — release validation scenarios
├── contracts/           # Phase 1 output
│   ├── capture-ingestion.md   # input contract (proxy / transcript / OmnisRouter)
│   ├── result-contract.md     # output contract + cache.core.api façade
│   └── cli.md                 # `proseweight cache <sub>` command surface
├── checklists/
│   └── requirements.md  # Spec quality checklist (green)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/proseweight/
├── cache/                    # NEW — the CacheScope feature (additive; imports nothing from 001 in core/)
│   ├── core/                 # TRANSPLANTABLE, one-way-dependent (FR-027; import-lint enforced, SC-008)
│   │   ├── contracts.py      #   CaptureIngestionRecord + CacheScopeResult dataclasses (versioned, serde)
│   │   ├── store.py          #   SQLite ledger + content-addressed blob store (WAL, user_version)
│   │   ├── lineage.py        #   cache-lineage grouping + consecutive pairing (Q1)
│   │   ├── divergence.py     #   linear first-divergence byte scan + cause classification (9 classes)
│   │   ├── breakpoints.py    #   breakpoint resolution + hit/recomputed/new/never_cached mapping
│   │   ├── pricing.py        #   editable per-model pricing table (rates, minimums, stamps)
│   │   ├── cost.py           #   attribution + meter fork (measured £ / shadow-price)
│   │   ├── ledger.py         #   period × cause × model rollups + headline (consumes cost.py)
│   │   ├── lint.py           #   static cache-hygiene rules (prediction layer, US2)
│   │   └── api.py            #   cache.core.api façade — ingest / analyse / ledger / lint (SemVer'd)
│   ├── proxy/                #   base-URL recording reverse proxy (R2) — writes the ingestion contract
│   ├── ingest/               #   Claude Code transcript ingester (R7; basic R1, byte-level R3)
│   ├── report/               #   brand-neutral self-contained HTML/PNG export adapter (R9; not core)
│   └── ci/                   #   cache-lint baseline gate (R10) — sibling of 001 ci/, shares the pattern
└── cli/
    └── main.py               #   register the `cache` Typer sub-app (additive edit — new group only)

data/
└── cache/
    ├── pricing.default.json  # seeded editable per-model pricing table (rates, minimums, version, dates)
    └── fixtures/             # planted-ground-truth capture sets (single CRLF, below-minimum, etc.) for gates

tests/
├── unit/                     # cache_divergence, cache_breakpoints, cache_cost, cache_lineage, cache_lint
├── integration/              # cache proxy→analyse→ledger→export end-to-end
├── contract/                 # cache_capture_ingestion, cache_result_schema guarantees
└── gates/                    # cache_transplant_import_lint (SC-008), cache_001_unchanged (SC-009),
                              # cache_result_determinism, cache_figures_stamped (SC-002), cache_never_cached (SC-010)

docs/
├── brainstorm-cache-profiler.md   # existing source brainstorm
└── methodology.md                 # R3 — cache-cost section appended (shared 001 methodology page)
```

**Structure Decision**: Single Python project; CacheScope is a new `src/proseweight/cache/` package. The
transplantable engine is `cache/core/` (Principle I), one-way dependent — it imports nothing from `001`
(`verdict`/`stats`/`report.brand`/`web`/`engine`/`segmentation`) nor from CacheScope's own adapters, a
boundary made executable by an import-lint gate (SC-008). `proxy`, `ingest`, `report`, and `ci` are thin
consumers of the core's two versioned contracts; the only edit to existing code is registering the `cache`
Typer sub-app in `cli/main.py` (additive — a new command group, no change to `001` commands, FR-029). The
capture store (`cache.db` + `blobs/`) is new and distinct from `001`'s per-run JSON. Data (pricing table,
gate fixtures) lives outside the package tree so pricing versions independently of code.

## Complexity Tracking

> No Constitution Check violations — this section intentionally left empty.

Deliberate R1 simplifications (documented in `research.md` as future refinements, not deferred in-scope
work): token counts use a local byte→token estimate with a stated confidence band in R1, with exact
`count_tokens` as an opt-in refinement (avoids a network call per turn); `difflib` is used only to render
a diff hunk, never to find the first divergent offset (a linear byte scan is the ground truth); DuckDB is
rejected for R1 in favour of stdlib SQLite (revisit only at millions-of-turns scale); the OmnisRouter
byte-capture sink and the OmnisVigil transplant are out of scope, reserved behind the two versioned
contracts. Each is recorded with the trigger that would justify adopting it later.
