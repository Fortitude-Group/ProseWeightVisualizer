# Contract: CLI (`proseweight`)

**Stability**: public, SemVer'd. Breaking a command/flag/exit-code is a MAJOR bump with a migration note.

The CLI is a thin surface over the engine. Every subcommand that produces a verdict emits the same versioned report JSON the web surface renders (parity — SC-007) plus a human terminal summary.

## Global

```
proseweight <command> [options]
```

Global options (all commands): `--model <id>`, `--suite <path|version>`, `--seed <int>`, `--depth quick|deep`, `--json <path>` (write report JSON; `-` for stdout), `--judge local|anthropic`, `--no-color`, `--quiet`, `-v/--verbose`.

Determinism: with a fully-local judge, identical `(<input>, --model, --suite, --seed, --depth, blend_config)` yields byte-identical report JSON (FR-017). `--judge anthropic` sets `reproducibility: best_effort` and requires `ANTHROPIC_API_KEY` in the environment (never a flag).

## Commands

### `scan <file>` — Release 1

Segment, measure, and print the verdict for a prompt file (US4).

```
proseweight scan ./CLAUDE.md --depth deep --seed 42 --json report.json
```

- Prints: headline noise-floor %, ranked instruction table (weight, CI, classification), dead-weight cut list with token cost, conflicts, suite version + model scoping.
- `--segments <path>`: supply a reviewed/edited segmentation instead of auto-segmenting (respects FR-002; auto-segmentation prints and requires `--yes` or an interactive confirm before a run).
- Exit `0` on a completed scan; non-zero only on error (a scan makes no pass/fail judgement — that's `lint`).

### `duel <fileA> <fileB> --instruction <id>` — Release 2

A/B two phrasings of one instruction (US5). Prints effect size, `P(|diff|>ROPE)`, and a winner only if it clears the threshold. `--export <path.html>` writes the shareable artefact.

### `emphasis <file> --instruction <id>` — Release 2
### `position <file> --instruction <id>` — Release 2
### `grid <file> --models <id,id,id>` — Release 2

Per-model weights side by side (US8); never prints a single cross-model score.

### `diff <fileV1> <fileV2>` — Release 2

Weight deltas, added/removed, flagged regressions (US9). Flags `blend_config_changed` as a confound.

### `export <report.json> --html <path> [--png <path>]` — Release 2

Self-contained HTML + PNG summary card from a stored report (US10).

### `lint <file> --baseline <weights.json>` — Release 3 (CI)

Regression gate (US12).

- Exit `0`: all within thresholds.
- Exit `1`: a load-bearing instruction's weight dropped beyond `--load-bearing-threshold`, **or** new dead weight exceeded `--dead-weight-budget`.
- Exit `2`: usage/config error.
- Exit `3`: baseline scoping mismatch (different suite/model/blend_config) — a confound, reported distinctly, not a silent pass or a false regression.
- `--update-baseline`: rewrite the baseline from the current run.

### `serve` — Release 3

Start the local watch-mode HTTP daemon (see [api.md](./api.md)). `--host`, `--port`.

## Terminal summary format (stable columns)

```
Prompt: CLAUDE.md   Model: Qwen2.5-1.5B-Instruct   Suite: v1.3.0 (sha256:ab..)   Seed: 42   Depth: deep
Headline: 34% of this prompt is below the noise floor.

  WEIGHT  CI            CLASS          INSTRUCTION
   92     [88, 95]      load-bearing   "Never defer; attempt the fix directly."
   ...
    3     [0, 9]  ◊noise decorative    "Be helpful and thorough."     ← ◊ = not distinguishable from noise
```
`CI` is the Bayesian **credible interval** (posterior 95% by default), not a frequentist confidence interval — the whole tool is Bayesian (see spec Clarifications). `◊` (or an equivalent marker) renders the noise-floor state distinctly from a low weight (FR-016). Attention is never shown as a standalone score here.
