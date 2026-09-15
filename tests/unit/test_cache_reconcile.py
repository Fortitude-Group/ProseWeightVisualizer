"""Unit test: reconciliation + validity summary (T031 / US4 / SC-003)."""

from __future__ import annotations

from proseweight.cache.core import api
from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.reconcile import reconcile, validity_summary
from proseweight.cache.core.store import CacheStore


def test_agree_when_prediction_matches_measured_write():
    r = reconcile(predicted_recomputed_tokens=1500, cur_cache_creation=1500,
                  cur_cache_read=0, prev_cache_read=8000, diagnostics=None)
    assert r["agreement"] == "agree"
    assert r["measured_read_drop"] == 8000


def test_token_mismatch_when_far_off():
    r = reconcile(predicted_recomputed_tokens=50, cur_cache_creation=5000,
                  cur_cache_read=0, prev_cache_read=8000, diagnostics=None)
    assert r["agreement"] == "token_mismatch"


def test_no_measurement_without_write_or_diagnostics():
    r = reconcile(predicted_recomputed_tokens=1500, cur_cache_creation=0,
                  cur_cache_read=8000, prev_cache_read=8000, diagnostics=None)
    assert r["agreement"] == "no_measurement"  # never treated as agreement (FR-015)


def test_diagnostics_fields_recorded_defensively():
    diag = {"cache_miss_reason": {"type": "system"}, "cache_missed_input_tokens": 1500}
    r = reconcile(predicted_recomputed_tokens=1500, cur_cache_creation=0,
                  cur_cache_read=0, prev_cache_read=None, diagnostics=diag)
    assert r["measured_cause_level"] == "system"
    assert r["measured_missed_tokens"] == 1500


def test_validity_rate_over_measured_only():
    divs = [
        {"id": "a", "reconciliation": {"agreement": "agree"}},
        {"id": "b", "reconciliation": {"agreement": "token_mismatch"}},
        {"id": "c", "reconciliation": {"agreement": "no_measurement"}},
    ]
    v = validity_summary(divs)
    assert v["diverging_turns_with_measurement"] == 2  # c excluded
    assert v["agreement_rate"] == 0.5
    assert v["disagreements"] == ["b"]


def _rec(prefix, ts, resp_id, prev_id=None, read=1000, creation=0):
    return CaptureIngestionRecord(
        source_kind=SourceKind.API_PROXY, confidence_grade=ConfidenceGrade.EXACT,
        model_id="claude-opus-5", timestamp=ts,
        usage=Usage(input_tokens=5, cache_read_input_tokens=read, cache_creation_input_tokens=creation),
        prefix_bytes=prefix, response_message_id=resp_id, previous_message_id=prev_id,
    )


def test_end_to_end_reconciliation_and_validity(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    tail = b"A" * 6000  # early CRLF -> predicted recompute ~1500 tokens
    store.add_turn(_rec(b"X\r\n" + tail, "2026-09-14T10:00:00Z", "p1", read=8000, creation=0))
    store.add_turn(_rec(b"X\n" + tail, "2026-09-14T10:01:00Z", "p2", "p1", read=0, creation=1500))
    result = api.analyse(store)
    result.validate()
    d = result.divergences[0]
    assert d["reconciliation"]["agreement"] == "agree"  # predicted 1500 ~ measured write 1500
    assert result.validity["agreement_rate"] == 1.0
    assert result.validity["diverging_turns_with_measurement"] == 1
    store.close()
