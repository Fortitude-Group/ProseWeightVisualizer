"""Cache breakpoint resolution + block-survival state (US3 / FR-010/011).

Maps a divergence offset onto Anthropic's real cache breakpoints (up to 4, or one
implicit auto-cache breakpoint), computing which recompute, which survive, and
which were never eligible to cache because their prefix is below the model minimum
(SC-010). Pure functions over bytes + the per-model minimum; core-clean (takes the
minimum and bytes-per-token as arguments rather than importing pricing).
"""

from __future__ import annotations

from dataclasses import dataclass

from proseweight.cache.core.contracts import BreakpointMarker, BreakpointState

_MARKER = b'"cache_control"'


@dataclass
class ResolvedBreakpoint:
    index: int
    level: str
    capped_byte_offset: int
    capped_tokens: int
    ttl: str
    state: BreakpointState = BreakpointState.HIT

    def to_dict(self, turn_id: str) -> dict:
        return {
            "turn_id": turn_id,
            "index": self.index,
            "level": self.level,
            "capped_byte_offset": self.capped_byte_offset,
            "capped_tokens": self.capped_tokens,
            "ttl": self.ttl,
            "state": self.state.value,
        }


def _section_of(prefix: bytes, offset: int) -> str:
    section = "messages"
    for pos, name in sorted(
        (prefix.find(k), n)
        for k, n in ((b'"tools"', "tools"), (b'"system"', "system"), (b'"messages"', "messages"))
        if prefix.find(k) != -1
    ):
        if pos <= offset:
            section = name
    return section


def resolve(
    prefix: bytes,
    *,
    model_min_tokens: int,
    bytes_per_token: int,
    markers: list[BreakpointMarker] | None = None,
) -> list[ResolvedBreakpoint]:
    """Resolve the breakpoints for a captured request.

    Uses explicit ``cache_control`` markers when the capture carried them; otherwise
    locates ``"cache_control"`` occurrences in the request JSON (their byte position
    approximates the end of each cached block); failing that, models a single implicit
    breakpoint capping the whole prefix (auto-caching). ``capped_tokens`` is a
    byte/``bytes_per_token`` estimate (the honesty band lives in the figure, R5).
    """
    bpt = max(1, bytes_per_token)
    resolved: list[ResolvedBreakpoint] = []

    if markers:
        for m in sorted(markers, key=lambda x: x.index)[:4]:
            resolved.append(
                ResolvedBreakpoint(
                    index=m.index,
                    level=m.level.value,
                    capped_byte_offset=m.capped_byte_offset,
                    capped_tokens=m.capped_byte_offset // bpt,
                    ttl=m.ttl.value,
                )
            )
    else:
        offsets: list[int] = []
        start = 0
        while len(offsets) < 4:
            pos = prefix.find(_MARKER, start)
            if pos == -1:
                break
            offsets.append(pos)
            start = pos + len(_MARKER)
        if not offsets:
            offsets = [len(prefix)]  # implicit whole-prefix auto-cache breakpoint
        for i, off in enumerate(offsets):
            resolved.append(
                ResolvedBreakpoint(
                    index=i,
                    level=_section_of(prefix, off),
                    capped_byte_offset=off,
                    capped_tokens=off // bpt,
                    ttl="5m",
                )
            )
    return resolved


def assign_states(
    breakpoints: list[ResolvedBreakpoint],
    divergence_offset: int | None,
    model_min_tokens: int,
) -> None:
    """Set each breakpoint's survival state in place.

    - below the model minimum -> ``never_cached`` (never eligible; carries no waste, SC-010)
    - no divergence (identical prefix) -> ``hit``
    - the cached block reaches the divergent byte -> ``recomputed``
    - otherwise the earlier block survives -> ``hit``
    """
    for bp in breakpoints:
        if bp.capped_tokens < model_min_tokens:
            bp.state = BreakpointState.NEVER_CACHED
        elif divergence_offset is None or divergence_offset < 0:
            bp.state = BreakpointState.HIT
        elif bp.capped_byte_offset >= divergence_offset:
            bp.state = BreakpointState.RECOMPUTED
        else:
            bp.state = BreakpointState.HIT
