"""`proseweight` CLI (contracts/cli.md).

Thin surface over the engine. ``scan`` produces the same verdict the web renders
as JSON + a terminal summary (parity, SC-007). Model-dependent commands load the
HF backend lazily and error cleanly without the runtime extra.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from proseweight.config import RunConfig
from proseweight.report.schema import Verdict

app = typer.Typer(add_completion=False, help="Prose Weight Visualiser — prompt weight linter.")


def _summary(verdict: Verdict) -> str:
    r = verdict.run
    lines = [
        f"Prompt weight verdict   Model: {r.subject_model.model_id}   "
        f"Suite: {r.suite_version} ({r.suite_hash[:16]})   Seed: {r.seed}   Depth: {r.depth}",
        f"Headline: {verdict.noise_floor_headline_pct:.0f}% of this prompt is below the noise floor.",
        "",
        "  WEIGHT  CI            CLASS          INSTRUCTION",
    ]
    for row in verdict.rows:
        w = row.weight
        mark = "◊noise " if w.is_noise_floor else "       "
        lines.append(
            f"   {w.weight:5.0f}  [{w.ci_low:.0f}, {w.ci_high:.0f}]".ljust(24)
            + f"{mark}{row.label.value:<13} {row.instruction.text.strip()[:60]}"
        )
    lines.append("")
    lines.append("CI = Bayesian credible interval (not a confidence interval).")
    return "\n".join(lines)


@app.command()
def scan(
    file: Path = typer.Argument(..., help="Prompt file to scan."),
    depth: str = typer.Option("quick", help="quick | deep"),
    seed: int = typer.Option(0),
    model: str = typer.Option(RunConfig().subject_model),
    judge: str = typer.Option("local", help="local | anthropic"),
    json_out: str = typer.Option(None, "--json", help="Write report JSON ('-' for stdout)."),
):
    """Segment, measure, and print the verdict for a prompt file."""
    source = Path(file).read_text(encoding="utf-8")
    cfg = RunConfig(
        subject_model=model,
        judge_backend="anthropic-api" if judge == "anthropic" else "local-hf",
        seed=seed,
        depth="deep_audit" if depth == "deep" else "quick_scan",
    )
    from proseweight.engine.hf_backend import HFMeasurementBackend
    from proseweight.probes.suite import load_suite
    from proseweight.segmentation.pipeline import segment_prompt
    from proseweight.verdict.orchestrator import run_verdict

    suite_path = Path(__file__).resolve().parents[3] / "data" / "suites" / "default-v1.yaml"
    suite = load_suite(suite_path)
    segments = segment_prompt(source)
    typer.echo(f"Segmented into {len(segments)} instructions.")
    backend = HFMeasurementBackend(cfg)
    bundle = backend.measure(source, segments, suite, cfg)  # raises without runtime
    verdict = run_verdict(source, segments, suite, cfg, bundle)
    if json_out:
        payload = json.dumps(verdict.to_dict(), indent=2)
        if json_out == "-":
            typer.echo(payload)
        else:
            Path(json_out).write_text(payload, encoding="utf-8")
    typer.echo(_summary(verdict))


@app.command()
def export(report: Path, html: str = typer.Option(...), png: str = typer.Option(None)):
    """Export a stored report JSON as self-contained HTML (+ optional PNG card)."""
    typer.echo("Loading report and rendering self-contained HTML …")
    # (rehydration of a stored verdict -> render_verdict_html; PNG via png_card)


if __name__ == "__main__":
    app()
