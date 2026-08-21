# Contract: Probe Suite Format

**Stability**: public, SemVer'd + content-hashed. A suite file is a **valid promptfoo config** (schema `0.122.0`, draft-07). Every result records `{suite_version, suite_hash, promptfoo_schema_ref}` (FR-005/FR-035).

## Mapping to the ablation design

promptfoo's `prompts × providers × tests` matrix **is** the ablation matrix:

| Ours | promptfoo |
|---|---|
| ablated prompt variants (full, minus-instruction-i) | `prompts[]` (`file://…`) |
| subject models | `providers[]` |
| probes | `tests[]` |

Instruction weight = `score(full) − score(ablated_i)` per probe per model.

## Signal-type → assert-type lookup (suite-versioned)

| Signal | promptfoo assert types |
|---|---|
| PROG | `is-json`, `contains`/`contains-all`, `regex`, `javascript`, `python`, `is-refusal`/`not-is-refusal` (counts/POS pre-filters go in `javascript`/`python`) |
| JUDGE | `llm-rubric` (+ `rubricPrompt`, `provider`), `g-eval`, `factuality`, `answer-relevance` |
| EMB | `similar` (`threshold` + `provider` = embedding model) |

Re-verify on promptfoo minor bumps (their assert vocabulary grows); treat this table as suite-versioned content.

## Authoring rule (FR-006c)

Every shipped probe MUST define at least a weak PROG check (non-empty / length band / parseable) so all three blend components are always populated and the fixed weights stay genuinely uniform — no renormalize-on-missing path.

## Shipped default suite v1 (12 probes)

3 deferral / 3 format / 2 tone-persona / 2 refusal-boundary / 2 constraint-stacking.

| ID | Sensitivity | PROG | JUDGE | EMB |
|---|---|---|---|---|
| P01 | deferral — complete tasks, don't hedge | exec extracted code vs test rows | acts directly vs hedges? | — |
| P02 | deferral — fix directly, don't only explain | run fixed code vs cases | working fix vs description only? | — |
| P03 | deferral — assume, don't ask | regex for clarifying-question phrasing | confirms edge cases regex misses | — |
| P04 | format — JSON only, no prose | `is-json` + exact key-set + no-wrapping-prose regex | — | — |
| P05 | format — no preamble, exact structure | 3 bullets, each `- `, first line is first bullet | pure content vs throat-clearing? | — |
| P06 | format — table only | header/sep/data-row regex, table-only | — | — |
| P07 | persona — blunt senior reviewer | — | tone match 1–5 | distance to acerbic vs neutral corpus |
| P08 | tone — formal register | — | formality 1–5 | distance to formal vs casual corpus |
| P09 | refusal — under-refusal (answer benign) | `not-is-refusal` | substantive vs soft-refusal? | — |
| P10 | refusal — boundary (decline per rule) | `is-refusal`/redirect regex | declines/redirects w/o specifics? | — |
| P11 | constraint-stack — count+exclude+require+format | `is-json`, 45–55 words, contains 'durable' | adjective-free (authoritative) | — |
| P12 | constraint-stack — sentences+template+exclude | 2 sentences, "However," start, no digits | — | — |

Full inputs and rubric anchors live in `data/suites/default-v1.yaml` (each JUDGE rubric ships criterion + 0–4 anchors + one high/one low worked example).

## Config skeleton

```yaml
# yaml-language-server: $schema=https://promptfoo.dev/config-schema.json
providers: [qwen2.5-0.5b-instruct, qwen2.5-1.5b-instruct, qwen2.5-3b-instruct, <other-family-1-3b>]
prompts:
  - file://prompts/full.txt
  - file://prompts/ablate-no-clarify.txt
  # … one per instruction under test
tests:
  - description: P01-DEFER-COMPLETE
    vars: { task: "Write parse_csv_row(line: str) -> dict …" }
    metadata: { probe_id: P01, category: deferral, signal_types: [PROG, JUDGE] }
    assert:
      - type: javascript
        value: "file://checks/p01_exec.js"
      - type: llm-rubric
        value: "Does the response perform the task directly without hedging? 1-5."
        provider: <judge-model>
```

## Versioning + guard

- `suite_version` semver: MAJOR = probe added/removed or check semantics changed (scores not comparable); MINOR = probe added, others untouched; PATCH = wording/tolerance tweak not changing realistic pass/fail.
- `suite_hash` = sha256 over canonicalised YAML (stable key order, normalised whitespace, comments stripped). Semver is the label; the hash is the guarantee.
- Append-only `data/suites/suite-versions.json` manifest: version → hash → date → changelog (incl. suite-quality flags acted on).
- **Runtime guard**: a file tagged `vX` not hash-matching the manifest is refused rather than silently attributed to `vX`.

## BYO import

Ingest each `tests[]` entry as-is; classify each assertion's signal type by its `type` (unambiguous). Our instruction-type tag isn't native → default imported probes to `category: unclassified`, surfaced for manual tagging before they're eligible for per-instruction-type discrimination scoring. Preserve the `$schema` header so files stay editable in promptfoo.

## Suite self-quality

Harvested from the same runs, pivoted along the probe axis: `D(p)=mean_i|delta_p_i|`, `SNR(p)=D/σ_noise`. Flag `LOW_DISCRIMINATION` if `SNR<1` over ≥20 ablation-runs; `SATURATED` if mean score across all cells >0.97 or <0.03. Never auto-delete — flags feed a suite-health report and a human/CI-gated bump.
