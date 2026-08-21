# Quickstart & Validation Guide: Prompt Weight Linter

**Date**: 2026-08-20 | **Feature**: `001-prompt-weight-linter`

A runnable guide proving the feature works end to end. It references the contracts and data model rather than repeating them. Implementation code lives in `tasks.md` / the implementation phase, not here.

## Prerequisites

- Python 3.11+ (predecessor runs on 3.14; pin the line at implementation).
- One local subject model (default `Qwen/Qwen2.5-1.5B-Instruct`) and the local judge (`Llama-3.1-8B-Instruct`, 4-bit). CUDA GPU used if present; CPU fallback works for small models (degraded, recorded in the report).
- Optional: `ANTHROPIC_API_KEY` in the environment only if using the opt-in frontier judge.
- Install: a single command sets up the environment without hand-managing it (`pip install -e .` / project script). No API keys in any config file.

## Install & smoke test

```bash
pip install -e .
proseweight --version
proseweight scan --help
```
Expected: version prints; `scan` help lists global options and exit codes matching [contracts/cli.md](./contracts/cli.md).

## Scenario 1 — Verdict on a pasted prompt (US1, P1)

```bash
proseweight scan ./examples/sample-prompt.md --depth quick --seed 42 --json out.json
```
Expected:
- A time/cost estimate prints **before** the run (FR-019).
- Terminal shows the headline "N% below the noise floor", a ranked table (weight, CI, classification), and the suite version + model scoping.
- `out.json` validates against [contracts/report-schema.md](./contracts/report-schema.md): every `weight` has `ci_low/ci_high/pd`; noise-floor rows have `is_noise_floor: true`; any `contradicted` row names `contradicts_instruction_id`.

## Scenario 2 — Reproducibility (SC-002 / Gate B)

```bash
proseweight scan ./examples/sample-prompt.md --depth deep --seed 7 --json a.json
proseweight scan ./examples/sample-prompt.md --depth deep --seed 7 --json b.json
diff a.json b.json    # fully-local judge → identical
```
Expected: byte-identical reports (guaranteed only for fully-local runs; an `--judge anthropic` run instead carries `reproducibility: best_effort` and is exempt).

## Scenario 3 — Instrument validity (SC-001 / Gate A)

```bash
proseweight scan ./data/fixtures/planted-ground-truth.md --depth deep --seed 1 --json gateA.json
python -m tests.gates.check_gate_a gateA.json    # ranking + noise-floor assertions
```
Expected: all planted load-bearing instructions rank above all planted no-ops, and the no-ops land in the noise-floor state — in ≥90% of deep-audit runs across seeds (the gate harness runs the repeat).

## Scenario 4 — Segment review before a run (FR-002)

```bash
proseweight scan ./examples/sample-prompt.md --depth quick    # no --yes
```
Expected: segmentation is printed and the run waits for confirmation; supplying `--segments reviewed.json` runs on the edited segmentation instead. A run never starts on unreviewed auto-segmentation.

## Scenario 5 — Dead-weight & conflicts (US2, P1)

Expected in the Scenario 1 output: a cut list of below-noise instructions each with a token cost (FR-012), and any mutually-reducing instruction pairs listed as conflicts (FR-013). No prompt text is rewritten (FR-014).

## Scenario 6 — Teardowns & CLI/web parity (US3/US4, SC-006/SC-007)

- Open the read-only web demo: at least two famous-prompt teardowns render fully with no run started, each citing its source.
- Parity: `proseweight scan <same prompt> --seed 42 --json cli.json` matches the web verdict for the same settings.

## Scenario 7 — CPU fallback (edge case)

On a machine with no GPU, Scenario 1 completes on a small model and the report's `run.subject_model.runtime == "cpu"`.

## Release 2 spot-checks

```bash
proseweight duel A.md B.md --instruction i7 --export duel.html   # US5: winner only if P(|diff|>ROPE) clears; self-contained HTML
proseweight grid prompt.md --models qwen2.5-0.5b,qwen2.5-1.5b,qwen2.5-3b   # US8: per-model, no universal score
proseweight diff v1.md v2.md    # US9: weight deltas, added/removed, flagged regressions
proseweight export out.json --html report.html --png card.png   # US10: opens offline, no server
```
Open `report.html` with no server running → renders fully (self-contained); `card.png` is the summary card.

## Release 3 spot-checks

```bash
proseweight lint ./CLAUDE.md --baseline weights.json    # US12: exit 0 within thresholds; 1 on regression/dead-weight; 3 on scoping confound
proseweight serve --port 8799    # US13: GET /health, POST /weight per contracts/api.md
```

## Gate C (flagship duel, process)

The vivid-vs-beige duel is published with full data regardless of outcome (SC-012) — a null result is still published. This is a definition-of-done check on the Release 2 article, verified by the article existing with its data, not by a command.

## Success-criteria coverage map

| Scenario | Covers |
|---|---|
| 1, 5 | US1, US2, FR-009/010/011/012/013/019 |
| 2 | SC-002, FR-017 (Gate B) |
| 3 | SC-001 (Gate A) |
| 4 | FR-002 |
| 6 | SC-006, SC-007, US3, US4 |
| 7 | FR-020 CPU fallback |
| R2/R3 | US5–US13, FR-024/027/028/029/031/032 |
| Gate C | SC-012 |
