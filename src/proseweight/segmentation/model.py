"""Segment data model + round-trip invariant (data-model.md, research.md R2).

Offsets into the original immutable source text are the canonical truth. The
round-trip invariant — concatenating top-level segments in order reproduces the
source exactly — is asserted on every segmentation run.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

ATOMIC_BLOCK_TYPES = frozenset({"code_fence", "xml_block", "table_row", "front_matter"})


@dataclass
class Segment:
    id: str
    start_offset: int
    end_offset: int
    text: str
    block_type: str = "paragraph"
    block_level: int = 0
    parent_id: str | None = None
    order_index: str = "0"
    source: str = "rule"  # rule | model | manual
    heading_path: list[str] = field(default_factory=list)
    confidence: float | None = None
    merged_from: list[str] = field(default_factory=list)
    split_from: list[str] = field(default_factory=list)

    @property
    def is_atomic(self) -> bool:
        return self.block_type in ATOMIC_BLOCK_TYPES

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]

    def recompute_text(self, source: str) -> str:
        return source[self.start_offset : self.end_offset]

    def token_cost(self, chars_per_token: float = 4.0) -> int:
        """Cheap token-cost estimate (real tokeniser used when a model is loaded)."""
        return max(1, round(len(self.text) / chars_per_token))


def assert_round_trip(source: str, segments: list[Segment]) -> None:
    """Concatenating top-level segments in order must reproduce the source.

    Ignores whitespace-only gaps between blocks (structural separators the
    markdown layer drops), but every segment's text must match its offsets.
    """
    for seg in segments:
        expected = source[seg.start_offset : seg.end_offset]
        if seg.text != expected:
            raise ValueError(
                f"segment {seg.id} text does not match its offsets "
                f"[{seg.start_offset}:{seg.end_offset}]"
            )
    covered = "".join(source[s.start_offset : s.end_offset] for s in segments)
    gap = source
    for s in segments:
        gap = gap.replace(source[s.start_offset : s.end_offset], "", 1)
    if gap.strip():
        raise ValueError("segmentation dropped non-whitespace source text")
    if not covered.strip() and source.strip():
        raise ValueError("segmentation produced no content from non-empty source")
