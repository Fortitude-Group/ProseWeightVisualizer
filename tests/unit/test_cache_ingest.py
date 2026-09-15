"""Unit test: Claude Code transcript ingester (T017, US1).

Fully offline/deterministic — writes a synthetic ``.jsonl`` fixture in the
verified Claude Code transcript shape into ``tmp_path``; never reads a real
``~/.claude`` transcript.
"""

from __future__ import annotations

import json
from pathlib import Path

from proseweight.cache.core.store import CacheStore
from proseweight.cache.ingest.claude_code import ingest_transcript


def _assistant_line(
    msg_id: str,
    timestamp: str,
    *,
    input_tokens: int = 10,
    cache_read: int = 0,
    ephemeral_5m: int | None = None,
    ephemeral_1h: int | None = None,
) -> dict:
    usage: dict = {
        "input_tokens": input_tokens,
        "cache_creation_input_tokens": (ephemeral_5m or 0) + (ephemeral_1h or 0),
        "cache_read_input_tokens": cache_read,
    }
    cache_creation = {}
    if ephemeral_5m is not None:
        cache_creation["ephemeral_5m_input_tokens"] = ephemeral_5m
    if ephemeral_1h is not None:
        cache_creation["ephemeral_1h_input_tokens"] = ephemeral_1h
    if cache_creation:
        usage["cache_creation"] = cache_creation
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "model": "claude-opus-5",
            "id": msg_id,
            "role": "assistant",
            "content": [{"type": "text", "text": f"reply for {msg_id}"}],
            "usage": usage,
        },
    }


def _user_line(timestamp: str) -> dict:
    return {
        "type": "user",
        "timestamp": timestamp,
        "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]},
    }


def _write_transcript(tmp_path: Path) -> Path:
    lines = [
        _assistant_line(
            "msg_1",
            "2026-09-15T10:00:00Z",
            input_tokens=12,
            cache_read=0,
            ephemeral_5m=100,
        ),
        _user_line("2026-09-15T10:00:30Z"),
        _assistant_line(
            "msg_2",
            "2026-09-15T10:01:00Z",
            input_tokens=8,
            cache_read=100,
            ephemeral_1h=50,
        ),
    ]
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return p


def test_ingest_transcript_parses_assistant_turns_and_skips_others(tmp_path):
    transcript_path = _write_transcript(tmp_path)
    store = CacheStore(tmp_path / "cache.db")

    turn_ids = ingest_transcript(transcript_path, store)

    assert len(turn_ids) == 2
    assert store.turn_count() == 2

    rows = store.conn.execute(
        "SELECT * FROM turns ORDER BY timestamp"
    ).fetchall()
    assert len(rows) == 2

    first, second = rows
    assert first["source_kind"] == "claude_code_transcript"
    assert first["confidence_grade"] == "reconstructed_low"
    assert second["source_kind"] == "claude_code_transcript"
    assert second["confidence_grade"] == "reconstructed_low"

    # ephemeral TTL split captured
    assert first["ephemeral_5m_input_tokens"] == 100
    assert first["ephemeral_1h_input_tokens"] is None
    assert second["ephemeral_1h_input_tokens"] == 50
    assert second["ephemeral_5m_input_tokens"] is None

    # previous_message_id threaded across turns
    assert first["response_message_id"] == "msg_1"
    assert first["previous_message_id"] is None
    assert second["response_message_id"] == "msg_2"
    assert second["previous_message_id"] == "msg_1"

    store.close()
