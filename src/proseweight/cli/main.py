"""`proseweight` CLI (contracts/cli.md).

Thin surface over the engine. ``scan`` produces the same verdict the web renders
as JSON + a terminal summary (parity, SC-007). Model-dependent commands load the
HF backend lazily and error cleanly without the runtime extra.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from proseweight.config import RunConfig
from proseweight.report.schema import Verdict

# The readout uses block glyphs; force UTF-8 so it renders on a Windows cp1252 console.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

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


def _bar(weight: float, noise: bool, width: int = 18) -> str:
    fill = round(max(0.0, min(weight, 100.0)) / 100.0 * width)
    ch = "░" if noise else "█"
    return ch * fill + "·" * (width - fill)


def _readout(verdict) -> str:
    r = verdict.run
    lines = [
        f"Prose Weight · Readout   model {r.subject_model.model_id}   suite {r.suite_version}"
        f"   seed {r.seed}   {r.depth.replace('_', ' ')}",
        f"{verdict.noise_floor_headline_pct:.0f}% of this prompt is below the noise floor.",
        "",
        f"  WGT  {'weight 0-100':<18}   {'95% CI':<10}  VERDICT        INSTRUCTION",
    ]
    for row in verdict.rows:
        w = row.weight
        tag = "◊ noise" if w.is_noise_floor else row.label.value
        lines.append(
            f"  {w.weight:3.0f}  {_bar(w.weight, w.is_noise_floor)}   "
            f"[{w.ci_low:3.0f},{w.ci_high:3.0f}]  {tag:<13}  {row.instruction.text.strip()[:44]}"
        )
    if verdict.dead_weight:
        lines.append("")
        for d in verdict.dead_weight:
            lines.append(f"  dead weight: {d.instruction_id} costs {d.token_cost} tokens/call for no effect")
    lines.append("")
    lines.append("Ablation-led · CI is a Bayesian credible interval · specific to this suite and model.")
    return "\n".join(lines)


# Local Ollama defaults (runs on a machine with an Ollama daemon).
OLLAMA_SUBJECT = "qwen3.5:2b"
OLLAMA_JUDGE = "qwen2.5:7b-instruct"
OLLAMA_EMBED = "nomic-embed-text"


@app.command()
def scan(
    file: Path = typer.Argument(..., help="Prompt file to scan."),
    backend: str = typer.Option("ollama", help="ollama | hf"),
    depth: str = typer.Option("deep", help="quick | deep"),
    probes: int = typer.Option(6, help="Probe-suite size (0 = all 12)."),
    n: int = typer.Option(3, help="Samples per condition (deep audit)."),
    seed: int = typer.Option(42),
    subject: str = typer.Option(OLLAMA_SUBJECT, help="Ollama subject model."),
    judge: str = typer.Option(OLLAMA_JUDGE, help="Ollama judge model."),
    embed: str = typer.Option(OLLAMA_EMBED, help="Ollama embedding model."),
    json_out: str = typer.Option(None, "--json", help="Write report JSON ('-' for stdout)."),
):
    """Segment a prompt, measure each instruction by ablation, and print the readout."""
    from proseweight.probes.suite import load_suite
    from proseweight.segmentation.pipeline import segment_prompt
    from proseweight.verdict.orchestrator import run_verdict

    source = Path(file).read_text(encoding="utf-8")
    suite_path = Path(__file__).resolve().parents[3] / "data" / "suites" / "default-v1.yaml"
    suite = load_suite(suite_path)
    if probes:
        suite.probes = suite.probes[: probes]
    segments = segment_prompt(source)
    depth_v = "deep_audit" if depth == "deep" else "quick_scan"
    cfg = RunConfig(subject_model=subject, seed=seed, depth=depth_v, posterior_samples=3000, n_runs=n)

    typer.echo(f"Segmented into {len(segments)} instructions. Measuring on {subject} via {backend}…")
    if backend == "ollama":
        from proseweight.engine.ollama_backend import OllamaMeasurementBackend

        mb = OllamaMeasurementBackend(subject, judge, embed, seed=seed, n_samples=n, temperature=0.7)
    else:
        from proseweight.engine.hf_backend import HFMeasurementBackend

        cfg.subject_model = subject
        mb = HFMeasurementBackend(cfg)
    bundle = mb.measure(source, segments, suite, cfg)
    verdict = run_verdict(source, segments, suite, cfg, bundle, run_id="cli")

    if json_out:
        payload = json.dumps(verdict.to_dict(), indent=2)
        (typer.echo(payload) if json_out == "-" else Path(json_out).write_text(payload, encoding="utf-8"))
    typer.echo("")
    typer.echo(_readout(verdict))


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


@app.command()
def serve(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8799)):
    """Start the local watch-mode HTTP API (loopback, single-tenant)."""
    import uvicorn

    typer.echo(f"Serving proseweight API on http://{host}:{port} (loopback).")
    uvicorn.run("proseweight.api.server:app", host=host, port=port, log_level="info")


@app.command()
def web(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8790)):
    """Start the interactive web app (paste a prompt, measure weights, see the verdict)."""
    import uvicorn

    typer.echo(f"Prose Weight web app on http://{host}:{port}  (paste a prompt and measure)")
    uvicorn.run("proseweight.web.app:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
