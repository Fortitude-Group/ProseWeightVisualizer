# BRAINSTORM — Prose Weight Visualiser: prompt linter + attnscope + attnduel (Fortitude Omnis R&D build)
Folder: `ProseWeightVisualiser` | Status: R&D BUILD — full-scope mandate ("boil the ocean"), sequenced in releases, nothing dropped
Use with: `/speckit.specify` — paste the sections below as the feature description.
Working name "Prose Weight Visualiser" (PWV). CLI name `proseweight`. Rename freely.

---

## One-liner
A measurement instrument and linter for prompts: paste a system prompt and get back, with numbers and confidence intervals, which instructions actually carry behavioural weight and which are decorative — measured empirically against local models via ablation, attention analysis, and A/B behavioural testing — for anyone who maintains a system prompt, CLAUDE.md, or agent instructions and has no idea which lines do anything.

## Why (context — do not re-litigate in the spec session)
- Every team now maintains prompts that grew by accretion (system prompts, CLAUDE.md files, agent instructions). No tooling exists to tell which instructions are load-bearing and which are ballast. Prompt "engineering" is currently folklore.
- Attention visualisation alone is dismissed (fairly) as "attention isn't explanation". The credibility of this tool rests on being ablation-led: attention suggests, ablation proves. This ordering is a design commitment, not a preference.
- Two working predecessors exist and are absorbed into this project: **attnscope** (CLI, token-level attention scores over prompt tokens on local HuggingFace models) and **attnduel** (Gradio GUI, two adversarial prompts competing, token heatmap). They become the "how it works" layer, not the headline.
- Prior experiment exists: a promptfoo A/B test of a vivid directive ("BOIL THE OCEAN") vs a beige equivalent ("please be thorough") on a deferral-prone coding task. This becomes a first-class feature (duel mode) and the flagship write-up.
- The author's thesis, to be demonstrated with receipts: English prose skill is now a core engineering skill, and prompts deserve the measurement discipline we once applied to inner loops. The tool is the argument.
- This is R&D under Fortitude Omnis: public repo, public web demo, published methodology. Prompt regression testing in CI is the potential product wedge beyond the demo.
- Novel-findings potential (each is a publishable article): the emphasis audit (does CAPS/bold/"IMPORTANT:" measurably work?), the decay curve (system-prompt weight over conversation length), position sensitivity, and the dead-weight percentage of well-known public prompts.

## Target user
An engineer who owns a 200-line system prompt for a production agent. Every sprint someone adds "IMPORTANT: always…" to fix an incident, nothing is ever removed, and nobody can say what any line does. They want to paste the prompt and get a ranked verdict — keep, cut, fix the contradiction — with enough statistical honesty that they can defend the cuts in review. Secondary user: the author himself, in debates with peers, armed with charts.

## What to build (full scope, sequenced in three releases — ALL of it is in scope)

### Release 1 — the linter core

1. **Instruction segmentation.** Parse a pasted prompt into discrete instructions at sentence/clause level, respecting markdown structure, XML tags, lists, and headers. Segmentation is performed by a small local model (recursive: the model parses instructions for the instrument that measures the model). Segments are editable — the user can merge/split before a run. Everything downstream hangs off this.

2. **Probe-task suite.** A fixed, versioned suite of 10–15 tasks chosen to be small but discriminating for instruction-following differences (deferral-prone coding tasks, formatting compliance, tone adherence, refusal boundaries, constraint juggling). The suite is: (a) visible — shown in the UI and docs, never implicit; (b) swappable — bring-your-own-suite (promptfoo-compatible format preferred) so weights are explicitly "weight against these tasks"; (c) versioned — results always record the suite version. No universal prompt score is ever implied.

3. **Ablation engine.** For each instruction: remove it, re-run the probe suite, measure behavioural delta versus the full prompt. Deltas measured as output divergence via a blend of embedding distance, LLM-judge scoring against per-probe rubrics, and task-specific programmatic checks — not string diffs. This is the causal ground truth.

4. **Attention analysis (attnscope absorbed).** Token-level attention mass over prompt tokens during probe runs, aggregated per instruction. Used as the cheap pre-screen that ranks instructions for ablation priority, and as the "how it works" visual layer. Never used as the verdict on its own.

5. **Paraphrase sensitivity.** For each instruction, generate K paraphrases (same intent, different wording), re-run probes, measure output variance. High sensitivity = the wording itself is doing work; low = only the intent matters.

6. **Weight score.** A 0–100 behavioural weight per instruction blending: ablation delta (dominant), attention mass (early signal), paraphrase sensitivity. The blend is shown, not hidden — per-component scores visible on every instruction. Blend weights configurable; default documented and justified.

