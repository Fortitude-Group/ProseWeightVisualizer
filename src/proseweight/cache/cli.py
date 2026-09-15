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
