"""High-fidelity Claude Code transcript reconstruction (US7 / FR-024).

Builds on the basic ingester. The transcript records the conversation (user and
assistant turns) but NOT the injected system prompt, tool definitions, or
CLAUDE.md/memory as actually sent, so a byte-exact prefix is impossible from a
transcript alone. What we can do faithfully is reconstruct the **growing message
prefix**: for each assistant turn, the ordered history that was its input. That
gives consecutive turns a real shared, growing prefix (so divergence analysis is
meaningful), and we calibrate its size against the turn's measured `usage`.

Confidence is graded from that calibration and never claimed as exact. When the
reconstruction disagrees with the measured token total we LOWER the confidence, we
never adjust the figure (FR-024). Transcript format verified from the system
2026-09-15: assistant lines are ``type == "assistant"`` with ``message.{model, id,
content, usage}`` and a top-level ``timestamp``; user lines are ``type == "user"``.
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

# The reconstruction omits system + tools, so it systematically undercounts. A ratio
# near 1 means the message history was most of the prefix (higher confidence); a low
# ratio means a large unseen system/tool block (lower confidence). Never "exact".
_HIGH_BAND = (0.7, 1.3)
_BYTES_PER_TOKEN = 4


def _content_text(content: Any) -> str:
    """Flatten a message's content to text.

    Real transcripts nest arbitrarily: a string, a list of blocks, or a block whose
    ``text``/``content`` is itself a list (e.g. a tool_result). Recurse so every part
    reduces to a string and the join never sees a list.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        inner = content.get("text")
        if inner is None:
            inner = content.get("content")
        return _content_text(inner) if inner is not None else str(content.get("type", ""))
    if isinstance(content, list):
        return " ".join(s for s in (_content_text(b) for b in content) if s)
    return "" if content is None else str(content)


def _usage(u: dict[str, Any]) -> Usage:
    cc = u.get("cache_creation") or {}
    return Usage(
        input_tokens=int(u.get("input_tokens", 0) or 0),
        cache_creation_input_tokens=int(u.get("cache_creation_input_tokens", 0) or 0),
        cache_read_input_tokens=int(u.get("cache_read_input_tokens", 0) or 0),
        ephemeral_5m_input_tokens=cc.get("ephemeral_5m_input_tokens"),
        ephemeral_1h_input_tokens=cc.get("ephemeral_1h_input_tokens"),
    )


def _grade(prefix_len_bytes: int, usage: Usage) -> ConfidenceGrade:
    measured_total = usage.input_tokens + usage.cache_read_input_tokens + usage.cache_creation_input_tokens
    if measured_total <= 0:
        return ConfidenceGrade.RECONSTRUCTED_LOW
    est_tokens = prefix_len_bytes / _BYTES_PER_TOKEN
    ratio = est_tokens / measured_total
    return ConfidenceGrade.RECONSTRUCTED_HIGH if _HIGH_BAND[0] <= ratio <= _HIGH_BAND[1] else ConfidenceGrade.RECONSTRUCTED_LOW


def reconstruct_transcript(path: str | Path, store: CacheStore) -> list[str]:
    """Ingest a transcript with growing-history reconstruction + calibrated confidence.

    Returns the turn ids in file order. The prefix for an assistant turn is the
    serialised history that preceded it (the input); the reply is then appended to
    the history for the next turn. Confidence is graded per turn; never exact.
    """
    turn_ids: list[str] = []
    history: list[dict[str, str]] = []
    previous_message_id: str | None = None

    with Path(path).open(encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(line, dict):
                continue
            msg = line.get("message")
            if not isinstance(msg, dict):
                continue
            role = msg.get("role") or line.get("type")
            text = _content_text(msg.get("content"))

            if line.get("type") == "assistant" and isinstance(msg.get("usage"), dict):
                # prefix = the input history that produced this turn (history so far)
                prefix = json.dumps(history, sort_keys=True).encode("utf-8")
                usage = _usage(msg["usage"])
                record = CaptureIngestionRecord(
                    source_kind=SourceKind.CLAUDE_CODE_TRANSCRIPT,
                    confidence_grade=_grade(len(prefix), usage),
                    model_id=msg.get("model", ""),
                    timestamp=line.get("timestamp", ""),
                    usage=usage,
                    prefix_bytes=prefix if prefix else b"[]",
                    response_message_id=msg.get("id"),
                    previous_message_id=previous_message_id,
                )
                turn_ids.append(api.ingest(record, store))
                previous_message_id = msg.get("id")

            # append this turn (user or assistant) to the running history
            if role and text:
                history.append({"role": str(role), "content": text})

    return turn_ids
