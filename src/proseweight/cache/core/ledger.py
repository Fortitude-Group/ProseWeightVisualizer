"""Ledger rollups — aggregate waste by period × cause × model (US5 / FR-018).

Sums attributed waste into day/week/month buckets by cause class and model, and
marks the single largest bucket as the headline figure. The pound totals are
measured for PAYG rows and shadow-price for subscription rows (the ``billing_model``
on each row says which). Non-avoidable divergences never reach here (they were
dropped in ``cost.attribute``), so a rollup already excludes intended change.
Core-clean.
"""

from __future__ import annotations

from datetime import datetime


def _period_key(timestamp: str, period: str) -> str:
    if not timestamp:
        return "unknown"
    if period == "month":
        return timestamp[:7]  # YYYY-MM
    if period == "day":
        return timestamp[:10]  # YYYY-MM-DD
    if period == "week":
        try:
            d = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()
            iso = d.isocalendar()
            return f"{iso.year}-W{iso.week:02d}"
        except ValueError:
            return "unknown"
    return timestamp[:7]


def rollup(attributions: list[dict], period: str = "month") -> list[dict]:
    """Aggregate attributions into rollup rows, largest first, headline flagged."""
    groups: dict[tuple, dict] = {}
    for a in attributions:
        key = (
            _period_key(a.get("timestamp", ""), period),
            a.get("cause"),
            a.get("model_id"),
            a.get("billing_model"),
        )
        g = groups.setdefault(key, {"wasted_gbp": 0.0, "wasted_quota_tokens": 0})
        g["wasted_gbp"] += a.get("wasted_gbp", 0.0)
        if a.get("billing_model") == "subscription":
            g["wasted_quota_tokens"] += a.get("quota_tokens") or 0

    rollups = [
        {
            "period": period,
            "period_key": k[0],
            "cause": k[1],
            "model_id": k[2],
            "billing_model": k[3],
            "wasted_gbp": round(v["wasted_gbp"], 4),
            "wasted_quota_tokens": v["wasted_quota_tokens"] or None,
            "headline": False,
        }
        for k, v in groups.items()
    ]
    rollups.sort(key=lambda r: (-r["wasted_gbp"], r["cause"] or "", r["period_key"]))
    if rollups:
        rollups[0]["headline"] = True
    return rollups
