"""PNG summary card for a CacheScopeResult (US6 / FR-023a).

A compact shareable card: the headline waste figure and the top causes. Uses
Pillow (a core dependency) with its built-in font, so it needs no external asset
and imports nothing from the 001 report package. Brand-neutral by default; a
Fortitude accent is an opt-in switch.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

_CAUSE_HUES = {
    "crlf_drift": (42, 120, 214), "trailing_whitespace": (235, 104, 52),
    "volatile_header": (27, 175, 122), "timestamp_injection": (237, 161, 0),
    "concat_order_change": (232, 123, 164), "tool_definition_churn": (0, 131, 0),
    "system_prompt_change": (74, 58, 167), "model_change": (227, 73, 72),
    "genuine_edit": (138, 137, 133),
}


def _headline(result: dict) -> tuple[str, float, str]:
    by_cause: dict[str, float] = {}
    meter = "measured"
    for r in result.get("rollups", []):
        by_cause[r["cause"]] = by_cause.get(r["cause"], 0.0) + r["wasted_gbp"]
        if r["billing_model"] == "subscription":
            meter = "shadow-price"
    if not by_cause:
        return ("none", 0.0, meter)
    top = max(by_cause.items(), key=lambda kv: kv[1])
    return (top[0], top[1], meter)


def render_png(result: dict, out_path: str, theme: str = "neutral") -> None:
    dark = theme == "dark"
    bg = (26, 26, 25) if dark else (252, 252, 251)
    ink = (255, 255, 255) if dark else (11, 11, 11)
    muted = (195, 194, 183) if dark else (82, 81, 78)
    accent = (15, 118, 110) if theme == "fortitude" else (42, 120, 214)

    W, H = 820, 360
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 6], fill=accent)

    cause, val, meter = _headline(result)
    pricing = result.get("pricing", {})
    d.text((28, 28), "CacheScope report", fill=ink)
    d.text((28, 48), f"pricing {pricing.get('pricing_version', '?')}  fx {pricing.get('fx_date', '?')}", fill=muted)
    d.text((28, 92), f"Headline: {cause}  £{val:.2f}  ({meter})", fill=ink)

    by_cause: dict[str, float] = {}
    for r in result.get("rollups", []):
        by_cause[r["cause"]] = by_cause.get(r["cause"], 0.0) + r["wasted_gbp"]
    rows = sorted(by_cause.items(), key=lambda kv: -kv[1])[:6]
    top = max((v for _, v in rows), default=1.0) or 1.0
    y = 140
    for name, v in rows:
        w = max(3, int(560 * (v / top)))
        colour = _CAUSE_HUES.get(name, (138, 137, 133))
        d.text((28, y), name, fill=muted)
        d.rectangle([210, y, 210 + w, y + 16], fill=colour)
        d.text((210 + w + 8, y), f"£{v:.2f}", fill=ink)
        y += 30

    d.text((28, H - 28), "measured £ on PAYG; subscription = shadow-price, not a bill", fill=muted)
    img.save(out_path, "PNG")
