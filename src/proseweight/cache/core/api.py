"""``cache.core.api`` — the single SemVer'd public surface (FR-027 / R11).

OmnisVigil and every CacheScope adapter import *this*, never core internals. The
façade returns only contract objects. Release 1 implements ``ingest`` and ``lint``;
``analyse`` and ``ledger`` are Release 2 and raise a clear NotImplementedError until
their detectors land (US3–US5), so a caller never gets a silent empty result.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from proseweight.cache.core.contracts import CacheScopeResult, CaptureIngestionRecord
from proseweight.cache.core.lint import lint_files
from proseweight.cache.core.pricing import Pricing
from proseweight.cache.core.store import CacheStore


def ingest(record: CaptureIngestionRecord, store: CacheStore) -> str:
    """Append a validated capture to the store; returns the turn id (US1)."""
    return store.add_turn(record)


def lint(
    target_files: list[str | Path],
    pricing: Pricing | None = None,
    model_id: str | None = None,
) -> CacheScopeResult:
    """Static cache-hygiene lint — no captured data required (US2)."""
    pricing = pricing or Pricing.load()
    findings = lint_files(target_files, pricing=pricing, model_id=model_id)
    return CacheScopeResult(
        pricing=pricing.stamp(),
        generated_at=datetime.now(UTC).isoformat(),
        lint_findings=findings,
    ).validate()


def analyse(store: CacheStore, pricing: Pricing | None = None) -> CacheScopeResult:  # noqa: ARG001
    """Lineage → divergence → breakpoint → reconciliation → cost (Release 2, US3–US5)."""
    raise NotImplementedError(
        "analyse() lands in Release 2 (US3–US5); Release 1 provides ingest() and lint()."
    )


def ledger(store: CacheStore, period: str = "month", pricing: Pricing | None = None) -> list[dict]:  # noqa: ARG001
    """Aggregated waste by period × cause × model (Release 2, US5)."""
    raise NotImplementedError("ledger() lands in Release 2 (US5).")
