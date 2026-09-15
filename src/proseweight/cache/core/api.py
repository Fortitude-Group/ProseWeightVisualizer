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


def analyse(store: CacheStore, pricing: Pricing | None = None) -> CacheScopeResult:
    """Lineage → divergence → breakpoint state, over the captured store (US3).

    Reconciliation (US4) and cost attribution/ledger (US5) build on this; this
    release populates lineages, divergences and breakpoint survival states.
    """
    from proseweight.cache.core import breakpoints as bp_mod
    from proseweight.cache.core import divergence as div_mod
    from proseweight.cache.core import lineage as lin_mod
    from proseweight.cache.core import reconcile as recon_mod
    from proseweight.cache.core.contracts import BreakpointState

    pricing = pricing or Pricing.load()
    bpt = pricing.bytes_per_token
    lineage_map = lin_mod.lineages(store)

    lineages_out: list[dict] = []
    divergences_out: list[dict] = []
    breakpoints_out: list[dict] = []

    for lineage_id, turns in lineage_map.items():
        lineages_out.append({
            "id": lineage_id,
            "source_kind": turns[0].source_kind if turns else None,
            "model_id": turns[0].model_id if turns else None,
            "turns": [t.id for t in turns],
        })
        for i, turn in enumerate(turns):
            model_min = pricing.for_model(turn.model_id).min_cacheable_tokens
            bps = bp_mod.resolve(turn.prefix_bytes, model_min_tokens=model_min, bytes_per_token=bpt)

            if i == 0:
                # lineage head: freshly cached, no predecessor to diff (FR-008)
                bp_mod.assign_states(bps, divergence_offset=None, model_min_tokens=model_min)
                for b in bps:
                    if b.state is BreakpointState.HIT:
                        b.state = BreakpointState.NEW
                    breakpoints_out.append(b.to_dict(turn.id))
                continue

            prev = turns[i - 1]
            offset = div_mod.first_divergence(prev.prefix_bytes, turn.prefix_bytes)
            bp_mod.assign_states(bps, divergence_offset=(None if offset < 0 else offset), model_min_tokens=model_min)
            for b in bps:
                breakpoints_out.append(b.to_dict(turn.id))

            if offset < 0:
                continue  # identical prefix, a clean cache hit — no divergence record

            cause, avoidable = div_mod.classify(
                prev.prefix_bytes, turn.prefix_bytes, offset, prev.model_id, turn.model_id
            )
            # Waste is the cached tokens actually thrown away: the recomputed blocks.
            # A never-cached (below-minimum) block recomputes nothing, so it contributes
            # zero — SC-010 holds by construction, no waste on a never-cached prefix.
            recomputed_bps = [b for b in bps if b.state is BreakpointState.RECOMPUTED]
            recomputed = max((b.capped_tokens for b in recomputed_bps), default=0)
            invalidated = [b.index for b in recomputed_bps]
            reconciliation = recon_mod.reconcile(
                predicted_recomputed_tokens=recomputed,
                cur_cache_creation=turn.cache_creation_input_tokens,
                cur_cache_read=turn.cache_read_input_tokens,
                prev_cache_read=prev.cache_read_input_tokens,
                diagnostics=turn.diagnostics,
            )
            divergences_out.append({
                "id": f"div_{turn.id}",
                "lineage_id": lineage_id,
                "prev_turn_id": prev.id,
                "turn_id": turn.id,
                "first_divergent_offset": offset,
                "line": div_mod.line_of(turn.prefix_bytes, offset),
                "cause": cause.value,
                "avoidable": avoidable,
                "predicted_recomputed_tokens": recomputed,
                "invalidated_breakpoints": invalidated,
                "reconciliation": reconciliation,
                # ride-along fields for cost attribution + ledger (US5)
                "model_id": turn.model_id,
                "source_kind": turn.source_kind,
                "timestamp": turn.timestamp,
                "cache_creation_input_tokens": turn.cache_creation_input_tokens,
            })

    from proseweight.cache.core import cost as cost_mod
    from proseweight.cache.core import ledger as ledger_mod

    attributions = cost_mod.attribute(divergences_out, pricing)
    rollups = ledger_mod.rollup(attributions, "month")
    validity = recon_mod.validity_summary(divergences_out)

    return CacheScopeResult(
        pricing=pricing.stamp(),
        generated_at=datetime.now(UTC).isoformat(),
        lineages=lineages_out,
        divergences=divergences_out,
        breakpoints=breakpoints_out,
        attributions=attributions,
        rollups=rollups,
        validity=validity,
    ).validate()


def ledger(store: CacheStore, period: str = "month", pricing: Pricing | None = None) -> list[dict]:
    """Aggregated waste by period × cause × model, headline flagged (US5 / FR-018).

    Re-rolls the attributions from ``analyse`` at the requested period. Pound totals
    are measured for PAYG rows and shadow-price for subscription rows.
    """
    from proseweight.cache.core import ledger as ledger_mod

    result = analyse(store, pricing=pricing)
    return ledger_mod.rollup(result.attributions, period)
