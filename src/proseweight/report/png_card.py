"""Deterministic PNG summary card (research.md R5 / FR-029).

Fixed-layout Pillow draw. Time/randomness are never touched here, so the output
is byte-stable for a given Pillow version (golden-test on decoded pixels, per
research.md). NOTE: the production path loads a checked-in OFL font (T004); until
that binary is committed this falls back to Pillow's bundled default font, which
is still deterministic but visually plainer.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from proseweight.report.schema import Classification, Verdict

_W, _H = 640, 360
_TEAL = (21, 82, 99)
_BG = (255, 255, 255)
_FG = (20, 32, 31)
_MUTED = (90, 107, 110)
_CLASS_RGB = {
    Classification.LOAD_BEARING: (21, 82, 99),
    Classification.CONTRIBUTING: (60, 141, 163),
    Classification.DECORATIVE: (183, 196, 201),
    Classification.CONTRADICTED: (192, 83, 43),
}

_FONT_PATH = Path(__file__).parent / "assets" / "fonts"


def _font(size: int):
    for name in ("Inter-Regular.ttf", "IBMPlexSans-Regular.ttf"):
        p = _FONT_PATH / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def render_card(verdict: Verdict) -> Image.Image:
    img = Image.new("RGB", (_W, _H), _BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, _W, 6], fill=_TEAL)
    d.text((28, 30), "Prompt weight verdict", font=_font(20), fill=_TEAL)
    d.text(
        (28, 66),
        f"{verdict.noise_floor_headline_pct:.0f}% below the noise floor",
        font=_font(30),
        fill=_FG,
    )
    d.text(
        (28, 108),
        f"suite {verdict.run.suite_version} · {verdict.run.subject_model.model_id}",
        font=_font(14),
        fill=_MUTED,
    )
    # top instruction bars (up to 6)
    y = 150
    for row in verdict.rows[:6]:
        colour = _CLASS_RGB.get(row.label, (150, 150, 150))
        w = int(360 * row.weight.weight / 100.0)
        d.text((28, y), f"{row.weight.weight:.0f}", font=_font(13), fill=_FG)
        d.rectangle([64, y + 2, 64 + w, y + 14], fill=colour)
        y += 30
    return img


def export_png_card(verdict: Verdict, path: str | Path) -> Path:
    out = Path(path)
    # never write PNG metadata chunks (determinism); fixed compression
    render_card(verdict).save(out, format="PNG", compress_level=6)
    return out
