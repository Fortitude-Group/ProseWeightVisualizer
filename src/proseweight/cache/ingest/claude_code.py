"""Claude Code transcript ingester (T017, US1) — a consumer of ``cache.core``.

Claude Code stores one JSONL transcript per session at
``~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl``. This module streams
one such file, picks out the assistant turns, and appends each as a
``CaptureIngestionRecord`` via ``cache.core.api.ingest``.

**Reconstruction fidelity (R1 — coarse, low confidence).** The transcript does
not contain the exact on-wire rendered prefix (system prompt, tool
definitions, and full message history as actually sent to the API) — only the
assistant's own reply and its reported token usage. So ``prefix_bytes`` here
is a *stand-in*: a deterministic, stable, non-empty serialisation of the
assistant message's own ``model``, ``id``, and ``content``, encoded as UTF-8
JSON with sorted keys. It is suitable for lineage grouping and low-confidence
usage capture (hence ``confidence_grade=reconstructed_low``), but it is
explicitly **not** a byte-exact reconstruction of the request prefix.
Byte-level reconstruction is deferred to a later task (R3 / T041).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from proseweight.cache.core import api
from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.store import CacheStore


def default_transcript_dir() -> Path:
    """Where Claude Code keeps per-project session transcripts (pure, no I/O)."""
    return Path("~/.claude/projects").expanduser()


def _usage_from_message(usage_dict: dict[str, Any]) -> Usage:
    cache_creation = usage_dict.get("cache_creation") or {}
    return Usage(
        input_tokens=int(usage_dict.get("input_tokens", 0) or 0),
        cache_creation_input_tokens=int(usage_dict.get("cache_creation_input_tokens", 0) or 0),
        cache_read_input_tokens=int(usage_dict.get("cache_read_input_tokens", 0) or 0),
        ephemeral_5m_input_tokens=cache_creation.get("ephemeral_5m_input_tokens"),
        ephemeral_1h_input_tokens=cache_creation.get("ephemeral_1h_input_tokens"),
    )


def _prefix_bytes_for(message: dict[str, Any]) -> bytes:
    """Coarse R1 stand-in prefix: the assistant's own model/id/content, serialised
    deterministically. NOT byte-exact — see module docstring.
    """
    payload = {
        "model": message.get("model"),
        "id": message.get("id"),
        "content": message.get("content"),
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _record_from_line(line: dict[str, Any], previous_message_id: str | None) -> CaptureIngestionRecord | None:
    if line.get("type") != "assistant":
        return None
    message = line.get("message")
    if not isinstance(message, dict):
        return None
    usage_dict = message.get("usage")
    if not isinstance(usage_dict, dict):
        return None
    return CaptureIngestionRecord(
        source_kind=SourceKind.CLAUDE_CODE_TRANSCRIPT,
        confidence_grade=ConfidenceGrade.RECONSTRUCTED_LOW,
        model_id=message.get("model", ""),
        timestamp=line.get("timestamp", ""),
        usage=_usage_from_message(usage_dict),
        prefix_bytes=_prefix_bytes_for(message),
        response_message_id=message.get("id"),
        previous_message_id=previous_message_id,
    )


def ingest_transcript(path: str | Path, store: CacheStore) -> list[str]:
    """Parse a Claude Code ``.jsonl`` transcript and ingest each assistant turn.

    Streams the file line by line, threading ``previous_message_id`` from the
    prior assistant turn seen in the same file. Non-assistant lines, and
    assistant lines without a ``message.usage``, are skipped. Malformed lines
    are tolerated defensively (never raise on an unexpected shape).

    Returns the list of turn ids, in file order.
    """
    turn_ids: list[str] = []
    previous_message_id: str | None = None
    with Path(path).open(encoding="utf-8") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                line = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(line, dict):
                continue
            record = _record_from_line(line, previous_message_id)
            if record is None:
                continue
            turn_id = api.ingest(record, store)
            turn_ids.append(turn_id)
            previous_message_id = record.response_message_id
    return turn_ids
