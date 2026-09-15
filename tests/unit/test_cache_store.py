"""Unit test: CacheStore (T009) — append-only, blob dedup, retention prune, lineage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.store import CacheStore


def _rec(prefix: bytes, ts: str, *, resp_id=None, prev_id=None) -> CaptureIngestionRecord:
    return CaptureIngestionRecord(
        source_kind=SourceKind.API_PROXY,
        confidence_grade=ConfidenceGrade.EXACT,
        model_id="claude-opus-5",
        timestamp=ts,
        usage=Usage(input_tokens=10, cache_read_input_tokens=100),
        prefix_bytes=prefix,
        response_message_id=resp_id,
        previous_message_id=prev_id,
    )


def test_append_and_blob_dedup(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    big = b"A" * 5000
    store.add_turn(_rec(big, "2026-09-14T10:00:00Z", resp_id="msg_1"))
    store.add_turn(_rec(big, "2026-09-14T10:01:00Z", resp_id="msg_2", prev_id="msg_1"))
    assert store.turn_count() == 2
    # identical prefix bytes → one blob file
    blob_files = list((tmp_path / "blobs").rglob("*"))
    blob_files = [p for p in blob_files if p.is_file()]
    assert len(blob_files) == 1
    store.close()


def test_message_id_link_groups_one_lineage(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    store.add_turn(_rec(b"A" * 5000, "2026-09-14T10:00:00Z", resp_id="msg_1"))
    store.add_turn(_rec(b"A" * 5000 + b"tail", "2026-09-14T10:01:00Z", resp_id="msg_2", prev_id="msg_1"))
    # previous_message_id links them even though bytes differ after the window
    assert store.lineage_count() == 1
    store.close()


def test_fingerprint_groups_without_message_id(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    shared = b"S" * 5000
    store.add_turn(_rec(shared, "2026-09-14T10:00:00Z"))
    store.add_turn(_rec(shared + b"more", "2026-09-14T10:02:00Z"))
    assert store.lineage_count() == 1  # same first-4096-byte fingerprint, within window
    # a different leading window → a new lineage
    store.add_turn(_rec(b"D" * 5000, "2026-09-14T10:03:00Z"))
    assert store.lineage_count() == 2
    store.close()


def test_retention_prunes_blob_keeps_row(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    old_ts = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    store.add_turn(_rec(b"Z" * 5000, old_ts, resp_id="old"))
    pruned = store.prune(retention_days=30)
    assert pruned == 1
    assert store.turn_count() == 1  # row survives
    # blob bytes gone
    hashes = [r["hash"] for r in store.conn.execute("SELECT hash FROM blobs").fetchall()]
    assert store.get_blob(hashes[0]) is None
    present = store.conn.execute("SELECT present FROM blobs WHERE hash=?", (hashes[0],)).fetchone()[0]
    assert present == 0
    store.close()


def test_migration_idempotent(tmp_path):
    p = tmp_path / "cache.db"
    CacheStore(p).close()
    store = CacheStore(p)  # reopen — user_version already set, no error
    assert store.conn.execute("PRAGMA user_version").fetchone()[0] == 1
    store.close()
