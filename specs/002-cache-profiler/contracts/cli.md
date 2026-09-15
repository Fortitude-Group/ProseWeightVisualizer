# Contract: CLI (`proseweight cache <sub>`)

**Stability**: public, SemVer'd. Breaking a command/flag/exit-code is a MAJOR bump with a migration note.
CacheScope adds a **`cache` command group** to the existing `proseweight` Typer app (a sibling of `scan`
/ `duel` / `lint`, registered additively — no change to `001` commands, FR-029). Every subcommand that
produces analysis emits the versioned `CacheScopeResult` JSON ([result-contract.md](./result-contract.md))
plus a human terminal summary.

## Group

```
proseweight cache <subcommand> [options]
```

Global options: `--db <path>` (capture store, default `./cache.db`), `--pricing <path>`
(default `./pricing.json`), `--json <path>` (`-` for stdout), `--no-color`, `--quiet`, `-v/--verbose`.

## Commands

### `proseweight cache lint <file>...` — Release 1

Static cache-hygiene lint — **no captured data, no API, no model runtime** (US2 / FR-006/007). Accepts
`CLAUDE.md`, the machine-wide `~/.claude/CLAUDE.md`, and `.kb/*.md` globs.

```
proseweight cache lint ./CLAUDE.md ~/.claude/CLAUDE.md .kb/*.md
```

- Prints each finding as a **prediction** (rule id, file, line/offset, estimated monthly cost) — never a
  measured verdict.
- `--baseline <file>` (Release 3, CI): regression gate. Exit `0` within tolerance; exit `1` on a
  cache-hostile regression, with the estimated monthly cost of the regression in the message; exit `2`
  usage/config error; exit `3` pricing/model mismatch vs baseline — a **confound**, reported distinctly,
  not a false regression (FR-025 edge). `--update-baseline` rewrites it.

### `proseweight cache serve` — Release 1

Start the local base-URL **recording reverse proxy** (R2). Bound to `127.0.0.1` (FR-005).

```
ANTHROPIC_BASE_URL=http://127.0.0.1:8790 <your app>     # after: proseweight cache serve --port 8790
```

- `--port`, `--upstream <url>` (default the real Anthropic API), `--diagnostics` (opt-in beta,
  passive/off by default; PAYG only — FR-014). Tees each turn into `--db` as an exact-confidence capture.

### `proseweight cache ingest <transcript-path>...` — Release 1 (basic) / R3 (byte-level)

Ingest Claude Code on-disk session transcripts (R7). R1 stores `usage`-level captures at a
`reconstructed_*` grade; R3 adds byte-level prefix reconstruction with an explicit confidence band and
`usage`-calibration (FR-024). `--watch` follows new turns.

### `proseweight cache analyse` — Release 2

Run lineage pairing → divergence → breakpoint → reconciliation → cost over the captured store; emit
`CacheScopeResult`. `--since <date>`, `--model <id>`, `--source <kind>`.

### `proseweight cache ledger` — Release 2

Aggregated waste (FR-018): headline figure + per-cause / per-period / per-model rollups. `--period
day|week|month`. Forks the meter by billing model (measured £ for PAYG, quota + labelled shadow-price
for subscription).

### `proseweight cache export <result.json> --html <path> [--png <path>]` — Release 2

Self-contained HTML (+ optional PNG) of the three views via the brand-neutral render adapter (FR-023a).
Interactivity (click-a-miss → byte diff) is inlined; no running service. `--theme neutral|fortitude`
(default `neutral`).

## Terminal summary (stable columns — `ledger`)

```
CacheScope · Ledger   store cache.db   pricing 2026-09 (eff 2026-09-01, fx 2026-09-01)   meter: subscription (shadow-price)
Headline: CRLF line endings cost you £4.12 this month (shadow-price) — 8,000 quota tokens.

  CAUSE               MONTH £*     QUOTA TOK   TURNS   TOP FILE
  crlf_drift          4.12         8,000       12      CLAUDE.md:3
  volatile_header     0.90         1,800        4      .kb/context.md:2
  * £ = shadow-price counterfactual on a subscription, not a bill.  Excludes non-avoidable edits and never-cached prefixes.
```

Every figure states its pricing/effective/FX stamp; a subscription pound value is always flagged a
shadow-price (SC-002/006). The excluded-set note satisfies Principle XII (a filtered count says what it
omits).

## Determinism & keys

Identical captures + identical `pricing.json` ⇒ byte-identical `CacheScopeResult` JSON (Principle IV).
No API key is ever a flag: `serve --diagnostics` and any live `count_tokens` refinement read
`ANTHROPIC_API_KEY` from the environment only (Security Rules).
