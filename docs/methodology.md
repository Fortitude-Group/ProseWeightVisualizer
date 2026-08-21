# How Prose Weight Visualiser measures a prompt

This is the honest account of what the tool does, what the numbers mean, and where they stop meaning anything. If you're going to cut lines from a production prompt on the strength of a score, you deserve to know how that score was made. So here it is, without the hand-waving.

## The one-sentence version

We remove an instruction, re-run a fixed set of tasks, and measure how much the model's behaviour changed. That change, aggregated and given a confidence interval, is the instruction's weight. Attention heatmaps are a supporting visual, never the verdict.

## Why ablation, not attention

Attention visualisation is seductive and mostly wrong as an explanation. It shows you where a model looks, which is not the same as what it obeys. You can stare at a bright attention band over a sentence the model completely ignores, and a faint one over the sentence doing all the work. The literature has been saying "attention isn't explanation" for years, and it's right.

So attention does one job here: it's a cheap pre-screen. It ranks instructions cheaply so the expensive step, ablation, spends its budget on the candidates most likely to matter. It also earns a spot in the "how it works" tab as an anatomy picture. It never sets a weight. That ordering is structural, not a disclaimer we bolted on at the end, and you'll find it stated on every surface the tool produces.

Ablation is the causal test. Take the full prompt, run the probe suite, record the behaviour. Take the prompt minus one instruction, run the same probes, record again. The difference is what that instruction was buying you. Do it for every instruction and you have a ranked account of the prompt, grounded in behaviour rather than vibes.

## The probe suite

Weight is always weight *against a set of tasks*. There's no universal prompt score, and we refuse to imply one. The default suite is twelve small tasks chosen to be discriminating for instruction-following: deferral (does the model do the work or hedge), format compliance, tone, refusal boundaries, and stacked constraints. Tasks with one obviously correct answer regardless of the prompt (arithmetic, factual recall) tell you nothing about instructions, so they're deliberately absent.

The suite is visible, versioned, and swappable. Every result records the suite version and a content hash, and the tool refuses to attribute a result to a version whose file doesn't match the recorded hash. Bring your own suite in promptfoo format if the default doesn't reflect what you actually care about. The weights will then be honest about being weights against *your* tasks.

A probe that never distinguishes any instruction is dead weight in the instrument, and the same logic that grades your prompt grades the suite. Low-discrimination and saturated probes get flagged rather than silently trusted.

## How a weight is computed

Each ablation produces three signals per probe:

- a judge score, from a separate local model scoring the output against the probe's rubric on a fixed 0 to 4 scale,
- a programmatic check, the deterministic pass or fail on a defined property (valid JSON, exact word count, and so on),
- an embedding distance between the full-prompt and ablated outputs.

These combine with fixed, documented weights (judge 0.5, programmatic 0.3, embedding 0.2). The weights are frozen and *validated* against a rigged test, never *fitted* to it. More on that below. The judge dominates because it's the only signal that's both aimed at what each probe actually cares about and available for every probe, including open-ended prose with no crisp check. Embedding distance is the cheap blunt floor: it catches gross drift the judge might miss, and it's kept at a low weight because it can't tell you whether a change was compliant or not.

The statistics are Bayesian throughout. Every weight is a posterior with a credible interval, not a point estimate pretending to be certain. We use conjugate posteriors and the Bayesian bootstrap, computed in plain numpy, with no sampling machinery whose results wobble across hardware. Given the same seed, a fully local run reproduces the same numbers exactly.

Scoring dozens of instructions at once is exactly where naive statistics lie to you: run enough comparisons and a few will look real by chance. The Bayesian answer is partial pooling. Noisy, extreme per-instruction estimates get shrunk toward the group in proportion to their uncertainty, using a closed-form empirical-Bayes step. That's the principled substitute for a frequentist multiple-comparisons correction, and it means we never quietly rack up false positives across a long prompt.

## The noise floor

This is the part most tools skip, and it's the part that makes the rest trustworthy. An instruction whose credible interval overlaps zero effect is reported as "not distinguishable from noise", rendered visibly differently from a genuinely low score. A low weight says "this does a little". The noise floor says "we can't tell this does anything at all". Those are different claims and the tool never blurs them.

The headline number on every report is the fraction of the prompt sitting below that floor. If a third of your system prompt can't be distinguished from noise against these tasks, that's the first thing you should see.

## What the numbers do not mean

- **Not a universal quality score.** A weight is specific to the probe suite and the model it was measured on. The model comparison grid exists precisely because prompt advice is model-specific, and it never collapses to a single cross-model number.
- **Not a verdict from attention.** If a report ever appears to rank something on attention alone, that's a bug, not a feature.
- **Not a rewriter.** The tool measures and classifies. It'll hand you a suggested cut list as a report artefact, but it won't write or edit your prompt for you.
- **Not proof about the wider world.** These are results against a defined set of tasks on a defined model. They generalise as far as those tasks resemble your real workload, and no further. Say the suite matched your workload, or don't lean on the number.

## Honesty gates

Three checks run on the instrument itself, and they're build gates, not afterthoughts.

The first is a rigged test. We feed the tool a synthetic prompt with planted ground truth: some instructions the probes directly test, plus planted no-op sentences that do nothing. The verdict has to rank every planted load-bearing instruction above every no-op, and park the no-ops in the noise floor, in at least ninety per cent of deep-audit runs. If the instrument can't pass a test we rigged for it to pass, nothing downstream is worth publishing. And crucially, a failure here is a signal about the instrument, not permission to tune the blend weights until it passes. That would make the whole check circular and worthless.

The second is reproducibility. Two deep audits of the same prompt with the same seed produce identical verdicts. Different seeds agree on the load-bearing and decorative classifications at least eighty-five per cent of the time, with the disagreements confined to scores whose intervals overlap anyway. If verdicts flap, we tighten the run count before adding features.

The third is a promise about our own flagship result. We ran a vivid directive against a beige equivalent on a deferral-prone task, and committed in advance to publishing the outcome whatever it was. A null result is still a result, and "I wanted the CAPS to matter, here's what the data actually said" is a more useful article than quietly burying it.

## Known limitations

- **Judge noise.** A model scoring outputs adds its own variance. We measure it directly by re-scoring identical text, fold it into the intervals rather than averaging it away, and fail the build loudly if a local greedy judge isn't near-deterministic (which usually means a missing flag, not real uncertainty).
- **Embedder truncation.** The embedding signal runs on a small model with a bounded context window. Probe outputs are meant to be short, but a very long output can lose its tail silently. Worth knowing before you read too much into that signal.
- **The optional API judge.** You can swap in a frontier API model as the judge. It's legitimate (judging needs no attention access), but API models aren't seed-deterministic, so any run using one is flagged best-effort and the same-seed reproducibility guarantee is explicitly waived. We measure and report its self-consistency noise so you can see why.
- **Candidate-only conflict detection.** Full pairwise ablation is combinatorial, so we only check the pairs the single-instruction pass flags as worth checking. A conflict between two instructions that both looked inert on their own could be missed.
- **Small local models.** The default subject is a small instruct model, chosen so a scan finishes on consumer hardware. Behaviour on a frontier model may differ, which is the whole reason we scope every number to its model rather than pretending otherwise.

If any of this changes how you'd read a report, good. That was the point.
