"""Gate (T048 / Principle IV): identical captures + pricing -> byte-identical result."""

from __future__ import annotations

import json

from proseweight.cache.core import api
from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.store import CacheStore


def _seed(store: CacheStore) -> None:
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


def _canonical(result) -> str:
    d = result.to_dict()
    d.pop("generated_at", None)  # the only intentionally nondeterministic field
    return json.dumps(d, sort_keys=True)


def test_analyse_is_byte_identical_across_runs(tmp_path):
    s = CacheStore(tmp_path / "cache.db")
    _seed(s)
    a = _canonical(api.analyse(s))
    b = _canonical(api.analyse(s))
    assert a == b
    s.close()
