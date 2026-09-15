"""Unit test: HTML/PNG export adapter (T039 / US6)."""

from __future__ import annotations

from proseweight.cache.core import api
from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.store import CacheStore
from proseweight.cache.report.export_html import export_html
from proseweight.cache.report.png_card import render_png


def _rec(prefix, ts, resp_id, prev_id=None):
    return CaptureIngestionRecord(
        source_kind=SourceKind.API_PROXY, confidence_grade=ConfidenceGrade.EXACT,
        model_id="claude-opus-5", timestamp=ts,
        usage=Usage(input_tokens=5, cache_read_input_tokens=1000),
        prefix_bytes=prefix, response_message_id=resp_id, previous_message_id=prev_id,
    )


def _built_store(tmp_path) -> CacheStore:
    store = CacheStore(tmp_path / "cache.db")
    tail = b"A" * 6000
    store.add_turn(_rec(b"X\r\n" + tail, "2026-09-14T10:00:00Z", "p1"))
    store.add_turn(_rec(b"X\n" + tail, "2026-09-14T10:01:00Z", "p2", "p1"))
    # a tiny prefix -> its own lineage head, below the model minimum -> never_cached
    store.add_turn(_rec(b"tiny prompt", "2026-09-14T10:02:00Z", "t1"))
    return store


def test_html_has_three_views_and_is_brand_neutral(tmp_path):
    store = _built_store(tmp_path)
    result = api.analyse(store).to_dict()
    doc = export_html(result, store=store, theme="neutral")
    assert "Block survival" in doc
    assert "Cost ledger" in doc
    assert "Prediction versus measured" in doc
    assert 'data-theme="neutral"' in doc
    assert "<title>CacheScope report</title>" in doc
    store.close()


def test_never_cached_is_hatched_and_distinct(tmp_path):
    store = _built_store(tmp_path)
    result = api.analyse(store).to_dict()
    # the tiny-prefix head must be a never_cached breakpoint
    states = {b["state"] for b in result["breakpoints"]}
    assert "never_cached" in states
    doc = export_html(result, store=store)
    assert "url(#hatch)" in doc  # never-cached rendered with a hatch, not colour alone
    assert "never cached" in doc  # labelled in the legend


def test_click_a_miss_opens_byte_diff(tmp_path):
    store = _built_store(tmp_path)
    result = api.analyse(store).to_dict()
    div_id = result["divergences"][0]["id"]
    doc = export_html(result, store=store)
    assert f"data-panel='panel-{div_id}'" in doc  # a clickable recomputed cell
    assert f"id='panel-{div_id}'" in doc            # ... targets a byte-diff panel
    assert "<mark>" in doc                          # the divergent byte is highlighted


def test_pred_vs_measured_states_no_measurement(tmp_path):
    store = _built_store(tmp_path)
    result = api.analyse(store).to_dict()
    doc = export_html(result, store=store)
    assert "no measurement" in doc  # reconciliation absent -> never treated as agreement
    store.close()


def test_png_renders(tmp_path):
    store = _built_store(tmp_path)
    result = api.analyse(store).to_dict()
    out = tmp_path / "card.png"
    render_png(result, str(out), theme="neutral")
    assert out.exists()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
    store.close()
