"""Byte-level divergence detection + cause classification (US3 / FR-008/009).

The "here is the byte that did it" engine. A **linear first-divergence byte scan**
(not an edit-distance minimisation) gives the exact first differing offset — the
ground truth the cache invalidates on — and a deterministic classifier labels the
cause. Pure functions over bytes; part of the transplantable core.
"""

from __future__ import annotations

import re

from proseweight.cache.core.contracts import CauseClass

_ISO_TS = re.compile(rb"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_VOLATILE_HEADER = re.compile(
    rb"(date|updated|version|last[-_ ]?modified|timestamp|generated)\s*:", re.IGNORECASE
)


def first_divergence(a: bytes, b: bytes) -> int:
    """First byte offset at which ``a`` and ``b`` differ.

    Returns -1 if identical. If one is a strict prefix of the other, the offset is
    the length of the shorter (the point the longer one continues).
    """
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    if i == n:
        return -1 if len(a) == len(b) else n
    return i


def line_of(data: bytes, offset: int) -> int:
    """1-indexed line number of a byte offset."""
    return data.count(b"\n", 0, offset) + 1


def _line_bounds(data: bytes, offset: int) -> tuple[int, int]:
    start = data.rfind(b"\n", 0, offset) + 1
    end = data.find(b"\n", offset)
    if end == -1:
        end = len(data)
    return start, end


def _section_at(prefix: bytes, offset: int) -> str | None:
    """Best-effort: which request section (tools/system/messages) the offset falls in,
    by the byte position of the top-level keys in the serialised request JSON.
    """
    keys = []
    for name in (b'"tools"', b'"system"', b'"messages"'):
        pos = prefix.find(name)
        if pos != -1:
            keys.append((pos, name.strip(b'"').decode()))
    keys.sort()
    section = None
    for pos, name in keys:
        if pos <= offset:
            section = name
        else:
            break
    return section


def classify(
    prev: bytes, cur: bytes, offset: int, prev_model: str, cur_model: str
) -> tuple[CauseClass, bool]:
    """Return ``(cause, avoidable)`` for a divergence at ``offset``.

    Byte-hygiene causes are recognised exactly (SC-001). Structural causes are
    best-effort from the request JSON. Intended changes (model change, a genuine
    edit, a system-prompt change) are marked **non-avoidable** and excluded from
    waste attribution (FR-012).
    """
    if prev_model != cur_model:
        return CauseClass.MODEL_CHANGE, False

    # CRLF drift — one side has "\r\n" where the other has "\n" at the offset (SC-001).
    if prev[offset : offset + 2] == b"\r\n" and cur[offset : offset + 1] == b"\n":
        return CauseClass.CRLF_DRIFT, True
    if cur[offset : offset + 2] == b"\r\n" and prev[offset : offset + 1] == b"\n":
        return CauseClass.CRLF_DRIFT, True

    # Trailing whitespace — the divergent byte is space/tab and its line ends soon after.
    for side in (prev, cur):
        if offset < len(side) and side[offset : offset + 1] in (b" ", b"\t"):
            _, end = _line_bounds(side, offset)
            if side[offset:end].strip() == b"":
                return CauseClass.TRAILING_WHITESPACE, True

    # Volatile header / timestamp — inspect the diverging line of the newer prefix.
    lstart, lend = _line_bounds(cur, offset)
    line = cur[lstart:lend]
    if _ISO_TS.search(line):
        return CauseClass.TIMESTAMP_INJECTION, True
    if _VOLATILE_HEADER.search(line):
        return CauseClass.VOLATILE_HEADER, True

    # Structural, best-effort by request section.
    section = _section_at(cur, offset)
    if section == "tools":
        return CauseClass.TOOL_DEFINITION_CHURN, True
    if section == "system":
        return CauseClass.SYSTEM_PROMPT_CHANGE, False  # usually intended → not waste

    return CauseClass.GENUINE_EDIT, False
