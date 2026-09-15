"""Gate (T049 / SC-002 / FR-030): every figure carries its pricing/effective/FX stamp."""

from __future__ import annotations

from proseweight.cache.core import api
from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.store import CacheStore

_STAMPS = ("pricing_version", "effective_date", "fx_date")


def test_every_attribution_and_finding_is_stamped(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    tail = b"A" * 6000
    store.add_turn(CaptureIngestionRecord(
        source_kind=SourceKind.API_PROXY, confidence_grade=ConfidenceGrade.EXACT,
        model_id="claude-opus-5", timestamp="2026-09-14T10:00:00Z",
        usage=Usage(input_tokens=5, cache_read_input_tokens=8000), prefix_bytes=b"X\r\n" + tail,
        response_message_id="p1"))
    store.add_turn(CaptureIngestionRecord(
        source_kind=SourceKind.API_PROXY, confidence_grade=ConfidenceGrade.EXACT,
        model_id="claude-opus-5", timestamp="2026-09-14T10:01:00Z",
        usage=Usage(input_tokens=5, cache_creation_input_tokens=1500), prefix_bytes=b"X\n" + tail,
        response_message_id="p2", previous_message_id="p1"))

    result = api.analyse(store)
    assert result.attributions, "expected at least one attribution to check"
    for a in result.attributions:
        for s in _STAMPS:
            assert a.get(s), f"attribution missing {s}"
    # the result's own pricing stamp
    for s in _STAMPS:
        assert getattr(result.pricing, s)
    store.close()


def test_lint_findings_are_stamped(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_bytes(b"x\r\ny   \n")
    result = api.lint([str(f)])
    assert result.lint_findings
    for finding in result.lint_findings:
        for s in _STAMPS:
            assert getattr(finding, s)
