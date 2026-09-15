"""Cost attribution + the billing-model meter fork (US5 / FR-017/019/020).

Prices each **avoidable** divergence (non-avoidable ones, e.g. a genuine edit or a
model swap, are excluded, FR-012). The meter forks by the capture's source: PAYG
API traffic (the proxy path) carries a **measured** pound cost; subscription
traffic (Claude Code transcripts) carries quota consumption as the primary meter,
with a pound value surviving only as an explicitly-labelled **shadow-price**
counterfactual, never a bill (SC-006). Every figure is stamped (SC-002). Core-clean.
"""

from __future__ import annotations

from proseweight.cache.core.contracts import BillingModel, SourceKind
from proseweight.cache.core.pricing import Pricing


def attribute(divergences: list[dict], pricing: Pricing) -> list[dict]:
    """Return one attribution per avoidable divergence, forked by billing model.

    Each divergence dict is expected to carry ``id``, ``avoidable``, ``model_id``,
    ``source_kind``, ``timestamp``, ``predicted_recomputed_tokens`` and
    ``cache_creation_input_tokens`` (populated by ``analyse``). The extra ``cause`` /
    ``model_id`` / ``timestamp`` fields ride along for the ledger rollup.
    """
    stamp = pricing.stamp()
    out: list[dict] = []
    for d in divergences:
        if not d.get("avoidable"):
            continue
        wasted_tokens = int(d.get("predicted_recomputed_tokens", 0))
        if wasted_tokens <= 0:
            continue  # nothing was cached to lose (e.g. a never-cached prefix, SC-010)
        model_id = d.get("model_id", "")
        mp = pricing.for_model(model_id)
        wasted_gbp = mp.waste_gbp(wasted_tokens, pricing.usd_gbp)
        is_payg = d.get("source_kind") == SourceKind.API_PROXY.value
        billing = BillingModel.PAYG if is_payg else BillingModel.SUBSCRIPTION
        out.append({
            "divergence_id": d["id"],
            "billing_model": billing.value,
            "wasted_tokens": wasted_tokens,
            "wasted_gbp": wasted_gbp,
            "quota_tokens": None if is_payg else wasted_tokens,
            "is_shadow_price": not is_payg,
            # a write that later reads reuse partially offsets this single-event figure (edge case)
            "amortisation_caveat": int(d.get("cache_creation_input_tokens", 0)) > 0,
            "pricing_version": stamp.pricing_version,
            "effective_date": stamp.effective_date,
            "fx_date": stamp.fx_date,
            # ride-along for rollup (not part of the minimal contract shape):
            "cause": d.get("cause"),
            "model_id": model_id,
            "timestamp": d.get("timestamp", ""),
        })
    return out
