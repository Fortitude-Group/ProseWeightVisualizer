"""Unit test: lineage pairing + end-to-end analyse() (T028 / US3)."""

from __future__ import annotations

from proseweight.cache.core import api
from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.store import CacheStore


def _rec(prefix: bytes, ts: str, *, resp_id: str, prev_id: str | None = None) -> CaptureIngestionRecord:
    return CaptureIngestionRecord(
        source_kind=SourceKind.API_PROXY,
        confidence_grade=ConfidenceGrade.EXACT,
        model_id="claude-opus-5",
        timestamp=ts,
        usage=Usage(input_tokens=5, cache_read_input_tokens=1000),
        prefix_bytes=prefix,
        response_message_id=resp_id,
        previous_message_id=prev_id,
    )


def test_analyse_finds_crlf_divergence_within_lineage(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    shared = b"A" * 5000  # first 4096 bytes match -> same lineage; above the 512-token min
    store.add_turn(_rec(shared + b"\r\nZ", "2026-09-14T10:00:00Z", resp_id="m1"))
    store.add_turn(_rec(shared + b"\nZ", "2026-09-14T10:01:00Z", resp_id="m2", prev_id="m1"))
    # a wholly different prefix -> its own lineage, head only (no divergence)
    store.add_turn(_rec(b"B" * 5000, "2026-09-14T10:02:00Z", resp_id="m3"))

    result = api.analyse(store)
    result.validate()

    assert len(result.lineages) == 2  # A-family and B-family, never merged
    assert len(result.divergences) == 1
    d = result.divergences[0]
    assert d["cause"] == "crlf_drift"
    assert d["avoidable"] is True
    assert d["first_divergent_offset"] == 5000  # exact \r-vs-\n byte
    assert d["prev_turn_id"].endswith("m1") or "m1" in d["prev_turn_id"]
    store.close()


def test_no_cross_lineage_pairing(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    # two unrelated prefixes, different leading windows -> two lineages, zero divergences
    store.add_turn(_rec(b"C" * 5000, "2026-09-14T10:00:00Z", resp_id="c1"))
    store.add_turn(_rec(b"D" * 5000, "2026-09-14T10:00:30Z", resp_id="d1"))
    result = api.analyse(store)
    assert len(result.lineages) == 2
    assert result.divergences == []  # no pair spans lineages
    store.close()


def test_head_turn_has_no_divergence_but_has_breakpoints(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    store.add_turn(_rec(b"E" * 5000, "2026-09-14T10:00:00Z", resp_id="e1"))
    result = api.analyse(store)
    assert result.divergences == []
    # head turn still yields a breakpoint in the 'new' state
    states = {b["state"] for b in result.breakpoints}
    assert "new" in states
    store.close()
