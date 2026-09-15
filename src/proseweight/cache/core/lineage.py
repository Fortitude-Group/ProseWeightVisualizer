"""Cache-lineage pairing for divergence analysis (US3 / FR-008).

Lineages are assigned at ingest time (see ``store._assign_lineage``); this module
reads the store and yields the **consecutive turn pairs within each lineage**, in
time order, that divergence analysis compares. Turns are never paired across
lineages. Core-clean (reads the store, imports nothing outside the core).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from proseweight.cache.core.store import CacheStore


@dataclass
class TurnView:
    id: str
    lineage_id: str
    source_kind: str
    model_id: str
    timestamp: str
    prefix_hash: str
    prefix_bytes: bytes
    byte_len: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


def _turn_view(store: CacheStore, row) -> TurnView:
    data = store.get_blob(row["prefix_hash"]) or b""
    return TurnView(
        id=row["id"],
        lineage_id=row["lineage_id"],
        source_kind=row["source_kind"],
        model_id=row["model_id"],
        timestamp=row["timestamp"],
        prefix_hash=row["prefix_hash"],
        prefix_bytes=data,
        byte_len=len(data),
        cache_read_input_tokens=row["cache_read_input_tokens"],
        cache_creation_input_tokens=row["cache_creation_input_tokens"],
    )


def lineages(store: CacheStore) -> dict[str, list[TurnView]]:
    """All lineages, each a time-ordered list of its turns."""
    out: dict[str, list[TurnView]] = {}
    rows = store.conn.execute(
        "SELECT * FROM turns ORDER BY lineage_id, timestamp, id"
    ).fetchall()
    for row in rows:
        out.setdefault(row["lineage_id"], []).append(_turn_view(store, row))
    return out


def consecutive_pairs(turns: list[TurnView]) -> Iterator[tuple[TurnView, TurnView]]:
    """Yield (previous, current) for each adjacent pair in one lineage's ordered turns."""
    yield from zip(turns, turns[1:], strict=False)
