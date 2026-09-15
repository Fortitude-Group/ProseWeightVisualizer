"""Gate (T050 / SC-010): a never-cached prefix is never attributed waste."""

from __future__ import annotations

from proseweight.cache.core import api
from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.store import CacheStore


def _rec(prefix, ts, resp_id, prev_id=None):
    return CaptureIngestionRecord(
        source_kind=SourceKind.API_PROXY, confidence_grade=ConfidenceGrade.EXACT,
        model_id="claude-opus-5", timestamp=ts,
        usage=Usage(input_tokens=5, cache_read_input_tokens=10), prefix_bytes=prefix,
        response_message_id=resp_id, previous_message_id=prev_id,
    )


def test_below_minimum_lineage_with_a_divergence_attributes_no_waste(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    # both prefixes are ~30 bytes = ~7 tokens, far below opus-5's 512-token minimum,
    # and they differ by a CRLF (an otherwise avoidable divergence)
    store.add_turn(_rec(b"tiny prompt\r\nsecond bit", "2026-09-14T10:00:00Z", "n1"))
    store.add_turn(_rec(b"tiny prompt\nsecond bit", "2026-09-14T10:01:00Z", "n2", "n1"))

    result = api.analyse(store)

    # the breakpoints are never_cached
    assert all(b["state"] == "never_cached" for b in result.breakpoints)
    # a divergence may be detected, but nothing was ever cached, so no waste is attributed
    assert result.attributions == []
    assert all(r["wasted_gbp"] == 0.0 for r in result.rollups) or result.rollups == []
    # and never_cached never shows up carrying tokens in a rollup
    assert all((r.get("wasted_quota_tokens") or 0) == 0 for r in result.rollups)
    store.close()
