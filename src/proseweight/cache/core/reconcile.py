"""Prediction-versus-measured reconciliation (US4 / FR-013/014/015).

Compares the predicted recomputed tokens against what the API actually reported.
The **measured** signal is the `usage` cache fields (verified): a cache write on the
current turn (``cache_creation_input_tokens``) is direct evidence of a miss and its
size. The cache-diagnostics beta payload (``cache_miss_reason.type`` /
``cache_missed_input_tokens``) is **recorded but not used to assert level agreement**
— those field names are unverified (research R8), so claiming a level match would be
asserting something unproven. Absence of any measurement is recorded as
``no_measurement`` and never treated as agreement (FR-015). Pure; core-clean.
"""

from __future__ import annotations

from typing import Any

# Token estimates here are coarse (bytes / bytes-per-token), so agreement uses a
# generous band rather than exact equality.
_REL_TOLERANCE = 0.4
_ABS_TOLERANCE = 50


def _diag_field(diagnostics: dict[str, Any] | None, *path: str) -> Any:
    node: Any = diagnostics
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def reconcile(
    *,
    predicted_recomputed_tokens: int,
    cur_cache_creation: int,
    cur_cache_read: int,
    prev_cache_read: int | None,
    diagnostics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a reconciliation dict for one divergence.

    ``agreement`` is one of agree / token_mismatch / no_measurement. (level_mismatch is
    reserved for when the diagnostics payload schema is verified — see module docstring.)
    """
    # Unverified diagnostics fields — recorded for display, not used to judge agreement.
    measured_cause_level = _diag_field(diagnostics, "cache_miss_reason", "type")
    measured_missed_tokens = _diag_field(diagnostics, "cache_missed_input_tokens")

    measured_read_drop = None
    if prev_cache_read is not None and prev_cache_read > cur_cache_read:
        measured_read_drop = prev_cache_read - cur_cache_read

    # Prefer the verified evidence: a write this turn is the token size that missed.
    measured_missed = cur_cache_creation if cur_cache_creation > 0 else measured_missed_tokens

    if measured_missed is None:
        agreement = "no_measurement"
    else:
        band = max(_ABS_TOLERANCE, int(_REL_TOLERANCE * measured_missed))
        agreement = "agree" if abs(predicted_recomputed_tokens - measured_missed) <= band else "token_mismatch"

    return {
        "measured_read_drop": measured_read_drop,
        "measured_cause_level": measured_cause_level,
        "measured_missed_tokens": measured_missed_tokens,
        "agreement": agreement,
    }


def validity_summary(divergences: list[dict]) -> dict[str, Any]:
    """Aggregate the per-turn reconciliations into the SC-003 validity block.

    Rate is computed only over diverging turns that carried a measurement (it states
    what it excludes); disagreeing divergence ids are listed, never hidden.
    """
    measured = [d for d in divergences if (d.get("reconciliation") or {}).get("agreement") not in (None, "no_measurement")]
    agrees = [d for d in measured if d["reconciliation"]["agreement"] == "agree"]
    disagreements = [d["id"] for d in measured if d["reconciliation"]["agreement"] != "agree"]
    return {
        "diverging_turns_with_measurement": len(measured),
        "level_agreements": len(agrees),
        "agreement_rate": round(len(agrees) / len(measured), 4) if measured else None,
        "disagreements": disagreements,
    }
