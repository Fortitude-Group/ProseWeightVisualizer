"""Contract test: CaptureIngestionRecord (T006) — the input boundary guarantees."""

from __future__ import annotations

import pytest

from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    ContractError,
    SourceKind,
    Usage,
)


def _rec(**kw) -> CaptureIngestionRecord:
    base = dict(
        source_kind=SourceKind.API_PROXY,
        confidence_grade=ConfidenceGrade.EXACT,
        model_id="claude-opus-5",
        timestamp="2026-09-14T10:00:00Z",
        usage=Usage(input_tokens=10, cache_read_input_tokens=100),
        prefix_bytes=b"hello world prefix",
    )
    base.update(kw)
    return CaptureIngestionRecord(**base)


def test_api_proxy_must_be_exact():
    with pytest.raises(ContractError):
        _rec(confidence_grade=ConfidenceGrade.RECONSTRUCTED_LOW).validate()


def test_transcript_may_not_be_exact():
    with pytest.raises(ContractError):
        _rec(
            source_kind=SourceKind.CLAUDE_CODE_TRANSCRIPT,
            confidence_grade=ConfidenceGrade.EXACT,
        ).validate()


def test_diagnostics_only_on_proxy():
    with pytest.raises(ContractError):
        _rec(
            source_kind=SourceKind.CLAUDE_CODE_TRANSCRIPT,
            confidence_grade=ConfidenceGrade.RECONSTRUCTED_LOW,
            prefix_bytes=b"x" * 20,
            diagnostics={"foo": "bar"},
        ).validate()


def test_exactly_one_prefix_source():
    with pytest.raises(ContractError):
        _rec(prefix_bytes=None, prefix_ref=None).validate()
    with pytest.raises(ContractError):
        _rec(prefix_bytes=b"x", prefix_ref={"sha256": "a", "byte_len": 1}).validate()


def test_roundtrip_preserves_fields_and_version():
    rec = _rec().validate()
    d = rec.to_dict()
    assert d["contract_version"] == "1.0.0"
    assert d["prefix_bytes_b64"]
    back = CaptureIngestionRecord.from_dict(d).validate()
    assert back.prefix_bytes == b"hello world prefix"
    assert back.prefix_hash() == rec.prefix_hash()


def test_at_most_four_breakpoints():
    from proseweight.cache.core.contracts import BreakpointLevel, BreakpointMarker

    bps = [BreakpointMarker(i, BreakpointLevel.SYSTEM, i * 10) for i in range(5)]
    with pytest.raises(ContractError):
        _rec(breakpoints=bps).validate()
