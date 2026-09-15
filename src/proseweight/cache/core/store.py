"""Local capture store — SQLite ledger + content-addressed blob directory (R3).

Append-only turns/lineages/breakpoints (+ tables reserved for R2 divergences /
attributions / rollups), plus a ``blobs/<sha256[:2]>/<sha256>`` store for raw
prefix bytes. Retention prunes a blob while keeping its row (hash + metadata) for
the longitudinal ledger (FR-003). Single-file, no service, offline (FR-005).

Stdlib only (``sqlite3``) — part of the transplantable core.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from proseweight.cache.core.contracts import (
    LINEAGE_PREFIX_WINDOW,
    CaptureIngestionRecord,
    sha256_hex,
)

SCHEMA_VERSION = 1

# Coarse lineage window: a turn joins an existing family only if it arrives within
# this gap of the family's last turn (bounded by the longest cache TTL, 1 hour).
LINEAGE_WINDOW = timedelta(hours=1)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS blobs (
    hash        TEXT PRIMARY KEY,
    byte_len    INTEGER NOT NULL,
    present     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS lineages (
    id              TEXT PRIMARY KEY,
    source_kind     TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    prefix_family_fp TEXT NOT NULL,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    id                  TEXT PRIMARY KEY,
    source_kind         TEXT NOT NULL,
    confidence_grade    TEXT NOT NULL,
    lineage_id          TEXT NOT NULL REFERENCES lineages(id),
    prefix_hash         TEXT NOT NULL REFERENCES blobs(hash),
    model_id            TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    input_tokens                INTEGER NOT NULL,
    cache_creation_input_tokens INTEGER NOT NULL,
    cache_read_input_tokens     INTEGER NOT NULL,
    ephemeral_5m_input_tokens   INTEGER,
    ephemeral_1h_input_tokens   INTEGER,
    response_message_id TEXT,
    previous_message_id TEXT,
    diagnostics_json    TEXT
);
CREATE INDEX IF NOT EXISTS idx_turns_lineage ON turns(lineage_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_turns_respid ON turns(response_message_id);
CREATE TABLE IF NOT EXISTS breakpoints (
    turn_id             TEXT NOT NULL REFERENCES turns(id),
    idx                 INTEGER NOT NULL,
    level               TEXT NOT NULL,
    capped_byte_offset  INTEGER NOT NULL,
    ttl                 TEXT NOT NULL,
    PRIMARY KEY (turn_id, idx)
);
-- Reserved for Release 2 (populated by analyse()/cost()); created now so the
-- schema version is stable and R2 adds no migration for table creation.
CREATE TABLE IF NOT EXISTS divergences (
    id TEXT PRIMARY KEY, lineage_id TEXT, prev_turn_id TEXT, turn_id TEXT,
    first_divergent_offset INTEGER, line INTEGER, cause TEXT, avoidable INTEGER,
    predicted_recomputed_tokens INTEGER
);
CREATE TABLE IF NOT EXISTS attributions (
    divergence_id TEXT PRIMARY KEY, billing_model TEXT, wasted_tokens INTEGER,
    wasted_gbp REAL, quota_tokens INTEGER, is_shadow_price INTEGER,
    pricing_version TEXT, effective_date TEXT, fx_date TEXT
);
"""


def _parse_ts(ts: str) -> datetime:
    s = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


