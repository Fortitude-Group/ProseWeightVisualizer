"""`proseweight cache <sub>` command group (contracts/cli.md).

Registered additively onto the existing `proseweight` app (T004); no change to the
`001` commands. Release 1 ships `cache lint` (the zero-data instant-proof surface,
US2). `serve` / `ingest` / `analyse` / `ledger` / `export` land in later increments.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

cache_app = typer.Typer(add_completion=False, help="CacheScope — empirical prompt-cache profiler.")


@cache_app.command("lint")
def lint_cmd(
    files: list[str] = typer.Argument(..., help="Files to lint (CLAUDE.md, ~/.claude/CLAUDE.md, .kb/*.md)."),
    json_out: str = typer.Option(None, "--json", help="Write CacheScopeResult JSON ('-' for stdout)."),
    model: str = typer.Option(None, "--model", help="Model id for the cost estimate (default: table fallback)."),
    pricing_path: str = typer.Option(None, "--pricing", help="Path to an editable pricing.json."),
) -> None:
    """Static cache-hygiene lint — no captured data, no API, no model runtime (US2)."""
    from proseweight.cache.core.api import lint as run_lint
    from proseweight.cache.core.pricing import Pricing

    pricing = Pricing.load(pricing_path)
    result = run_lint(list(files), pricing=pricing, model_id=model)

    if json_out:
        payload = json.dumps(result.to_dict(), indent=2)
        if json_out == "-":
            typer.echo(payload)
        else:
            Path(json_out).write_text(payload, encoding="utf-8")
            typer.echo(f"Wrote {json_out}")

    stamp = result.pricing
    typer.echo(
        f"CacheScope · Static lint   pricing {stamp.pricing_version} "
        f"(eff {stamp.effective_date}, fx {stamp.fx_date})   [predictions — confirmed later by measurement]"
    )
    if not result.lint_findings:
        typer.echo("No cache-hostile patterns predicted.")
        return
    typer.echo("  RULE                FILE:LINE            EST £/MONTH*  ")
    for f in result.lint_findings:
        loc = f"{Path(f.file).name}:{f.line}"
        typer.echo(f"  {f.rule_id:<18}  {loc:<20} {f.estimated_monthly_gbp:>10.2f}")
    typer.echo("  * predicted monthly cost (assumptions in the pricing table); not yet a measured fact.")


@cache_app.command("serve")
def serve_cmd(
    db: str = typer.Option("cache.db", "--db", help="Capture store path."),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (loopback by default)."),
    port: int = typer.Option(8790, "--port", help="Port for the recording proxy."),
    upstream: str = typer.Option("https://api.anthropic.com", "--upstream", help="Real API base URL."),
    diagnostics: bool = typer.Option(False, "--diagnostics", help="Opt in to the cache-diagnostics beta (PAYG only)."),
) -> None:
    """Run the local base-URL recording reverse proxy (US1). Point your SDK at it via ANTHROPIC_BASE_URL."""
    from proseweight.cache.proxy.server import run

    typer.echo(
        f"CacheScope proxy on http://{host}:{port}  ->  {upstream}   (store {db}"
        f"{', diagnostics on' if diagnostics else ''})\n"
        f"Set ANTHROPIC_BASE_URL=http://{host}:{port} in the app you want to profile."
    )
    run(store_db_path=db, host=host, port=port, upstream=upstream, diagnostics=diagnostics)


@cache_app.command("ingest")
def ingest_cmd(
    paths: list[str] = typer.Argument(..., help="Claude Code .jsonl transcript files or a directory of them."),
    db: str = typer.Option("cache.db", "--db", help="Capture store path."),
) -> None:
    """Ingest Claude Code session transcripts (US1, subscription path) into the capture store."""
    from proseweight.cache.core.store import CacheStore
    from proseweight.cache.ingest.claude_code import ingest_transcript

    targets: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            targets.extend(sorted(p.glob("*.jsonl")))
        elif p.exists():
            targets.append(p)
    if not targets:
        typer.echo("No .jsonl transcripts found at the given paths.")
        raise typer.Exit(1)

    store = CacheStore(db)
    total = 0
    try:
        for t in targets:
            ids = ingest_transcript(t, store)
            total += len(ids)
            typer.echo(f"  {t.name}: {len(ids)} turns")
    finally:
        store.close()
    typer.echo(f"Ingested {total} turns from {len(targets)} transcript(s) into {db} (source: claude_code_transcript).")


@cache_app.command("analyse")
def analyse_cmd(
    db: str = typer.Option("cache.db", "--db", help="Capture store path."),
    json_out: str = typer.Option(None, "--json", help="Write CacheScopeResult JSON ('-' for stdout)."),
    pricing_path: str = typer.Option(None, "--pricing", help="Path to an editable pricing.json."),
) -> None:
    """Analyse captures: lineage → divergence → breakpoint survival (US3)."""
    import json as _json

    from proseweight.cache.core.api import analyse as run_analyse
    from proseweight.cache.core.pricing import Pricing
    from proseweight.cache.core.store import CacheStore

    store = CacheStore(db)
    try:
        result = run_analyse(store, pricing=Pricing.load(pricing_path))
    finally:
        store.close()

    if json_out:
        payload = _json.dumps(result.to_dict(), indent=2)
        if json_out == "-":
            typer.echo(payload)
        else:
            Path(json_out).write_text(payload, encoding="utf-8")
            typer.echo(f"Wrote {json_out}")

    avoidable = [d for d in result.divergences if d["avoidable"]]
    typer.echo(
        f"CacheScope · Analyse   {len(result.lineages)} lineage(s), "
        f"{len(result.divergences)} divergence(s) ({len(avoidable)} avoidable)."
    )
    for d in result.divergences:
        mark = "avoidable" if d["avoidable"] else "intended "
        typer.echo(f"  {mark}  {d['cause']:<20} @byte {d['first_divergent_offset']} (line {d['line']})")


@cache_app.command("ledger")
def ledger_cmd(
    db: str = typer.Option("cache.db", "--db", help="Capture store path."),
    period: str = typer.Option("month", "--period", help="day | week | month."),
    json_out: str = typer.Option(None, "--json", help="Write rollups JSON ('-' for stdout)."),
    pricing_path: str = typer.Option(None, "--pricing", help="Path to an editable pricing.json."),
) -> None:
    """Aggregated cache waste by cause and period, with the meter forked by billing model (US5)."""
    import json as _json

    from proseweight.cache.core.api import ledger as run_ledger
    from proseweight.cache.core.pricing import Pricing
    from proseweight.cache.core.store import CacheStore

    pricing = Pricing.load(pricing_path)
    store = CacheStore(db)
    try:
        rollups = run_ledger(store, period=period, pricing=pricing)
    finally:
        store.close()

    if json_out:
        payload = _json.dumps(rollups, indent=2)
        if json_out == "-":
            typer.echo(payload)
        else:
            Path(json_out).write_text(payload, encoding="utf-8")
            typer.echo(f"Wrote {json_out}")

    stamp = pricing.stamp()
    typer.echo(
        f"CacheScope · Ledger   store {db}   pricing {stamp.pricing_version} "
        f"(eff {stamp.effective_date}, fx {stamp.fx_date})"
    )
    if not rollups:
        typer.echo("No avoidable cache waste attributed yet.")
        return
    headline = next((r for r in rollups if r["headline"]), rollups[0])
    meter = "shadow-price" if headline["billing_model"] == "subscription" else "measured"
    typer.echo(
        f"Headline: {headline['cause']} cost £{headline['wasted_gbp']:.2f} "
        f"per {period} ({meter}" + (f", {headline['wasted_quota_tokens']} quota tokens" if headline["wasted_quota_tokens"] else "") + ")."
    )
    typer.echo("  CAUSE               MODEL                PERIOD      £*        METER")
    for r in rollups:
        m = "shadow-price" if r["billing_model"] == "subscription" else "measured"
        typer.echo(
            f"  {(r['cause'] or '?'):<18}  {(r['model_id'] or 'all'):<18}  {r['period_key']:<10}  "
            f"{r['wasted_gbp']:>7.2f}   {m}"
        )
    typer.echo(
        "  * measured £ on PAYG; a subscription figure is a shadow-price counterfactual, not a bill. "
        "Excludes non-avoidable edits and never-cached prefixes."
    )


@cache_app.command("export")
def export_cmd(
    result_json: str = typer.Argument(None, help="A CacheScopeResult JSON file. Omit to analyse --db live."),
    html_out: str = typer.Option(..., "--html", help="Output self-contained HTML path."),
    png_out: str = typer.Option(None, "--png", help="Optional PNG summary card path."),
    db: str = typer.Option(None, "--db", help="Capture store, for byte-diff context (and live analyse)."),
    theme: str = typer.Option("neutral", "--theme", help="neutral | fortitude | dark."),
    pricing_path: str = typer.Option(None, "--pricing", help="Path to an editable pricing.json."),
) -> None:
    """Render the three views to a self-contained HTML (+ optional PNG) — no server (US6)."""
    import json as _json

    from proseweight.cache.core.store import CacheStore
    from proseweight.cache.report.export_html import export_html
    from proseweight.cache.report.png_card import render_png

    store = CacheStore(db) if db else None
    try:
        if result_json:
            result = _json.loads(Path(result_json).read_text(encoding="utf-8"))
        elif store is not None:
            from proseweight.cache.core.api import analyse
            from proseweight.cache.core.pricing import Pricing

            result = analyse(store, pricing=Pricing.load(pricing_path)).to_dict()
        else:
            typer.echo("Provide a result JSON argument or --db to analyse live.")
            raise typer.Exit(2)

        Path(html_out).write_text(export_html(result, store=store, theme=theme), encoding="utf-8")
        typer.echo(f"Wrote {html_out}")
        if png_out:
            render_png(result, png_out, theme=theme)
            typer.echo(f"Wrote {png_out}")
    finally:
        if store is not None:
            store.close()


@cache_app.command("prune")
def prune_cmd(
    db: str = typer.Option("cache.db", "--db", help="Capture store path."),
    retention_days: int = typer.Option(..., "--retention-days", help="Prune raw prefix bytes older than N days (rows kept)."),
) -> None:
    """Retention (FR-003): drop raw prefix blobs older than N days; keep rows + metadata for the ledger."""
    from proseweight.cache.core.store import CacheStore

    store = CacheStore(db)
    try:
        pruned = store.prune(retention_days=retention_days)
    finally:
        store.close()
    typer.echo(f"Pruned {pruned} prefix blob(s) older than {retention_days} days; ledger rows retained.")
