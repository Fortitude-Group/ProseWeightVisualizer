"""Editable per-model pricing table (FR-016) + GBP conversion + stamping.

Seeded with published defaults verified 2026-09-14 (research R1). The multipliers
and minimums are **per model** (the read multiplier is not a global constant — the
Fable class reads at ~0.025x), and the minimum cacheable prefix is **non-monotonic**
across generations, so both live in the table, not in code.

The core carries an embedded default so it is self-contained (transplant-friendly);
``data/cache/pricing.default.json`` is the user-facing editable copy. Every figure
computed here is stamped with pricing version + effective date + FX date (SC-002).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proseweight.cache.core.contracts import PricingStamp

# Verified 2026-09-14 (claude-api shared/prompt-caching.md). write_mult_1h≈2.0 is the
# published rate — confirm against the live pricing row before a production figure.
DEFAULT_TABLE: dict[str, Any] = {
    "pricing_version": "2026-09",
    "effective_date": "2026-09-01",
    "fx_date": "2026-09-01",
    "usd_gbp": 0.79,
    "_note": "prices change — edit me (per-model rates, minimums, FX and dates)",
    "assumptions": {"monthly_requests": 1000, "bytes_per_token": 4},
    "models": {
        # base input $/MTok, 5m/1h write multipliers, read multiplier, min cacheable tokens
        "claude-opus-5": {"base_input_rate_usd_per_mtok": 5.0, "write_mult_5m": 1.25, "write_mult_1h": 2.0, "read_mult": 0.1, "min_cacheable_tokens": 512},
        "claude-fable-5-1": {"base_input_rate_usd_per_mtok": 10.0, "write_mult_5m": 1.25, "write_mult_1h": 2.0, "read_mult": 0.025, "min_cacheable_tokens": 512},
        "claude-fable-5": {"base_input_rate_usd_per_mtok": 10.0, "write_mult_5m": 1.25, "write_mult_1h": 2.0, "read_mult": 0.025, "min_cacheable_tokens": 512},
        "claude-opus-4-8": {"base_input_rate_usd_per_mtok": 5.0, "write_mult_5m": 1.25, "write_mult_1h": 2.0, "read_mult": 0.1, "min_cacheable_tokens": 1024},
        "claude-sonnet-5": {"base_input_rate_usd_per_mtok": 2.0, "write_mult_5m": 1.25, "write_mult_1h": 2.0, "read_mult": 0.1, "min_cacheable_tokens": 1024},
        "claude-sonnet-4-6": {"base_input_rate_usd_per_mtok": 3.0, "write_mult_5m": 1.25, "write_mult_1h": 2.0, "read_mult": 0.1, "min_cacheable_tokens": 1024},
        "claude-opus-4-7": {"base_input_rate_usd_per_mtok": 5.0, "write_mult_5m": 1.25, "write_mult_1h": 2.0, "read_mult": 0.1, "min_cacheable_tokens": 2048},
        "claude-opus-4-6": {"base_input_rate_usd_per_mtok": 5.0, "write_mult_5m": 1.25, "write_mult_1h": 2.0, "read_mult": 0.1, "min_cacheable_tokens": 4096},
        "claude-haiku-4-5": {"base_input_rate_usd_per_mtok": 1.0, "write_mult_5m": 1.25, "write_mult_1h": 2.0, "read_mult": 0.1, "min_cacheable_tokens": 4096},
    },
    # used when a captured model_id is not in the table
    "fallback_model": "claude-opus-5",
}


@dataclass(frozen=True)
class ModelPricing:
    model_id: str
    base_input_rate_usd_per_mtok: float
    write_mult_5m: float
    write_mult_1h: float
    read_mult: float
    min_cacheable_tokens: int

    def waste_gbp(self, recomputed_tokens: int, usd_gbp: float, *, ttl_1h: bool = False) -> float:
        """FR-017: recomputed_tokens x base_rate x (write_mult - read_mult), in GBP."""
        write_mult = self.write_mult_1h if ttl_1h else self.write_mult_5m
        usd = (recomputed_tokens / 1_000_000) * self.base_input_rate_usd_per_mtok * (write_mult - self.read_mult)
        return round(usd * usd_gbp, 4)


class Pricing:
    """Loaded pricing table. Use ``Pricing.load()`` (file or embedded default)."""

    def __init__(self, table: dict[str, Any]) -> None:
        self._t = table

    @classmethod
    def load(cls, path: str | Path | None = None) -> Pricing:
        if path is not None and Path(path).exists():
            return cls(json.loads(Path(path).read_text(encoding="utf-8")))
        return cls(json.loads(json.dumps(DEFAULT_TABLE)))  # deep copy of the embedded default

    @property
    def usd_gbp(self) -> float:
        return float(self._t["usd_gbp"])

    @property
    def monthly_requests(self) -> int:
        return int(self._t.get("assumptions", {}).get("monthly_requests", 1000))

    @property
    def bytes_per_token(self) -> int:
        return int(self._t.get("assumptions", {}).get("bytes_per_token", 4))

    def stamp(self) -> PricingStamp:
        return PricingStamp(
            pricing_version=self._t["pricing_version"],
            effective_date=self._t["effective_date"],
            fx_date=self._t["fx_date"],
            usd_gbp=self.usd_gbp,
        )

    def for_model(self, model_id: str) -> ModelPricing:
        models = self._t["models"]
        row = models.get(model_id) or models[self._t.get("fallback_model", "claude-opus-5")]
        return ModelPricing(
            model_id=model_id,
            base_input_rate_usd_per_mtok=float(row["base_input_rate_usd_per_mtok"]),
            write_mult_5m=float(row["write_mult_5m"]),
            write_mult_1h=float(row["write_mult_1h"]),
            read_mult=float(row["read_mult"]),
            min_cacheable_tokens=int(row["min_cacheable_tokens"]),
        )

    def estimate_monthly_gbp(self, affected_bytes: int, model_id: str | None = None) -> float:
        """Prediction (FR-007): a cache-hostile line recomputes the bytes after it on
        every request. monthly = monthly_requests x recomputed_tokens x rate_delta, GBP.
        Transparent and configurable via the table's ``assumptions`` (Principle XII).
        """
        mp = self.for_model(model_id or self._t.get("fallback_model", "claude-opus-5"))
        recomputed_tokens = max(1, affected_bytes // self.bytes_per_token)
        per_request = mp.waste_gbp(recomputed_tokens, self.usd_gbp)
        return round(per_request * self.monthly_requests, 4)
