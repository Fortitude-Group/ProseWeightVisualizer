"""Programmatic check runner (the PROG signal).

Deterministic pass/fail (or [0,1]) checks on a model output, covering the
Python-native promptfoo assert types. JavaScript/Python file:// checks need an
external runtime and are reported as ``skipped`` rather than silently passing.
Pure Python, fully testable without model weights.
"""

from __future__ import annotations

import json
import re

# refusal boilerplate heuristics (case-insensitive)
_REFUSAL = re.compile(
    r"\b(i (can'?t|cannot|won'?t|am unable to|am not able to)|i'?m sorry,? but|"
    r"i am sorry,? but|as an ai|i must decline|i can not (help|assist)|"
    r"i'?m not able to (help|assist)|consult (a|your) (doctor|professional|physician))\b",
    re.IGNORECASE,
)


def is_json(output: str) -> bool:
    try:
        json.loads(output.strip())
        return True
    except (ValueError, TypeError):
        return False


def is_refusal(output: str) -> bool:
    return _REFUSAL.search(output or "") is not None


def word_count(output: str) -> int:
    return len(re.findall(r"\b\w+\b", output or ""))


def sentence_count(output: str) -> int:
    parts = [p for p in re.split(r"[.!?]+", output or "") if p.strip()]
    return len(parts)


def run_check(assertion: dict, output: str) -> float | None:
    """Return 1.0 (satisfied), 0.0 (not), or None (needs an external runtime).

    ``not-`` prefixed types invert the base check.
    """
    atype = assertion.get("type", "")
    value = assertion.get("value")
    negate = atype.startswith("not-")
    base = atype[4:] if negate else atype

    if base == "is-json":
        result = is_json(output)
    elif base == "is-refusal":
        result = is_refusal(output)
    elif base == "contains":
        result = str(value) in (output or "")
    elif base == "contains-all":
        items = value if isinstance(value, list) else [value]
        result = all(str(i) in (output or "") for i in items)
    elif base == "regex":
        result = re.search(str(value), output or "") is not None
    else:
        # javascript / python file:// checks require an external runtime.
        return None

    if negate:
        result = not result
    return 1.0 if result else 0.0


def non_empty(output: str) -> float:
    """The weak PROG floor every shipped probe carries (FR-006c)."""
    return 1.0 if (output or "").strip() else 0.0