7. **The verdict report.** The linter's output: every instruction ranked, coloured, and classified into **load-bearing / contributing / decorative / contradicted**. "Contradicted" = instructions whose ablation *improves* compliance with another instruction. Report includes the headline number: "N% of this prompt is below the noise floor."

8. **Noise honesty (non-negotiable, built into Release 1, never deferred).** N runs per condition; confidence intervals on every score; an explicit "not distinguishable from noise" state rendered visually distinct from a low score; seed control for reproducibility; run-to-run variance reported. A verdict without intervals never ships.

9. **Tiered depth.** Two run modes from day one: **quick scan** (attention pre-screen + ablation of the top-ranked candidates only, minutes) and **deep audit** (full ablation matrix × N runs, designed to run overnight). Cost/time estimates shown before a run starts.

10. **Local model runtime.** One local HuggingFace model in Release 1, with the model abstraction designed for the Release 2 comparison grid (per-model results storage from the start). GPU-optional: degraded-but-functional on CPU for small models.

11. **Dead-weight detector.** Rule on top of measurement: instructions below the noise floor, listed with their cost (tokens spent) — "you are paying X tokens per call for sentences that do nothing."

12. **Conflict detector.** Pairwise ablation on candidate pairs flagged by the single-ablation pass (full pairwise is combinatorial; candidates only), surfacing instruction pairs that fight each other.

13. **Two famous-prompt teardowns, pre-loaded.** Full verdict reports on recognisable public/published system prompts (published Claude system prompt is fair game; pick a second well-known public one). Visitors see the verdict on a prompt they recognise without running anything. These are the marketing.

14. **Web UI + CLI.** Web: paste prompt → segment review → run config → live progress → verdict report, with the attention heatmap demoted to a "how it works" tab. CLI: `proseweight scan <file>` producing the same report as JSON + terminal summary. Both ship in Release 1; the web demo is the R&D-page embed.

### Release 2 — duels, comparison, diffing

15. **Phrasing duel mode (attnduel absorbed and grown up).** A/B any two phrasings of the same instruction across the probe suite with significance testing (effect size + p-value or Bayesian equivalent — spec session decides, but significance is mandatory). Side-by-side attention heatmaps as the supporting visual. Duel results exportable/shareable. The "BOIL THE OCEAN vs please be thorough" experiment re-run here as the flagship published duel.

16. **Emphasis audit.** Systematic measurement of formatting devices: CAPS, bold, "IMPORTANT:", exclamation marks, repetition, position in list. For a given instruction, auto-generate the emphasis variants, run the matrix, report which devices move weight on which model. Publishable as a standalone finding.

17. **Position sensitivity.** Move an instruction through prompt positions (top/middle/bottom, before/after related sections), re-measure weight. Per-model empirical answer to "does putting it first matter?"

18. **Model comparison grid.** Same prompt, weight scores across 3–4 local models side by side. Demonstrates that prompt advice is model-specific. The grid is the honest version of a universal score.

19. **Prompt diff.** Paste v1 and v2 of a prompt; see which instruction weights shifted, which instructions appeared/vanished, and whether any previously load-bearing instruction was accidentally neutered. Turns a one-shot tool into something teams re-run every prompt change.

20. **Report export.** Any verdict/duel/diff as a standalone, self-contained shareable HTML page (no server required to view), because these will be pasted into team Slacks. Include a compact PNG summary card for social embedding.

### Release 3 — decay, CI, ecosystem

21. **Decay curve.** Weight of system-prompt instructions as conversation length grows: instruction in turn 1, compliance measured at turns 1, 5, 10, 20 with synthetic filler conversation of controlled content. Output: the "your system prompt evaporates" chart, per instruction, per model. Most compute-hungry feature; deep-audit only; the best chart in the project.

22. **CI mode.** `proseweight lint CLAUDE.md --baseline weights.json` with exit codes: fail the build if a load-bearing instruction's weight drops beyond threshold after an edit, or if new dead weight exceeds a budget. GitHub Action wrapper. Baseline files checked into the repo like lockfiles. Prompt regression testing as a category basically doesn't exist; this is the product wedge.

23. **Watch mode / API.** Local daemon + small HTTP API so editors/agents can query weights during prompt editing. Minimal; exists to make integrations possible, not to be a platform.

