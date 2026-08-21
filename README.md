# Prose Weight Visualiser

A measurement instrument and linter for prompts. Paste a system prompt, a `CLAUDE.md`, or a
set of agent instructions, and get back which lines actually carry behavioural weight and
which are ballast, measured empirically against a local model instead of argued from taste.
Every score comes with a credible interval, and it runs entirely on your machine.

It's ablation-led: to score a line, the tool removes it, re-runs a fixed suite of probe
tasks, and measures how much the model's behaviour changed. Token attention is used only as
a cheap pre-screen and an explainer, never as the verdict.

## What it does

- Splits a prompt into discrete instructions.
- Scores each one 0 to 100 by ablation, and classifies it load-bearing, contributing,
  decorative, or contradicted.
- Puts a Bayesian credible interval on every score, and marks a line as noise when its
  effect can't be told apart from run-to-run variance, rather than dressing it up as a low
  number.
- Runs a phrasing duel: two wordings of the same instruction go head to head, and it names a
  winner only when the difference clears a region of practical equivalence.
- Two surfaces, same numbers: an interactive web app and a CLI.

## Requirements

- Python 3.11 or newer.
- A local model runtime. The easiest is [Ollama](https://ollama.com): no gated downloads, no
  GPU wrangling, and it manages the models for you. A CUDA GPU helps but isn't required for
  the small models.

## Quickstart (Ollama, recommended)

1. Install Ollama, then pull the three models it uses:

   ```bash
   ollama pull qwen3.5:2b            # subject: the model under test
   ollama pull qwen2.5:7b-instruct   # judge: scores compliance (never judges itself)
   ollama pull nomic-embed-text      # embedder: output-divergence signal
   ```

2. Install the package (editable, so the shipped probe suite is found in place):

   ```bash
   pip install -e ".[web]"
   ```

3. Run the web app:

   ```bash
   proseweight web
   ```

   Open <http://127.0.0.1:8790>, paste a prompt, and click **Measure weights**. The **Duel**
   tab pits two phrasings against each other.

Or measure straight from the command line:

```bash
proseweight scan your-prompt.txt --depth deep --probes 6 --n 3
```

You get a terminal readout with a weight bar, a 95% credible interval, and a verdict per
line, plus a machine-readable report with `--json report.json`.

A deep audit runs a lot of model calls and takes a few minutes; the 7B judge is the pacing
item. Lower `--probes` and `--n` for a faster first look.

## The models

| Role     | Default               | Notes                                                        |
|----------|-----------------------|--------------------------------------------------------------|
| Subject  | `qwen3.5:2b`          | The model under test. A bigger subject (7B) discriminates better. |
| Judge    | `qwen2.5:7b-instruct` | A different model, so nothing judges its own output.         |
| Embedder | `nomic-embed-text`    | Semantic distance between outputs.                           |

All swappable:

```bash
proseweight scan p.txt --subject qwen2.5:7b-instruct --judge qwen3.5:4b
```

## Commands

- `proseweight scan <file>` measure a prompt and print the readout (`--json` for the report)
- `proseweight web` the interactive app (Scan and Duel)
- `proseweight export <report.json> --html out.html [--png card.png]` a self-contained report
- `proseweight diff <v1.json> <v2.json>` weight changes between two versions of a prompt
- `proseweight lint <report.json> --baseline weights.json` CI gate; exits non-zero on a
  load-bearing regression or a dead-weight budget breach
- `proseweight serve` a small local HTTP API

## How the weight is measured

For each instruction the tool removes it, re-runs the probe suite N times, and measures the
behavioural delta against the full prompt. The delta blends three signals with fixed,
documented weights: an LLM-judge rubric score, an embedding distance between outputs, and
task-specific programmatic checks. The statistics are Bayesian throughout, computed in
numpy: every weight is a posterior with a credible interval, and cross-instruction shrinkage
does the job a multiple-comparisons correction would. Attention is a pre-screen that ranks
which lines to ablate first, and an explainer under the "how it works" view. It never sets a
score.

## Honest limits

- Weights are specific to the probe suite and the model. There is no universal prompt score;
  the model-comparison view exists instead.
- Small models shift their output when you remove almost anything, so genuine dead weight is
  hard to surface without a fuller probe suite and a larger subject model.
- An optional frontier API judge (Anthropic, key from `ANTHROPIC_API_KEY` only) is available;
  runs that use it are flagged best-effort and waive same-seed reproducibility.

## Hugging Face runtime (instead of Ollama)

```bash
pip install -e ".[runtime]"
proseweight scan p.txt --backend hf --subject Qwen/Qwen2.5-1.5B-Instruct
```

This downloads the weights from the Hugging Face Hub and, realistically, wants a GPU.

## Predecessor

The original single-file attention demo (`attnscope` / `attnduel`) still lives in
`prose_weight_visualiser.py`. Its attention view became the "how it works" layer here, and
its two-prompt fight became the phrasing duel.

## Development

```bash
pip install -e ".[dev]"
pytest        # the deterministic engine is covered without any model runtime
ruff check .
```
