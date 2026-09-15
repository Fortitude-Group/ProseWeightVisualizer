---
description: "Task list for Cache Profiler (CacheScope)"
---

# Tasks: Cache Profiler (CacheScope)

**Input**: Design documents from `specs/002-cache-profiler/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Included. Constitution Principle III requires comprehensive coverage of public contracts at merge, and the spec makes several honesty/boundary criteria non-negotiable executable checks — transplant import-lint (SC-008), `001` suite unchanged (SC-009), result determinism (Principle IV), every-figure-stamped (SC-002), never-cached-no-waste (SC-010). Test-first ordering is encouraged but not mandated.

**Organization**: Tasks are grouped by user story. Priorities map to releases — P1 = Release 1, P2 = Release 2, P3 = Release 3. The two versioned contracts + the SQLite store + the pricing table are Foundational (block every story). **MVP = User Story 1 + User Story 2** (both P1: capture, and the zero-data static lint).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US9 for story-phase tasks; Setup/Foundational/Polish carry no story label
- All paths are relative to repo root and follow the structure in [plan.md](./plan.md)
- **All work is additive** — the only edit to existing code is registering the `cache` CLI sub-app (T004); zero changes to `001` modules or tests (FR-029)

---

## Parallelization & fan-out (per owner's always-parallel rule)

**The genuine dependency chain** (must be serial): `contracts.py` (T005) → `store.py` (T008) + `pricing.py` (T010) → `api.py` façade (T012) → everything else. Foundational blocks all stories.

**Independent fan-out once Foundational lands** — dispatch as concurrent agents:
- **US1 (capture) ∥ US2 (static lint)** — both P1, no shared files; US2 needs only `pricing.py`, not capture. Ship them concurrently for the MVP.
- Within **US3**, the three core detectors are disjoint files → `lineage.py` ∥ `divergence.py` ∥ `breakpoints.py` (T024/T025/T026 all `[P]`), joined by `analyse()` (T027).
- **US4, US5, US6** each build on US3's `analyse()` output but touch disjoint files (`reconcile.py`, `cost.py`, `report/`) → run concurrently once T027 lands.
- **US7, US8, US9** (all P3) are mutually independent → concurrent.
- Cross-cutting gate tests (T013/T014 in Foundational; T048–T050 in Polish) are all `[P]`.

**Serial exceptions**: CLI wiring tasks that all edit the `cache` sub-app module (T019, T022, T034, T038) are serialized against each other even though their stories are parallel — they share one file.

---

## Phase 0: Tracker Sync (ADO — Principle VII, runs first and stays current)

**Purpose**: Keep the ADO board the project of record. See **T053** — it is performed **before** T001 and kept current throughout (states + commit↔work-item linkage). Numbered last only to avoid renumbering; it is the first action.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: New `cache/` package skeleton, seed data, and the single additive CLI hook.

- [X] T001 Create the CacheScope source tree: `src/proseweight/cache/{core,proxy,ingest,report,ci}/` each with `__init__.py`, and `src/proseweight/cache/cli.py`; add `data/cache/` and confirm `tests/{unit,integration,contract,gates}/` exist
- [X] T002 [P] Seed the editable per-model pricing table `data/cache/pricing.default.json` from research R1 (base input rate, `write_mult_5m`≈1.25, `write_mult_1h`≈2.0, per-model `read_mult` incl. 0.025 Fable-class, `min_cacheable_tokens` 512/1024/2048/4096, `pricing_version`, `effective_date`, and a `"_note": "prices change — edit me"` field per FR-016) — confirm the live pricing/FX row before locking values
- [X] T003 [P] Create and populate planted-ground-truth fixtures under `data/cache/fixtures/` used by US3 and the gates: a single-`\r\n`-vs-`\n` prefix pair, a below-minimum prefix, a `updated:`-header pair, a concat-order-swap pair — each with expected offset/cause
- [X] T004 Register the `cache` Typer sub-app in `src/proseweight/cli/main.py` (`app.add_typer(cache_app, name="cache")`) — additive; new group only, no change to existing `scan`/`duel`/`lint` commands

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The two versioned contracts, the SQLite store, the pricing table, and the transplant/boundary gates. **No story work begins until this phase is complete.**

**⚠️ CRITICAL**: All of Phase 2 blocks all user stories.

- [X] T005 [P] Implement the versioned contract dataclasses in `src/proseweight/cache/core/contracts.py` — `CaptureIngestionRecord` and `CacheScopeResult` (+ nested Reconciliation/attribution/rollup/lint types) with explicit `to_dict`/`from_dict`/`validate` and `contract_version`/`result_version`, per [contracts/capture-ingestion.md](./contracts/capture-ingestion.md) and [contracts/result-contract.md](./contracts/result-contract.md)
- [X] T006 [P] Contract test `tests/contract/test_cache_capture_ingestion.py` — `api_proxy ⇒ exact`, `diagnostics non-null ⇒ api_proxy`, exactly one of `prefix_bytes_b64`/`prefix_ref`, unknown fields ignored, missing required rejected with version
- [X] T007 [P] Contract test `tests/contract/test_cache_result_schema.py` — every figure carries pricing/effective/FX stamps + measured-vs-attributed flag (SC-002), `subscription ⇒ is_shadow_price` (SC-006), `no_measurement` never `agree` (SC-003), lint `framing == prediction`
- [X] T008 Implement the SQLite ledger + content-addressed blob store in `src/proseweight/cache/core/store.py` — WAL, `PRAGMA user_version` migrations, append-only turns/lineages/breakpoints/divergences/attributions/rollups tables, `blobs/<sha256[:2]>/<sha256>` prefix store with dedup (depends on T005)
- [X] T009 [P] Unit test `tests/unit/test_cache_store.py` — append-only, blob dedup by hash, prune-blob-keeps-row, `user_version` migration round-trip
- [X] T010 [P] Implement the editable per-model pricing table in `src/proseweight/cache/core/pricing.py` — load `pricing.json` (fallback to the seeded default), per-model rates/multipliers/`min_cacheable_tokens`, version+date stamps, GBP FX (data-model ModelPricing)
- [X] T011 [P] Unit test `tests/unit/test_cache_pricing.py` — non-monotonic minimums preserved, per-model read multiplier (0.025 Fable-class), stamps present, an edit is reflected on reload
- [X] T012 Scaffold the `cache.core.api` façade in `src/proseweight/cache/core/api.py` — `ingest`/`analyse`/`ledger`/`lint` signatures returning contract objects only (methods filled in their story phases) (depends on T005, T008)
- [X] T013 [P] Gate `tests/gates/test_cache_transplant_import_lint.py` — AST/import scan asserts `cache/core/` imports none of `proseweight.{verdict,stats,report.brand,web,engine,segmentation}` nor any CacheScope adapter (SC-008 / FR-027)
- [X] T014 [P] Gate `tests/gates/test_cache_001_unchanged.py` — assert no `001` module/test files were modified by this feature and the full `001` suite still passes (SC-009 / FR-029)

**Checkpoint**: contracts + store + pricing + façade exist and are green → US1 and US2 can start in parallel.

---

## Phase 3: User Story 1 — Capture real sessions locally (P1 · Release 1)

**Goal**: Accumulate an append-only local record of each turn's rendered prefix + reported cache-usage, from the base-URL proxy (PAYG, `exact`) and Claude Code transcript ingest (subscription, reconstructed), honouring retention. Nothing leaves the machine.

**Independent test**: Route two consecutive requests through the proxy and separately ingest a transcript; confirm each turn stores its prefix, `usage` fields, model, timestamp, source, and confidence grade, and that there is no off-machine egress from the analysis path.

- [X] T015 [US1] Implement the base-URL recording reverse proxy in `src/proseweight/cache/proxy/server.py` — Starlette/uvicorn on `127.0.0.1`, streaming (SSE) pass-through to `--upstream`, tees exact request bytes + response `usage` into a `CaptureIngestionRecord` (depends on T012)
- [X] T016 [US1] Implement `ingest()` in `cache/core/api.py` — persist a `CaptureIngestionRecord` → `CapturedTurn` + `RenderedPrefix` blob, assigning/creating the `CacheLineage` (source+model+prefix-family; `previous_message_id` override) (depends on T012)
- [X] T017 [P] [US1] Implement the basic Claude Code transcript ingester in `src/proseweight/cache/ingest/claude_code.py` — usage-level captures tagged `claude_code_transcript` at a `reconstructed_*` grade (never `exact`) (depends on T012)
- [X] T018 [US1] Implement retention in `cache/core/store.py` + `settings.json` — prune raw prefix bytes past N days while retaining hash + cost metadata (FR-003) (depends on T008)
- [X] T019 [US1] Add `proseweight cache serve` (`--port`/`--upstream`/`--diagnostics`/`--db`) and `cache ingest <path>...` (`--watch`) to `src/proseweight/cache/cli.py` (depends on T004, T015, T017)
- [X] T020 [US1] Integration test `tests/integration/test_cache_capture.py` — two proxy turns stored `exact` + one transcript turn `reconstructed`; assert no socket opens except to `--upstream` (SC-005)

**Checkpoint**: real captures accumulate in `cache.db`.

---

## Phase 4: User Story 2 — Static cache-hygiene lint without captured data (P1 · Release 1)

**Goal**: Fast offline lint over `CLAUDE.md` / `~/.claude/CLAUDE.md` / `.kb/*.md` producing predicted cache-hostility findings with an estimated monthly cost, each framed as a prediction. No capture, no API, no model.

**Independent test**: Lint a `CLAUDE.md` seeded with a CRLF line, a trailing-whitespace line, and an `updated:` header in line 2; confirm three distinct predicted findings with rule id, file, line, and estimated monthly cost, each labelled a prediction. **Runs in parallel with US1.**

- [X] T021 [P] [US2] Implement static cache-hygiene rules in `src/proseweight/cache/core/lint.py` — `crlf_drift`, `trailing_whitespace`, `concat_order`, `volatile_header`; emit `LintFinding` with rule id/file/line/offset, `estimated_monthly_gbp` (via pricing), `framing = prediction` (depends on T010)
- [X] T022 [US2] Wire `lint()` in `cache/core/api.py` and add `proseweight cache lint <file>...` to `cache/cli.py` (globs, `~/.claude/CLAUDE.md`, `--json`) (depends on T012, T021, T004)
- [X] T023 [P] [US2] Unit test `tests/unit/test_cache_lint.py` — three seeded findings, every finding `framing == prediction`, each carries a stamped estimated cost (SC-004)

**Checkpoint**: MVP complete — the tool has day-one value (lint) while capture accumulates.

---

## Phase 5: User Story 3 — Divergence analysis of consecutive turns (P2 · Release 2)

**Goal**: Byte-diff consecutive turns *within a lineage*, report the exact first divergent offset + cause, and map it onto cache breakpoints (hit / recomputed / new / never-cached).

**Independent test**: Feed two prefixes differing only by one `\r\n`-vs-`\n`; confirm the exact first divergent offset, its line, cause `crlf_drift`, the invalidated breakpoints, and a never-cached state rendered distinctly for a below-minimum prefix.

- [X] T024 [P] [US3] Implement cache-lineage grouping + consecutive pairing in `src/proseweight/cache/core/lineage.py` — key on source+model+`prefix_family_fp` (sha256 of the first `lineage_prefix_window`=4096 bytes), TTL-bounded; a matching `previous_message_id`→`response_message_id` link is authoritative and overrides the fingerprint; transcript path uses the fingerprint alone; first-seen head yields no record (depends on T005, T008)
- [X] T025 [P] [US3] Implement the linear first-divergence byte scan + 9-class cause classifier in `src/proseweight/cache/core/divergence.py` (`difflib` only to render the surrounding hunk); mark `genuine_edit`/intended `model_change` non-avoidable (depends on T005)
- [X] T026 [P] [US3] Implement breakpoint resolution + state mapping in `src/proseweight/cache/core/breakpoints.py` — ≤4 breakpoints (tools→system→messages, 1h-before-5m), map offset → hit/recomputed/new/never_cached using per-model minimum (depends on T010)
- [X] T027 [US3] Wire `analyse()` in `cache/core/api.py` — produce `DivergenceRecord`s over the store (lineage → byte-diff → breakpoint states) into a `CacheScopeResult` (depends on T024, T025, T026, T012)
- [X] T028 [P] [US3] Unit tests: `tests/unit/test_cache_divergence.py` (single CRLF → exact offset + `crlf_drift`, SC-001), `tests/unit/test_cache_breakpoints.py` (below-minimum → `never_cached` distinct from `recomputed`, SC-010), `tests/unit/test_cache_lineage.py` (no cross-lineage pairing; first-seen no record; **fingerprint-path grouping when no `previous_message_id`**; message-id link overrides fingerprint)

---

## Phase 6: User Story 4 — Prediction versus measured reconciliation (P2 · Release 2)

**Goal**: Reconcile predicted recomputed tokens against measured `usage`, and (opt-in, PAYG only) against the diagnostics beta, as a first-class view. Never treat absent measurement as agreement.

**Independent test**: For a captured turn with a divergence + present `usage`/diagnostics, the reconciliation shows predicted vs measured level and recomputed-vs-missed tokens and flags a mismatch.

- [ ] T029 [P] [US4] Implement reconciliation in `src/proseweight/cache/core/reconcile.py` — predicted recomputed vs measured `cache_read`/`cache_creation` drop; parse `response.diagnostics` **defensively** (payload sub-fields unverified, R8 — absent ⇒ `no_measurement`, never `agree`); compute the result's aggregate `validity` block (agreement_rate over diverging turns with measurement + disagreeing ids, SC-003) (depends on T025, T027)
- [ ] T030 [US4] Add opt-in diagnostics-beta injection to the proxy in `cache/proxy/server.py` — `client.beta.messages.*` + `cache-diagnosis-2026-04-07`, thread `previous_message_id`, PAYG only, passive by default (depends on T015, T029)
- [ ] T031 [P] [US4] Unit test `tests/unit/test_cache_reconcile.py` — predicted vs read-drop; `level_mismatch` flagged; absent diagnostics ⇒ `no_measurement` (never `agree`); **aggregate `validity.agreement_rate` computed over only measured diverging turns with disagreeing ids listed** (SC-003)

---

## Phase 7: User Story 5 — Cost attribution and ledger (P2 · Release 2)

**Goal**: Price each avoidable divergence and aggregate by period × cause × model, forking the meter by billing model; every figure stamped.

**Independent test**: A month of captures with a recurring CRLF divergence yields a headline waste figure per cause; PAYG shows measured £, subscription shows quota + labelled shadow-price; every figure carries pricing/effective/FX stamps.

- [ ] T032 [P] [US5] Implement cost attribution + meter fork in `src/proseweight/cache/core/cost.py` — `recomputed_tokens × base_rate × (write_mult − read_mult)` → GBP; PAYG measured vs subscription quota + `is_shadow_price`; amortisation caveat; provenance stamps; exclude non-avoidable (depends on T010, T027)
- [ ] T033 [P] [US5] Implement ledger rollups in `src/proseweight/cache/core/ledger.py` — day/week/month × cause × model, headline per cause (depends on T032)
- [ ] T034 [US5] Wire `ledger()` in `api.py` and add `proseweight cache ledger` (`--period`) to `cache/cli.py` — terminal summary forks the meter and states the excluded set (Principle XII) (depends on T012, T033, T004)
- [ ] T035 [P] [US5] Unit test `tests/unit/test_cache_cost.py` — formula; subscription never a bill (SC-006); all three stamps present (SC-002); non-avoidable excluded

---

## Phase 8: User Story 6 — Visualisation (P2 · Release 2)

**Goal**: Three views as a self-contained HTML/PNG export via a brand-neutral adapter (never the core).

**Independent test**: Render each view from a captured dataset; heatmap y-axis is breakpoints with a distinct never-cached state, clicking a miss opens the byte diff, the ledger shows a headline + drill-down, and prediction-vs-measured flags a seeded delta.

- [ ] T036 [P] [US6] Implement the self-contained HTML export adapter in `src/proseweight/cache/report/export_html.py` — inline CSS/SVG/JS; heatmap (breakpoints y-axis, hit/recomputed/new/never-cached), cost ledger (stacked + headline + drill), prediction-vs-measured; click-a-miss → byte diff; brand-neutral default (reuses the `001` self-contained-export pattern, **no import**) (depends on T027, T032, T033)
- [ ] T037 [P] [US6] Implement the PNG summary card in `src/proseweight/cache/report/png_card.py` via `Pillow`, `--theme neutral|fortitude` (depends on T036)
- [ ] T038 [US6] Add `proseweight cache export <result.json> --html --png --theme` to `cache/cli.py` (depends on T036, T037, T004)
- [ ] T039 [P] [US6] Snapshot test `tests/unit/test_cache_export.py` — three views present, never-cached state distinct, seeded delta flagged, brand-neutral by default

---

## Phase 9: User Story 7 — High-fidelity Claude Code reconstruction (P3 · Release 3)

**Goal**: Reconstruct the effective byte prefix + breakpoints per transcript turn with explicit confidence, calibrated against measured `usage`; never present a figure as exact.

**Independent test**: Reconstruct a turn's prefix, confirm a confidence grade is attached, predicted tokens are calibrated against `usage`, and no figure is shown as exact.

- [ ] T040 [US7] Probe the installed Claude Code transcript format **from the system** (Principle XI) and document the reconstruction confidence grades against what it exposes, in `src/proseweight/cache/ingest/claude_code_reconstruct.py`
- [ ] T041 [US7] Implement byte-level prefix + breakpoint reconstruction with an explicit confidence band and `usage` calibration — on disagreement, **lower confidence, never adjust the figure**; show a band (FR-024) (depends on T040, T026)
- [ ] T042 [P] [US7] Unit test `tests/unit/test_cache_reconstruct.py` — confidence attached, calibrated against `usage`, never exact, band shown (SC-006)

---

## Phase 10: User Story 8 — CI cache-lint gate (P3 · Release 3)

**Goal**: `proseweight cache lint <file> --baseline <file>` fails the build on a cache-hostile regression with the estimated monthly cost; benign passes; pricing/model mismatch is a confound.

**Independent test**: A CRLF-conversion edit → non-zero exit + £ in message; a benign edit → zero; a baseline pricing/model mismatch → confound exit.

- [ ] T043 [US8] Implement the baseline regression gate in `src/proseweight/cache/ci/lint.py` — exit 0/1/2/3, estimated monthly £ in the failure message, pricing/model mismatch → confound (exit 3); `--baseline`/`--update-baseline` on `cache lint` (depends on T021, T032; shares the `001` `ci/` pattern)
- [ ] T044 [P] [US8] GitHub Action wrapper in `src/proseweight/cache/ci/action/` mirroring the `001` action (depends on T043)
- [ ] T045 [P] [US8] Integration test `tests/integration/test_cache_ci_gate.py` — CRLF edit → exit 1 + £; benign → exit 0; mismatch → exit 3 (SC-007)

---

## Phase 11: User Story 9 — Methodology (P3 · Release 3)

**Goal**: Publish the cache-cost methodology section.

**Independent test**: The section describes divergence detection, measured-vs-attributed cost, the meter fork, the breakpoint model + per-model minimums, and the known limitations.

- [ ] T046 [US9] Append the cache-cost section to `docs/methodology.md` (divergence detection, measured vs attributed, PAYG-vs-subscription meter fork, breakpoint model + per-model minimums, limitations: reconstruction fidelity, diagnostics availability, pricing drift, amortisation) — write with `writing-no-slop`
- [ ] T047 [P] [US9] Doc-presence test `tests/unit/test_cache_methodology.py` — the section names each required topic

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: The remaining executable guarantees and the additive-clean close-out.

- [ ] T048 [P] Gate `tests/gates/test_cache_result_determinism.py` — fixed captures + fixed `pricing.json` ⇒ byte-identical `CacheScopeResult` (modulo `generated_at`) (Principle IV)
- [ ] T049 [P] Gate `tests/gates/test_cache_figures_stamped.py` — 100% of result figures carry pricing/effective/FX stamps + measured-vs-attributed flag (SC-002 / FR-030)
- [ ] T050 [P] Gate `tests/gates/test_cache_never_cached.py` — no `never_cached` breakpoint appears in any attribution or rollup (SC-010)
- [ ] T051 [P] Update `README.md` with the `proseweight cache` command group and the OmnisRouter→CacheScope→OmnisVigil shape (write with `writing-no-slop`)
- [ ] T052 Final verification: run the full suite incl. the `001` set (SC-009), the transplant import-lint (SC-008), and `ruff`/build clean; confirm zero edits to `001` modules and a clean additive delta
- [ ] T053 Tracker sync (Principle VII — **perform first, keep current throughout**): mirror this T001–T052 breakdown onto the ADO board (project ProseWeightVisualizer) as Feature → Story (US1–US9) → Task items under the correct parents; set each item's state as work starts/completes; link every commit to its work item by hash (`AB#<id>`) and record the delivering commit hash on each item. A board that disagrees with this task list is a defect to fix, not tolerate.

---

## Dependencies (story completion order)

```text
Setup (T001–T004)
  └─> Foundational (T005 → T008/T010 → T012; gates T013/T014)   [BLOCKS ALL STORIES]
        ├─> US1 Capture (P1)  ─┐
        ├─> US2 Static lint (P1) ┘  ← US1 ∥ US2  = MVP
        └─> US3 Divergence (P2)  [lineage ∥ divergence ∥ breakpoints → analyse]
              ├─> US4 Reconciliation (P2)  ┐
              ├─> US5 Cost/ledger (P2)      ├─ concurrent (disjoint files, all consume analyse())
              └─> US6 Visualisation (P2)   ┘
                    ├─> US7 Hi-fi reconstruction (P3)  ┐
                    ├─> US8 CI gate (P3)                ├─ concurrent (all P3, independent)
                    └─> US9 Methodology (P3)           ┘
        Polish gates (T048–T050) ∥ ; T052 last
```

- **US1 ∥ US2** are both P1 and share no files → dispatch concurrently.
- **US3 core detectors** (T024/T025/T026) are `[P]` → three concurrent agents, joined by T027.
- **US4/US5/US6** depend only on T027 and touch disjoint files → concurrent.
- **US7/US8/US9** are independent → concurrent.
- **Serial contention**: T019/T022/T034/T038 all edit `cache/cli.py` → serialize those four.

## Implementation strategy

0. **Tracker sync first (T053)** — populate the ADO board from this breakdown before writing code, and keep states + commit↔work-item linkage current as each task lands (Principle VII).
1. **Foundational first, once** — the contracts/store/pricing/façade chain is the only hard serial spine.
2. **MVP = US1 + US2** delivered concurrently — capture starts accumulating real data while the offline lint gives day-one value.
3. **Release 2 fan-out** — build US3's three detectors in parallel, then fan US4/US5/US6 out on top of `analyse()`.
4. **Release 3 fan-out** — US7/US8/US9 concurrently.
5. **Close on the gates** — determinism, stamps, never-cached, transplant import-lint, `001` unchanged — these are the merge blockers that prove the honesty and additive guarantees.
