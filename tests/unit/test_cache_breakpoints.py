"""Unit test: breakpoint resolution + survival state (T028 / US3 / SC-010)."""

from __future__ import annotations

from proseweight.cache.core.breakpoints import assign_states, resolve
from proseweight.cache.core.contracts import BreakpointState


def test_below_minimum_is_never_cached():
    # tiny prefix, high model minimum -> never eligible to cache
    bps = resolve(b"x" * 40, model_min_tokens=512, bytes_per_token=4)
    assign_states(bps, divergence_offset=0, model_min_tokens=512)
    assert all(b.state is BreakpointState.NEVER_CACHED for b in bps)


def test_recomputed_vs_hit_by_offset():
    prefix = b"y" * 8000  # 2000 tokens at 4 bytes/token, above 512 minimum
    bps = resolve(prefix, model_min_tokens=512, bytes_per_token=4)
    # implicit whole-prefix breakpoint caps at len(prefix); a divergence inside it recomputes
    assign_states(bps, divergence_offset=10, model_min_tokens=512)
    assert bps[0].state is BreakpointState.RECOMPUTED
    # no divergence -> hit
    assign_states(bps, divergence_offset=None, model_min_tokens=512)
    assert bps[0].state is BreakpointState.HIT


def test_never_cached_distinct_from_recomputed():
    prefix = b"z" * 100  # 25 tokens, below 512
    bps = resolve(prefix, model_min_tokens=512, bytes_per_token=4)
    assign_states(bps, divergence_offset=5, model_min_tokens=512)
    # even with a divergence inside it, a below-minimum prefix is never_cached, not recomputed
    assert bps[0].state is BreakpointState.NEVER_CACHED
    assert bps[0].state is not BreakpointState.RECOMPUTED


def test_explicit_cache_control_markers_resolved():
    prefix = b'{"system":[{"text":"...","cache_control":{"type":"ephemeral"}}],"messages":[]}'
    bps = resolve(prefix, model_min_tokens=1, bytes_per_token=4)
    assert len(bps) == 1
    assert bps[0].capped_byte_offset == prefix.find(b'"cache_control"')
