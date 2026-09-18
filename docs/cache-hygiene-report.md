# Cache hygiene: a before/after on my own instruction files

Run date: 2026-09-18. Tool: `proseweight cache lint` (CacheScope static lint, pricing table
`2026-09`). This records what CacheScope found when I pointed it at the three instruction files
that load into every Claude session on this machine, what I changed, and what the numbers do and
do not mean. It ends with why this belongs in OmnisRouter or OmnisVigil as a cost lever.

## What was checked and fixed

Three files load as governing instructions on every request: the global `~/.claude/CLAUDE.md`, the
personal-projects `C:\projects\personal\CLAUDE.md`, and the binding `~/.claude/constitution.md`.
CacheScope flagged CRLF line endings on two of the three. I converted both to LF (byte for byte,
content identical, only the endings changed) and re-linted to confirm.

| File | Before | After | Whole-file estimate (see below) |
|---|---|---|---|
| `~/.claude/CLAUDE.md` | already LF, clean | unchanged | none |
| `C:\projects\personal\CLAUDE.md` | 79 lines, all CRLF | LF, lint clean | ~£5.30 / month |
| `~/.claude/constitution.md` | 468 lines, all CRLF | LF, lint clean | ~£33.60 / month |

Both conversions re-lint clean. The global file was fine to start with.

## What the "savings" actually are, and what they are not

Read this part before quoting any figure.

**These are predicted costs, not measured savings.** The static lint reads bytes and predicts; it
does not watch your real traffic. A measured figure needs the recording proxy, which a Claude
subscription cannot use.

**Do not sum the per-line findings.** The lint emits one finding per CRLF line, so the personal
file produced 79 and the constitution produced 468, each with its own descending pound figure.
Adding them (it would read £229 and £7,800) is nonsense: they are overlapping estimates of a single
problem, that the file is CRLF. One file, one fix. The only figure worth citing is the whole-file
one, which is the cost if that file's cached prefix recomputes on every request.

**The whole-file figure, shown transparently** (Principle XII, explain every number). It is
`monthly_requests x (file_bytes / bytes_per_token) x base_input_rate x (write_mult - read_mult) x
FX`, with the table's defaults (1,000 requests/month, 4 bytes/token, Opus-5 at $5/MTok, 1.25x write,
0.1x read, FX 0.79):

- personal `CLAUDE.md`: 4,737 bytes -> ~1,184 tokens -> £0.0054/request -> **£5.38/month**
- `constitution.md`: 29,573 bytes -> ~7,393 tokens -> £0.0336/request -> **£33.58/month**

**And even that is contingent.** A file that is stably CRLF caches fine, because the bytes are the
same every request. CRLF costs you only when it drifts: mixed with LF content, or normalised
differently by git or an editor across machines and runs. So what the lint really flags is a drift
risk, and what the conversion bought is the removal of that risk on two always-loaded files, for
free. Whether it was costing anything yet depends on whether drift was happening. I have not
measured that it was.

So the honest summary: no confirmed saving to bank. Two real risks removed at no cost, with a
predicted exposure of roughly £5 and £34 a month per file under stated assumptions if they had
drifted on every request.

## Why this belongs in OmnisRouter / OmnisVigil

The interesting part is that the subscription's weakness is the proxy's strength. OmnisRouter sits
in the request path, so it sees the exact on-wire bytes, the real `usage`, and the real cache
breakpoints. It can turn every prediction above into a measured pound figure, which CacheScope's
subscription path never can. That is the same split the contracts were built around: OmnisRouter
captures, the cost core analyses, OmnisVigil reports.

Cache-waste reduction is a **second, independent lever** next to what OmnisRouter already does.
Routing to the cheapest capable model cuts the per-token price. Cache hygiene cuts the number of
tokens you pay full or write price for, on the same model. They stack, and neither touches output
quality.

Concrete levers worth building, roughly in order of effort against payoff:

- **Line-ending normalisation.** Normalise request bytes to LF before forwarding. Cheap, safe, and
  it kills the exact issue found here at the proxy rather than asking every user to fix their files.
- **Stable-prefix enforcement.** Warn (or reorder) when a volatile header, a timestamp, or an
  unsorted tool list sits before a cache breakpoint, where it silently busts the prefix every call.
- **Measured waste attribution.** Because the proxy has real `usage`, report actual pounds lost to
  cache misses per cause, per project, per model, not a prediction. This is the headline OmnisVigil
  number: "cache misses cost you £X last week, here is the byte and the fix."
- **Auto-fix with receipts.** Where a fix is safe (line endings, whitespace), apply it in flight and
  show the before/after in the routing receipt, so the saving is visible rather than asserted.

The wedge is that most of this is free money: no quality trade, no model downgrade, just not paying
to rewrite a cache entry that a stray carriage return threw away.

## Honest limits carried over

- The per-line finding explosion (79, 468) is a reporting fault in the current lint; a whole-file
  CRLF should be one finding. Logged as tool work.
- The transcript-reconstruction cost path over-counts and is not trustworthy for a headline figure;
  only the byte-exact proxy path is. That is exactly the gap OmnisRouter closes.
- Every figure here is stamped to pricing version `2026-09` and FX 0.79, and moves when those do.
