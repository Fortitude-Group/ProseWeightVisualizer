"""Static cache-hygiene lint — the prediction layer (US2 / FR-006/007).

Runs with **no captured data, no API, no model**: reads target files as raw bytes,
finds cache-hostile patterns, and emits ``LintFinding``s each framed as a
**prediction** the profiler can later confirm with measurement, with a transparent
estimated monthly cost (Principle XII). Part of the transplantable core.

Rules: crlf_drift, trailing_whitespace, volatile_header, concat_order.
"""

from __future__ import annotations

import re
from pathlib import Path

from proseweight.cache.core.contracts import LintFinding
from proseweight.cache.core.pricing import Pricing

_VOLATILE_HEADER = re.compile(
    rb"^\s*(date|updated|version|last[-_ ]?modified|timestamp|generated)\s*:",
    re.IGNORECASE,
)
_ISO_TS = re.compile(rb"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_VOLATILE_HEADER_WINDOW_LINES = 8


def _line_of(data: bytes, offset: int) -> int:
    """1-indexed line number of a byte offset."""
    return data.count(b"\n", 0, offset) + 1


def _finding(
    pricing: Pricing,
    rule_id: str,
    file: str,
    data: bytes,
    offset: int,
    model_id: str | None,
) -> LintFinding:
    stamp = pricing.stamp()
    affected = max(1, len(data) - offset)  # bytes after the hostile point recompute
    f = LintFinding(
        rule_id=rule_id,
        file=file,
        line=_line_of(data, offset),
        offset=offset,
        estimated_monthly_gbp=pricing.estimate_monthly_gbp(affected, model_id),
        pricing_version=stamp.pricing_version,
        effective_date=stamp.effective_date,
        fx_date=stamp.fx_date,
    )
    f.id = f"lf_{rule_id}_{file.replace('/', '_')}_{offset}"
    return f.validate()


def lint_bytes(
    data: bytes, file_label: str, pricing: Pricing, model_id: str | None = None
) -> list[LintFinding]:
    """Lint one file's raw bytes. One finding per offending line/pattern."""
    findings: list[LintFinding] = []

    # Walk lines, tracking byte offsets. Split keeping structure via manual scan.
    line_start = 0
    line_no = 0
    for raw_line in data.splitlines(keepends=True):
        line_no += 1
        # strip the trailing newline(s) to inspect content + ending
        has_crlf = raw_line.endswith(b"\r\n")
        content = raw_line.rstrip(b"\r\n")

        # crlf_drift — a \r\n ending (cache-hostile relative to LF-normalised text)
        if has_crlf:
            cr_off = line_start + len(content)
            findings.append(_finding(pricing, "crlf_drift", file_label, data, cr_off, model_id))

        # trailing_whitespace — space/tab at end of content (ignoring the \r)
        if content and content[-1:] in (b" ", b"\t"):
            # offset of the first trailing-whitespace byte
            stripped = content.rstrip(b" \t")
            findings.append(
                _finding(pricing, "trailing_whitespace", file_label, data,
                         line_start + len(stripped), model_id)
            )

        # volatile_header — only in the early lines (headers/front-matter)
        if line_no <= _VOLATILE_HEADER_WINDOW_LINES and (
            _VOLATILE_HEADER.search(content) or _ISO_TS.search(content)
        ):
            findings.append(_finding(pricing, "volatile_header", file_label, data, line_start, model_id))

        line_start += len(raw_line)

    return findings


def lint_files(
    paths: list[str | Path], pricing: Pricing | None = None, model_id: str | None = None
) -> list[LintFinding]:
    """Lint each target file (``~`` expanded). Adds a concat_order finding when a set
    of files is not in LC_ALL=C (byte-sorted) order — the order the cache concatenates.
    """
    pricing = pricing or Pricing.load()
    findings: list[LintFinding] = []
    resolved: list[Path] = [Path(str(p)).expanduser() for p in paths]

    for p in resolved:
        if not p.exists():
            continue
        data = p.read_bytes()
        findings.extend(lint_bytes(data, str(p), pricing, model_id))

    # concat_order: multiple files whose given order differs from byte-sorted order
    if len(resolved) > 1:
        names = [str(p) for p in resolved]
        if names != sorted(names):
            stamp = pricing.stamp()
            f = LintFinding(
                rule_id="concat_order",
                file=names[0],
                line=1,
                offset=0,
                estimated_monthly_gbp=0.0,  # ordering cost depends on which prefix moves; flagged, not priced
                pricing_version=stamp.pricing_version,
                effective_date=stamp.effective_date,
                fx_date=stamp.fx_date,
            )
            f.id = "lf_concat_order"
            findings.append(f.validate())

    return findings