class CacheStore:
    """The capture ledger. Construct with a db path; the blob dir sits beside it."""

    def __init__(self, db_path: str | Path, blob_dir: str | Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.blob_dir = Path(blob_dir) if blob_dir else self.db_path.parent / "blobs"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        cur = self.conn.execute("PRAGMA user_version")
        version = cur.fetchone()[0]
        if version < SCHEMA_VERSION:
            self.conn.executescript(_SCHEMA)
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> CacheStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- blobs ------------------------------------------------------------- #

    def _blob_path(self, h: str) -> Path:
        return self.blob_dir / h[:2] / h

    def put_blob(self, data: bytes) -> str:
        h = sha256_hex(data)
        p = self._blob_path(h)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        self.conn.execute(
            "INSERT INTO blobs(hash, byte_len, present) VALUES(?,?,1) "
            "ON CONFLICT(hash) DO UPDATE SET present=1",
            (h, len(data)),
        )
        return h

    def get_blob(self, h: str) -> bytes | None:
        p = self._blob_path(h)
        return p.read_bytes() if p.exists() else None

    # -- turns / lineages -------------------------------------------------- #

    def _assign_lineage(self, rec: CaptureIngestionRecord, prefix_hash: str) -> str:
        """Place a turn in a cache lineage (M1): authoritative message-id link first,
        else the leading-window fingerprint within the TTL window; else a new lineage.
        """
        ts = rec.timestamp
        # 1) authoritative: previous_message_id -> an existing turn's response_message_id
        if rec.previous_message_id:
            row = self.conn.execute(
                "SELECT lineage_id FROM turns WHERE response_message_id=? LIMIT 1",
                (rec.previous_message_id,),
            ).fetchone()
            if row:
                self._touch_lineage(row["lineage_id"], ts)
                return row["lineage_id"]
        # 2) fingerprint of the first LINEAGE_PREFIX_WINDOW bytes
        data = self.get_blob(prefix_hash) or b""
        fp = sha256_hex(data[:LINEAGE_PREFIX_WINDOW])
        cutoff = (_parse_ts(ts) - LINEAGE_WINDOW).isoformat()
        row = self.conn.execute(
            "SELECT id, last_seen FROM lineages WHERE source_kind=? AND model_id=? "
            "AND prefix_family_fp=? AND last_seen>=? ORDER BY last_seen DESC LIMIT 1",
            (rec.source_kind.value, rec.model_id, fp, cutoff),
        ).fetchone()
        if row:
            self._touch_lineage(row["id"], ts)
            return row["id"]
        # 3) new lineage
        lineage_id = f"lin_{fp[:12]}_{_parse_ts(ts).strftime('%Y%m%d%H%M%S')}"
        self.conn.execute(
            "INSERT OR IGNORE INTO lineages(id, source_kind, model_id, prefix_family_fp, first_seen, last_seen) "
            "VALUES(?,?,?,?,?,?)",
            (lineage_id, rec.source_kind.value, rec.model_id, fp, ts, ts),
        )
        return lineage_id

    def _touch_lineage(self, lineage_id: str, ts: str) -> None:
        self.conn.execute(
            "UPDATE lineages SET last_seen=? WHERE id=? AND last_seen<?",
            (ts, lineage_id, ts),
        )

    def add_turn(self, rec: CaptureIngestionRecord) -> str:
        """Append a validated capture. Returns the turn id. Append-only (FR-003)."""
        rec.validate()
        if rec.prefix_bytes is not None:
            prefix_hash = self.put_blob(rec.prefix_bytes)
        else:
            prefix_hash = rec.prefix_hash()
            self.conn.execute(
                "INSERT OR IGNORE INTO blobs(hash, byte_len, present) VALUES(?,?,0)",
                (prefix_hash, rec.byte_len()),
            )
        lineage_id = self._assign_lineage(rec, prefix_hash)
        turn_id = f"turn_{rec.response_message_id or sha256_hex((prefix_hash + rec.timestamp).encode())[:16]}"
        import json as _json

        self.conn.execute(
            "INSERT OR REPLACE INTO turns(id, source_kind, confidence_grade, lineage_id, prefix_hash, "
            "model_id, timestamp, input_tokens, cache_creation_input_tokens, cache_read_input_tokens, "
            "ephemeral_5m_input_tokens, ephemeral_1h_input_tokens, response_message_id, "
            "previous_message_id, diagnostics_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                turn_id, rec.source_kind.value, rec.confidence_grade.value, lineage_id, prefix_hash,
                rec.model_id, rec.timestamp, rec.usage.input_tokens,
                rec.usage.cache_creation_input_tokens, rec.usage.cache_read_input_tokens,
                rec.usage.ephemeral_5m_input_tokens, rec.usage.ephemeral_1h_input_tokens,
                rec.response_message_id, rec.previous_message_id,
                _json.dumps(rec.diagnostics) if rec.diagnostics is not None else None,
            ),
        )
        for bp in rec.breakpoints:
            self.conn.execute(
                "INSERT OR REPLACE INTO breakpoints(turn_id, idx, level, capped_byte_offset, ttl) "
                "VALUES(?,?,?,?,?)",
                (turn_id, bp.index, bp.level.value, bp.capped_byte_offset, bp.ttl.value),
            )
        self.conn.commit()
        return turn_id

    def turn_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0])

    def lineage_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM lineages").fetchone()[0])

    # -- retention --------------------------------------------------------- #

    def prune(self, retention_days: int, now: datetime | None = None) -> int:
        """Delete raw prefix blobs for turns older than ``retention_days``; keep the
        rows (hash + metadata) for the longitudinal ledger. Returns blobs pruned.
        """
        now = now or datetime.now(UTC)
        cutoff = (now - timedelta(days=retention_days)).isoformat()
        rows = self.conn.execute(
            "SELECT DISTINCT prefix_hash FROM turns WHERE timestamp < ?", (cutoff,)
        ).fetchall()
        pruned = 0
        for row in rows:
            h = row["prefix_hash"]
            # only prune a blob if no *retained* turn still needs it
            still = self.conn.execute(
                "SELECT 1 FROM turns WHERE prefix_hash=? AND timestamp >= ? LIMIT 1", (h, cutoff)
            ).fetchone()
            if still:
                continue
            p = self._blob_path(h)
            if p.exists():
                p.unlink()
                pruned += 1
            self.conn.execute("UPDATE blobs SET present=0 WHERE hash=?", (h,))
        self.conn.commit()
        return pruned
