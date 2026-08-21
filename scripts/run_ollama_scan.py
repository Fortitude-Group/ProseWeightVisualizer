"""Run a REAL scan through Ollama (subject + judge + embedder over the local API).

Usage:
    python scripts/run_ollama_scan.py [prompt_file] [--probes N] [--deep]

Defaults to a small built-in prompt and a 4-probe subset for a quick first run.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from proseweight.config import RunConfig
from proseweight.engine.ollama_backend import OllamaMeasurementBackend
from proseweight.probes.suite import load_suite
from proseweight.segmentation.pipeline import segment_prompt
from proseweight.verdict.orchestrator import run_verdict

SUBJECT = "qwen3.5:2b"
JUDGE = "qwen2.5:7b-instruct"
EMBED = "nomic-embed-text"

DEFAULT_PROMPT = (
    "Return every answer as strict JSON only, with no prose.\n"
    "Be helpful and thorough in your responses.\n"
    "Never apologise or add disclaimers.\n"
)


def main() -> None:
    args = sys.argv[1:]
    n_probes = 4
    depth = "quick_scan"
    n_samples = 1
    temperature = 0.7
    prompt_file = None
    skip = set()
    for i, a in enumerate(args):
        if i in skip:
            continue
        if a == "--probes":
            n_probes = int(args[i + 1])
            skip.add(i + 1)
        elif a == "--n":
            n_samples = int(args[i + 1])
            skip.add(i + 1)
        elif a == "--temp":
            temperature = float(args[i + 1])
            skip.add(i + 1)
        elif a == "--deep":
            depth = "deep_audit"
        elif not a.startswith("--"):
            prompt_file = a

    source = Path(prompt_file).read_text(encoding="utf-8") if prompt_file else DEFAULT_PROMPT
    root = Path(__file__).resolve().parents[1]
    suite = load_suite(root / "data" / "suites" / "default-v1.yaml")
    suite.probes = suite.probes[:n_probes]  # subset for a fast first run
    segments = segment_prompt(source)

    print(f"Subject={SUBJECT}  Judge={JUDGE}  Embed={EMBED}")
    print(f"{len(segments)} instructions, {len(suite.probes)} probes, depth={depth}, "
          f"N={n_samples} samples, temp={temperature}\n")

    cfg = RunConfig(subject_model=SUBJECT, seed=42, depth=depth, posterior_samples=3000, n_runs=n_samples)
    backend = OllamaMeasurementBackend(
        SUBJECT, JUDGE, EMBED, seed=42, n_samples=n_samples, temperature=temperature
    )

    t0 = time.time()
    bundle = backend.measure(source, segments, suite, cfg)
    print(f"measurement: {time.time() - t0:.0f}s")
    verdict = run_verdict(source, segments, suite, cfg, bundle, run_id="ollama-run")
    verdict.validate()

    print(f"\nHeadline: {verdict.noise_floor_headline_pct:.0f}% below the noise floor\n")
    print(f"{'WEIGHT':>7}  {'CI':>12}  {'CLASS':<13} INSTRUCTION")
    for r in verdict.rows:
        w = r.weight
        nf = " noise" if w.is_noise_floor else "      "
        print(f"{w.weight:7.0f}  [{w.ci_low:3.0f},{w.ci_high:4.0f}]{nf} {r.label.value:<13} {r.instruction.text.strip()[:50]!r}")

    out = root / "results-ollama-verdict.json"
    import json

    out.write_text(json.dumps(verdict.to_dict(), indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
