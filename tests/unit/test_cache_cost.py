"""Unit test: cost attribution + ledger (T035 / US5 / SC-002 / SC-006)."""

from __future__ import annotations

from proseweight.cache.core import api
from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.cost import attribute
from proseweight.cache.core.ledger import rollup
from proseweight.cache.core.pricing import Pricing
from proseweight.cache.core.store import CacheStore


def _divergence(avoidable: bool, source_kind: str, tokens: int = 1_000_000) -> dict:
    return {
        "id": "div_x", "avoidable": avoidable, "model_id": "claude-opus-5",
        "source_kind": source_kind, "timestamp": "2026-09-14T10:00:00Z",
        "predicted_recomputed_tokens": tokens, "cache_creation_input_tokens": 0,
        "cause": "crlf_drift",
    }


def test_formula_and_stamps():
    p = Pricing.load()
    attrs = attribute([_divergence(True, "api_proxy")], p)
    assert len(attrs) == 1
    a = attrs[0]
    # 1M tokens, opus-5: (1.25-0.1) x 5 x 0.79 = 4.5425
    assert abs(a["wasted_gbp"] - 4.5425) < 1e-6
    assert a["pricing_version"] and a["effective_date"] and a["fx_date"]  # SC-002


def test_non_avoidable_excluded():
    assert attribute([_divergence(False, "api_proxy")], Pricing.load()) == []


def test_payg_is_measured_subscription_is_shadow_price():
    p = Pricing.load()
    payg = attribute([_divergence(True, "api_proxy")], p)[0]
    sub = attribute([_divergence(True, "claude_code_transcript")], p)[0]
    assert payg["billing_model"] == "payg" and payg["is_shadow_price"] is False and payg["quota_tokens"] is None
    assert sub["billing_model"] == "subscription" and sub["is_shadow_price"] is True
    assert sub["quota_tokens"] == 1_000_000  # SC-006: quota is the primary meter


def test_ledger_headline_and_rollup():
    p = Pricing.load()
    attrs = attribute(
        [_divergence(True, "api_proxy", 1_000_000), _divergence(True, "api_proxy", 10)], p
    )
    rows = rollup(attrs, "month")
    assert rows[0]["headline"] is True
    assert rows[0]["cause"] == "crlf_drift"
    assert rows[0]["period_key"] == "2026-09"


def _rec(prefix, ts, source, grade, resp_id, prev_id=None):
    return CaptureIngestionRecord(
        source_kind=source, confidence_grade=grade, model_id="claude-opus-5",
        timestamp=ts, usage=Usage(input_tokens=5, cache_read_input_tokens=1000),
        prefix_bytes=prefix, response_message_id=resp_id, previous_message_id=prev_id,
    )


def test_end_to_end_meter_fork(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    tail = b"A" * 6000
    # PAYG lineage linked by message id, early CRLF divergence -> large recomputed suffix
    store.add_turn(_rec(b"X\r\n" + tail, "2026-09-14T10:00:00Z", SourceKind.API_PROXY, ConfidenceGrade.EXACT, "p1"))
    store.add_turn(_rec(b"X\n" + tail, "2026-09-14T10:01:00Z", SourceKind.API_PROXY, ConfidenceGrade.EXACT, "p2", "p1"))
    # Subscription lineage (transcript), same shape
    store.add_turn(_rec(b"Y\r\n" + tail, "2026-09-14T10:02:00Z", SourceKind.CLAUDE_CODE_TRANSCRIPT, ConfidenceGrade.RECONSTRUCTED_LOW, "s1"))
    store.add_turn(_rec(b"Y\n" + tail, "2026-09-14T10:03:00Z", SourceKind.CLAUDE_CODE_TRANSCRIPT, ConfidenceGrade.RECONSTRUCTED_LOW, "s2", "s1"))

    result = api.analyse(store)
    result.validate()
    assert len(result.attributions) == 2
    by_meter = {a["billing_model"]: a for a in result.attributions}
    assert by_meter["payg"]["is_shadow_price"] is False and by_meter["payg"]["wasted_gbp"] > 0
    assert by_meter["subscription"]["is_shadow_price"] is True and by_meter["subscription"]["quota_tokens"] > 0
    assert any(r["headline"] for r in result.rollups)
    store.close()
