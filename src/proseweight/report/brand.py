"""Fortitude Omnis branding for the report (render-time toggle).

The branded header is emitted only when ``brand=True`` so the same renderer can
still produce a neutral, Fortitude-free report for a different audience (see the
project's audience-dependent branding note). The lion logo (the official Fortitude
Omnis Group mark) is embedded as a base64 data URI so the report stays
self-contained. The mark is teal on transparent, so the header sits it in a light
tile for contrast.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

BRAND_NAME = "Fortitude Omnis Group"
BRAND_TAGLINE = "Prose Weight · Readout"

_LOGO_PATH = Path(__file__).parent / "assets" / "fortitude-logo.png"


@lru_cache(maxsize=1)
def lion_data_uri() -> str:
    """The Fortitude lion as a self-contained data URI (empty if the asset is absent)."""
    if not _LOGO_PATH.exists():
        return ""
    b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"
