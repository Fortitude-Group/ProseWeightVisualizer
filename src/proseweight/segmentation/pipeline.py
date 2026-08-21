"""Instruction segmentation: rules layer + optional local-model split step.

Rules layer (fully deterministic, no model): markdown-it-py block AST + an
XML-tag pre-pass + pysbd sentence splitting of prose blocks. The local-model
clause-split step is injected as a callable (see ``SplitModel``) so the rules
layer is testable without any model; the default is a no-op that keeps sentence
boundaries (research.md R2).
"""

from __future__ import annotations

import re
from typing import Protocol

from markdown_it import MarkdownIt

from proseweight.segmentation.model import Segment, assert_round_trip

# Block-start XML-ish tags (custom prompt tags, often not valid HTML). Matched
# only at line start to avoid catching inline generics like ``<Type>``.
_XML_OPEN = re.compile(r"^<([A-Za-z][\w:-]*)(?:\s[^>]*)?>\s*$")
_XML_CLOSE_TMPL = r"^</{tag}>\s*$"


class SplitModel(Protocol):
    """Turns a prose block into clause split offsets (block-local indices)."""

    def split_indices(self, text: str) -> list[int]: ...


class NoSplitModel:
    """Default: no further clause splitting beyond the rules layer."""

    def split_indices(self, text: str) -> list[int]:
        return []


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _extract_xml_blocks(source: str) -> list[tuple[int, int]]:
    """Find line-start <tag>...</tag> spans, returned as (start, end) char offsets."""
    lines = source.splitlines(keepends=True)
    offs = _line_offsets(source)
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        m = _XML_OPEN.match(lines[i].strip() + "\n") or _XML_OPEN.match(lines[i])
        if m:
            tag = m.group(1)
            close = re.compile(_XML_CLOSE_TMPL.format(tag=re.escape(tag)))
            j = i + 1
            while j < len(lines) and not close.match(lines[j]):
                j += 1
            if j < len(lines):
                spans.append((offs[i], offs[j + 1]))
                i = j + 1
                continue
        i += 1
    return spans


def _split_sentences(text: str) -> list[tuple[int, int]]:
    """Sentence spans within a prose block using pysbd, with offset recovery."""
    try:
        import pysbd

        seg = pysbd.Segmenter(language="en", clean=False, char_span=True)
        spans = seg.segment(text)
        out = []
        for sp in spans:
            out.append((sp.start, sp.end))
        if out:
            return out
    except Exception:
        pass
    # Fallback: naive split on sentence-ending punctuation.
    out = []
    start = 0
    for m in re.finditer(r"[.!?](?:\s+|$)", text):
        out.append((start, m.end()))
        start = m.end()
    if start < len(text):
        out.append((start, len(text)))
    return out or [(0, len(text))]


def segment_prompt(source: str, split_model: SplitModel | None = None) -> list[Segment]:
    """Segment a prompt into discrete instructions. Deterministic (rules layer)."""
    split_model = split_model or NoSplitModel()
    xml_spans = _extract_xml_blocks(source)
    segments: list[Segment] = []
    order = 0

    def _emit(start: int, end: int, block_type: str, level: int = 0) -> None:
        nonlocal order
        text = source[start:end]
        if not text.strip():
            return
        segments.append(
            Segment(
                id=f"i{order}",
                start_offset=start,
                end_offset=end,
                text=text,
                block_type=block_type,
                block_level=level,
                order_index=str(order),
            )
        )
        order += 1

    # Mask XML spans so the markdown parser doesn't see them; emit them atomic.
    masked = list(source)
    for s, e in xml_spans:
        for k in range(s, e):
            masked[k] = " " if source[k] != "\n" else "\n"
    masked_src = "".join(masked)

    md = MarkdownIt("commonmark")
    tokens = md.parse(masked_src)
    line_offs = _line_offsets(source)

    block_events: list[tuple[int, int, str]] = []
    for tok in tokens:
        if tok.map is None:
            continue
        start = line_offs[tok.map[0]]
        end = line_offs[min(tok.map[1], len(line_offs) - 1)]
        if tok.type == "fence" or tok.type == "code_block":
            block_events.append((start, end, "code_fence"))
        elif tok.type == "inline" and tok.content.strip():
            # inline content of a paragraph/heading/list item
            block_events.append((start, end, "prose"))

    # Merge XML spans in, then sort all block events by start offset.
    events = [(s, e, "xml_block") for s, e in xml_spans] + block_events
    events.sort(key=lambda t: t[0])

    for start, end, kind in events:
        if kind in ("code_fence", "xml_block"):
            _emit(start, end, kind)
            continue
        # prose: split into sentences, then optional model clause split
        block_text = source[start:end]
        for s0, s1 in _split_sentences(block_text):
            sent = block_text[s0:s1]
            base = start + s0
            extra = [i for i in split_model.split_indices(sent) if 0 < i < len(sent)]
            cuts = [0, *sorted(set(extra)), len(sent)]
            for a, b in zip(cuts, cuts[1:], strict=False):
                _emit(base + a, base + b, "paragraph")

    # renumber order_index / ids in document order
    segments.sort(key=lambda s: s.start_offset)
    for idx, seg in enumerate(segments):
        seg.id = f"i{idx}"
        seg.order_index = str(idx)

    assert_round_trip(source, segments)
    return segments


def merge(segments: list[Segment], ids: list[str], source: str) -> list[Segment]:
    """Merge adjacent segments (manual edit). Returns a new ordered list."""
    chosen = [s for s in segments if s.id in ids]
    if len(chosen) < 2:
        return segments
    chosen.sort(key=lambda s: s.start_offset)
    start, end = chosen[0].start_offset, chosen[-1].end_offset
    merged = Segment(
        id=chosen[0].id,
        start_offset=start,
        end_offset=end,
        text=source[start:end],
        block_type="paragraph",
        source="manual",
        merged_from=[s.id for s in chosen],
    )
    remaining = [s for s in segments if s.id not in ids]
    remaining.append(merged)
    remaining.sort(key=lambda s: s.start_offset)
    for idx, seg in enumerate(remaining):
        seg.order_index = str(idx)
    return remaining
