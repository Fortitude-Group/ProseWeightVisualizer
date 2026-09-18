"""Unit test: high-fidelity transcript reconstruction (T042 / US7 / SC-006)."""

from __future__ import annotations

import json

from proseweight.cache.core.contracts import ConfidenceGrade, Usage
from proseweight.cache.core.store import CacheStore
from proseweight.cache.ingest.claude_code_reconstruct import (
    _content_text,
    _grade,
    reconstruct_transcript,
)


def test_content_text_handles_nested_list_blocks():
    # real transcripts nest: a tool_result block whose content is itself a list
    content = [
        {"type": "text", "text": "hello"},
        {"type": "tool_result", "content": [{"type": "text", "text": "nested"}]},
        {"type": "tool_use", "content": None},
    ]
    out = _content_text(content)
    assert "hello" in out and "nested" in out  # never raises on a list-valued block


def test_grade_calibrates_against_usage_never_exact():
    # 400 bytes ~ 100 tokens; measured total 100 -> ratio 1.0 -> high
    assert _grade(400, Usage(input_tokens=100)) is ConfidenceGrade.RECONSTRUCTED_HIGH
    # same prefix, but a big measured total (large unseen system/tools) -> low confidence
    assert _grade(400, Usage(input_tokens=1000)) is ConfidenceGrade.RECONSTRUCTED_LOW
    # never 'exact' either way
    assert _grade(400, Usage(input_tokens=100)) is not ConfidenceGrade.EXACT


def _line(role, mid=None, content="hello there", ts="2026-09-14T10:00:00Z", usage=None):
    msg = {"role": role, "content": content}
    if mid:
        msg["id"] = mid
    if usage is not None:
        msg["usage"] = usage
    return json.dumps({"type": role, "timestamp": ts, "message": msg})


def test_reconstruct_growing_prefix_and_confidence(tmp_path):
    tpath = tmp_path / "session.jsonl"
    tpath.write_text(
        "\n".join([
            _line("user", content="first user message, reasonably long to matter"),
            _line("assistant", mid="m1", content="first reply", ts="2026-09-14T10:00:00Z",
                  usage={"input_tokens": 1, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
            _line("user", content="second user message continues the thread"),
            _line("assistant", mid="m2", content="second reply", ts="2026-09-14T10:01:00Z",
                  usage={"input_tokens": 1, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}),
        ]) + "\n",
        encoding="utf-8",
    )
    store = CacheStore(tmp_path / "cache.db")
    ids = reconstruct_transcript(tpath, store)
    assert len(ids) == 2

    rows = store.conn.execute("SELECT id, prefix_hash, confidence_grade, previous_message_id FROM turns ORDER BY timestamp").fetchall()
    # never exact
    assert all(r["confidence_grade"] in ("reconstructed_high", "reconstructed_low") for r in rows)
    # growing prefix: turn 2's input history is longer than turn 1's
    len1 = len(store.get_blob(rows[0]["prefix_hash"]))
    len2 = len(store.get_blob(rows[1]["prefix_hash"]))
    assert len2 > len1
    # previous_message_id threaded m1 -> m2
    assert rows[1]["previous_message_id"] == "m1"
    store.close()