24. **Public methodology paper/page.** A full written methodology (how weights are computed, what they mean, what they don't mean, known limitations) published alongside the tool. This is both honesty and citation-bait.

## Explicitly OUT of scope
- Hosted multi-tenant SaaS, accounts, billing. The web demo is a demo; CI mode runs on the user's hardware.
- Measuring against closed API models as the primary path (nondeterminism, cost, no attention access). A thin optional adapter for behavioural-only signals (ablation/duel deltas via API models, no attention) may be specced as future work, but local models are the instrument.
- Prompt *generation* or auto-rewriting. The tool measures and verdicts; it does not write prompts. (A "suggested cut list" is a report artefact, not a rewriter.)
- Universal cross-model "prompt quality score". Explicitly refused; the comparison grid exists instead.
- Fine-tuning, training, or model modification of any kind.
- Jailbreak/red-team tooling. Duel mode compares phrasings of legitimate instructions; the tool is not a bypass-finder and marketing copy never implies it.

## Technical kill criteria / honesty gates (build into the harness from day one)
- Gate A (instrument validity): on a synthetic prompt with planted ground truth (instructions known to be load-bearing because probes directly test them, plus planted no-op sentences), the verdict must rank all planted load-bearing instructions above all planted no-ops in ≥ 90% of deep-audit runs, and the noise-floor state must correctly capture the no-ops. If the instrument can't pass a rigged test, nothing downstream is publishable.
- Gate B (reproducibility): two deep audits of the same prompt, same seed → identical verdicts; different seeds → classification agreement ≥ 85% on load-bearing/decorative, with disagreements confined to interval-overlapping scores. If verdicts flap, tighten N before adding features.
- Gate C (the flagship claim): the BOIL-vs-beige duel result, whatever it shows, is published with full data — including if the vivid phrasing does NOT win. A null result is still an article ("I wanted CAPS to matter. Here's what the data said."). Pre-commit to publishing before running.
- Cost sanity: quick scan of a 50-instruction prompt completes in ≤ 10 minutes on a single consumer GPU; if not, shrink the probe suite or the pre-screen threshold before shipping.
- Reconsideration trigger: a credible open-source tool ships ablation-based prompt linting with published methodology first → pivot to the CI/diff/decay layers and interoperate rather than duplicate.

## Constraints & guardrails
- **Ablation-led, always.** Attention never appears as a verdict, only as pre-screen and explainer. Every public surface (UI, report, README, articles) states this ordering. This is the defence against the "attention isn't explanation" dismissal and it must be structural, not a disclaimer.
- **Honesty over drama.** Confidence intervals on everything; noise states rendered prominently; probe-suite dependence stated on every report ("weights measured against suite vX"); per-model scoping on every number. The tool's credibility is the entire point of putting it on an R&D page.
- **Sequencing:** Release 1 items 1–14 ship together as the public v1 (teardowns + web demo + CLI). Release 2 = duels/comparison/diff. Release 3 = decay/CI. Design decisions in R1 (per-model result storage, suite versioning, report schema) must anticipate R2/R3 — the spec session should treat the release boundaries as shipping order, not architectural walls.
- Stack as constraint, not design: model runtime will realistically be Python (HF/PyTorch); the CLI and report tooling should still install and run as a single command without the user hand-managing environments. Web demo hosting budgeted with a GPU-backed queue or degraded CPU mode; decide in spec.
- Repo public from day one; methodology page ships with v1, not after.
- Famous-prompt teardowns use only published/officially released prompts; no leaked material of ambiguous provenance; each teardown cites its source.
- Articles accompany each release (v1 verdict tool, the duel result, the emphasis audit, the decay curve) — treat each as part of that release's definition of done.

## Open questions for the spec session
1. Judge model for behavioural deltas: same local model judging itself (cheap, incestuous), a second local model, or a small ensemble? How is judge noise separated from subject noise in the intervals?
2. Divergence metric blend: embedding distance vs judge rubric vs programmatic checks — fixed blend, per-probe blend, or learned combiner validated against Gate A's planted ground truth?
3. Statistical machinery: frequentist (effect size + corrected p-values across many instructions — multiple-comparisons handling needed) or Bayesian (posterior intervals per weight)? Pick one and use it everywhere.
4. Segmentation model: which small local model, and what's the fallback when segmentation is wrong — pure manual editing, or rules+model hybrid?
5. First local model and the R2 grid roster: which 3–4 models (size classes, instruction-tuned variants) give the most interesting comparison per GPU-hour?
6. Probe suite composition: which 10–15 tasks maximise discrimination for instruction-following, and how is suite quality itself measured (a probe that never differentiates is dead weight in the instrument — pleasingly, the tool's own logic applies to its suite)?
7. Web demo compute: queue with a single GPU worker, CPU-only small model, or pre-computed results only (teardowns + duels live, paste-your-own runs locally via CLI)?
8. Decay-curve filler conversations: how is filler content controlled so decay isn't confounded by topical interference?
