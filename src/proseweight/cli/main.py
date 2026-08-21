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
def export(
    report: Path,
    html: str = typer.Option(..., "--html", help="Output HTML path."),
    png: str = typer.Option(None, "--png", help="Optional PNG summary-card path."),
):
    """Export a stored report JSON as self-contained HTML (+ optional PNG card)."""
    from proseweight.report.export_html import export_html
    from proseweight.report.png_card import export_png_card
    from proseweight.report.store import load_verdict

    verdict = load_verdict(report)
    out = export_html(verdict, html)
    typer.echo(f"Wrote self-contained HTML: {out}")
    if png:
        export_png_card(verdict, png)
        typer.echo(f"Wrote PNG summary card: {png}")


@app.command("diff")
def diff_cmd(
    v1: Path = typer.Argument(..., help="Baseline verdict JSON."),
    v2: Path = typer.Argument(..., help="New verdict JSON."),
    json_out: str = typer.Option(None, "--json"),
):
    """Diff two stored verdicts (weight changes, added/removed, regressions)."""
    from proseweight.diff.diff import diff_verdicts
    from proseweight.report.store import load_verdict

    d = diff_verdicts(load_verdict(v1), load_verdict(v2))
    if json_out:
        payload = json.dumps(d.to_dict(), indent=2)
        (typer.echo(payload) if json_out == "-" else Path(json_out).write_text(payload, encoding="utf-8"))
    typer.echo(f"{len(d.regressions)} regression(s), {len(d.added)} added, {len(d.removed)} removed.")
    for r in d.regressions:
        typer.echo(f"  REGRESSION {r.delta:+.0f}: {r.text[:60]}")
    if d.blend_config_changed:
        typer.echo("  NOTE: blend config differs between runs (confound, not a regression).")


@app.command()
def lint(
    report: Path = typer.Argument(..., help="Current verdict JSON."),
    baseline: str = typer.Option(..., "--baseline", help="Baseline weights JSON."),
):
    """CI gate: fail if a load-bearing instruction regressed or dead weight grew."""
    from proseweight.ci.lint import Baseline
    from proseweight.ci.lint import lint as run_lint
    from proseweight.report.store import load_verdict

    result = run_lint(load_verdict(report), Baseline.load(baseline))
    for m in result.messages:
        typer.echo(m)
    typer.echo("OK" if result.ok else f"FAILED (exit {result.exit_code})")
    raise typer.Exit(result.exit_code)


if __name__ == "__main__":
    app()
