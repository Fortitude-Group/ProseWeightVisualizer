"""Self-contained HTML export adapter for a CacheScopeResult (US6 / FR-021/022/023).

A **consumer** of the result contract, never part of the transplantable core
(FR-023a). Emits one self-contained HTML file (inline CSS/SVG/JS, no server, no
external assets) with three views: a block-survival heatmap (breakpoints on the y
axis, a distinct never-cached state), a cost ledger (waste by cause with a headline
figure), and a prediction-vs-measured view. Clicking a miss opens the byte diff.

Colours come from the validated dataviz reference palette; every state and cause
carries a label so identity is never colour-alone. Brand-neutral by default; a
Fortitude theme is an opt-in switch on the palette only.
"""

from __future__ import annotations

import html

from proseweight.cache.core.store import CacheStore

# Status-style colours for the four breakpoint states (validated reference palette).
_STATE = {
    "hit": ("#0ca30c", "hit"),
    "recomputed": ("#ec835a", "recomputed"),
    "new": ("#2a78d6", "new"),
    "never_cached": ("#8a8985", "never cached"),  # rendered with a hatch, not colour alone
}

# Fixed categorical order for causes (never cycled); a 9th folds to "other".
_CAUSE_ORDER = [
    "crlf_drift", "trailing_whitespace", "volatile_header", "timestamp_injection",
    "concat_order_change", "tool_definition_churn", "system_prompt_change",
    "model_change", "genuine_edit",
]
_CAUSE_HUES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948", "#8a8985"]


def _cause_color(cause: str) -> str:
    try:
        return _CAUSE_HUES[_CAUSE_ORDER.index(cause)]
    except ValueError:
        return "#8a8985"


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _visible(b: bytes) -> str:
    """Render a byte window readable: control chars as caret glyphs, HTML-escaped."""
    out = []
    for byte in b:
        ch = chr(byte)
        if ch == "\r":
            out.append("␍")
        elif ch == "\n":
            out.append("␊\n")
        elif ch == "\t":
            out.append("␉")
        elif 32 <= byte < 127:
            out.append(_esc(ch))
        else:
            out.append(f"\\x{byte:02x}")
    return "".join(out)


def _prefix_hash_by_turn(store: CacheStore) -> dict[str, str]:
    rows = store.conn.execute("SELECT id, prefix_hash FROM turns").fetchall()
    return {r["id"]: r["prefix_hash"] for r in rows}


def _byte_diff_panel(div: dict, store: CacheStore | None, hashes: dict[str, str]) -> str:
    """A hidden panel showing the divergence context, with the divergent byte marked."""
    offset = div["first_divergent_offset"]
    header = (
        f"<b>{_esc(div['cause'])}</b> at byte {offset} (line {div['line']}), "
        f"{'avoidable' if div['avoidable'] else 'intended'} · "
        f"predicted recompute {div['predicted_recomputed_tokens']} tokens"
    )
    body = "<p class='muted'>Raw prefix bytes unavailable (no store, or pruned by retention).</p>"
    if store is not None:
        prev_bytes = store.get_blob(hashes.get(div["prev_turn_id"], "")) or b""
        cur_bytes = store.get_blob(hashes.get(div["turn_id"], "")) or b""
        lo = max(0, offset - 48)
        prev_win = _visible(prev_bytes[lo:offset]) + "<mark>" + _visible(prev_bytes[offset:offset + 2]) + "</mark>" + _visible(prev_bytes[offset + 2:offset + 48])
        cur_win = _visible(cur_bytes[lo:offset]) + "<mark>" + _visible(cur_bytes[offset:offset + 2]) + "</mark>" + _visible(cur_bytes[offset + 2:offset + 48])
        body = (
            f"<div class='diffrow'><span class='difftag'>prev</span><pre>{prev_win}</pre></div>"
            f"<div class='diffrow'><span class='difftag'>curr</span><pre>{cur_win}</pre></div>"
        )
    return f"<div class='panel' id='panel-{_esc(div['id'])}' hidden><div class='phead'>{header}</div>{body}</div>"


def _heatmap(result: dict) -> str:
    """SVG: x = turns, y = breakpoint index; cells coloured by state; a miss is clickable."""
    bps = result.get("breakpoints", [])
    if not bps:
        return "<p class='muted'>No breakpoints captured yet.</p>"
    turns = list(dict.fromkeys(b["turn_id"] for b in bps))
    max_idx = max(b["index"] for b in bps)
    # divergence per turn (for click → byte-diff)
    div_by_turn = {d["turn_id"]: d["id"] for d in result.get("divergences", [])}
    cell, gap, left, top = 26, 2, 120, 24
    width = left + len(turns) * (cell + gap) + 20
    height = top + (max_idx + 1) * (cell + gap) + 20
    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='block-survival heatmap' class='heat'>",
        "<defs><pattern id='hatch' width='6' height='6' patternUnits='userSpaceOnUse' patternTransform='rotate(45)'>"
        "<rect width='6' height='6' fill='#e9e8e4'/><line x1='0' y1='0' x2='0' y2='6' stroke='#8a8985' stroke-width='2'/></pattern></defs>",
    ]
    for row in range(max_idx + 1):
        y = top + row * (cell + gap)
        parts.append(f"<text x='{left - 8}' y='{y + cell - 8}' class='ytick' text-anchor='end'>bp {row}</text>")
    for ci, turn in enumerate(turns):
        x = left + ci * (cell + gap)
        for b in [b for b in bps if b["turn_id"] == turn]:
            y = top + b["index"] * (cell + gap)
            state = b["state"]
            fill = "url(#hatch)" if state == "never_cached" else _STATE.get(state, ("#ccc", ""))[0]
            clickable = state == "recomputed" and turn in div_by_turn
            attrs = f" class='cell click' data-panel='panel-{_esc(div_by_turn[turn])}' tabindex='0'" if clickable else " class='cell'"
            title = f"{state}" + (" — click for the byte diff" if clickable else "")
            parts.append(f"<rect x='{x}' y='{y}' width='{cell}' height='{cell}' rx='4' fill='{fill}'{attrs}><title>{title}</title></rect>")
    parts.append("</svg>")
    return "".join(parts)


def _ledger(result: dict) -> str:
    """Horizontal bars of wasted spend by cause, headline flagged."""
    rollups = result.get("rollups", [])
    if not rollups:
        return "<p class='muted'>No avoidable waste attributed yet.</p>"
    by_cause: dict[str, float] = {}
    meter = "measured"
    for r in rollups:
        by_cause[r["cause"]] = by_cause.get(r["cause"], 0.0) + r["wasted_gbp"]
        if r["billing_model"] == "subscription":
            meter = "shadow-price"
    rows = sorted(by_cause.items(), key=lambda kv: -kv[1])
    top = max(v for _, v in rows) or 1.0
    bar_w, row_h = 360, 26
    out = [f"<p class='headline'>Headline: <b>{_esc(rows[0][0])}</b> £{rows[0][1]:.2f} ({meter})</p>",
           f"<svg viewBox='0 0 {bar_w + 220} {len(rows) * (row_h + 6) + 8}' class='bars' role='img' aria-label='waste by cause'>"]
    for i, (cause, val) in enumerate(rows):
        y = i * (row_h + 6) + 4
        w = max(2, int(bar_w * (val / top)))
        out.append(f"<text x='0' y='{y + row_h - 8}' class='blabel'>{_esc(cause)}</text>")
        out.append(f"<rect x='150' y='{y}' width='{w}' height='{row_h}' rx='4' fill='{_cause_color(cause)}'/>")
        out.append(f"<text x='{150 + w + 6}' y='{y + row_h - 8}' class='bval'>£{val:.2f}</text>")
    out.append("</svg>")
    out.append("<p class='muted'>Measured £ on pay-as-you-go; a subscription figure is a shadow-price counterfactual, not a bill. Excludes non-avoidable edits and never-cached prefixes.</p>")
    return "".join(out)


def _pred_vs_measured(result: dict) -> str:
    divs = result.get("divergences", [])
    if not divs:
        return "<p class='muted'>No divergences to reconcile.</p>"
    rows = ["<table class='pvm'><thead><tr><th>cause</th><th>predicted recompute (tokens)</th><th>measured</th><th>delta</th></tr></thead><tbody>"]
    for d in divs:
        rec = d.get("reconciliation") or {}
        agreement = rec.get("agreement", "no_measurement")
        if agreement != "no_measurement":
            measured = str(rec.get("measured_missed_tokens") if rec.get("measured_missed_tokens") is not None else rec.get("measured_read_drop"))
            delta = agreement
            flag = "" if agreement == "agree" else " class='flag'"
        else:
            measured, delta, flag = "no measurement", "—", ""
        rows.append(f"<tr{flag}><td>{_esc(d['cause'])}</td><td>{d['predicted_recomputed_tokens']}</td><td>{_esc(measured)}</td><td>{_esc(delta)}</td></tr>")
    rows.append("</tbody></table>")
    rows.append("<p class='muted'>Measured reconciliation arrives with the live proxy and the diagnostics beta; rows without it read \"no measurement\", never treated as agreement.</p>")
    return "".join(rows)


def _legend() -> str:
    items = []
    for key, (color, label) in _STATE.items():
        swatch = "background:url(#none)" if key == "never_cached" else f"background:{color}"
        cls = "sw hatch" if key == "never_cached" else "sw"
        items.append(f"<span class='legitem'><span class='{cls}' style='{swatch}'></span>{_esc(label)}</span>")
    return "<div class='legend'>" + "".join(items) + "</div>"


_CSS = """
:root{--surface:#fcfcfb;--ink:#0b0b0b;--muted:#52514e;--line:#e9e8e4;--accent:#2a78d6}
@media (prefers-color-scheme:dark){:root{--surface:#1a1a19;--ink:#fff;--muted:#c3c2b7;--line:#2f2f2c;--accent:#3987e5}}
*{box-sizing:border-box}body{margin:0;background:var(--surface);color:var(--ink);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;margin:0 0 2px}h2{font-size:15px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.sub{color:var(--muted);margin:0 0 8px}.muted{color:var(--muted);font-size:12px}
.headline{font-size:15px;margin:0 0 8px}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin:8px 0}.legitem{display:inline-flex;align-items:center;gap:6px;font-size:12px}
.sw{width:14px;height:14px;border-radius:3px;display:inline-block;border:1px solid var(--line)}
.hatch{background-image:repeating-linear-gradient(45deg,#8a8985 0 2px,#e9e8e4 2px 6px)!important}
svg{max-width:100%;height:auto}.ytick,.blabel{fill:var(--muted);font-size:11px}.bval{fill:var(--ink);font-size:11px}
.cell{stroke:var(--surface);stroke-width:2}.click{cursor:pointer}.click:hover,.click:focus{stroke:var(--ink);outline:none}
.panel{border:1px solid var(--line);border-radius:6px;padding:10px;margin:8px 0;background:var(--surface)}
.phead{font-size:12px;margin-bottom:6px}.diffrow{display:flex;gap:8px;align-items:flex-start}
.difftag{color:var(--muted);font-size:11px;width:32px;flex:none;padding-top:6px}
pre{margin:2px 0;padding:6px 8px;background:var(--line);border-radius:4px;overflow-x:auto;white-space:pre-wrap;word-break:break-all;font:12px ui-monospace,monospace}
mark{background:#eda100;color:#000;border-radius:2px}
table.pvm{border-collapse:collapse;width:100%;font-size:13px}.pvm th,.pvm td{text-align:left;border-bottom:1px solid var(--line);padding:4px 8px}
tr.flag td{background:rgba(236,131,90,.18)}
"""

_JS = """
document.addEventListener('click',e=>{const c=e.target.closest('.click');if(!c)return;toggle(c.dataset.panel)});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest('.click')){e.preventDefault();toggle(e.target.closest('.click').dataset.panel)}});
function toggle(id){const p=document.getElementById(id);if(p)p.hidden=!p.hidden}
"""


def export_html(result: dict, store: CacheStore | None = None, theme: str = "neutral") -> str:
    """Render a CacheScopeResult (as a dict) to a self-contained HTML document."""
    pricing = result.get("pricing", {})
    stamp = f"pricing {pricing.get('pricing_version','?')} (eff {pricing.get('effective_date','?')}, fx {pricing.get('fx_date','?')})"
    hashes = _prefix_hash_by_turn(store) if store is not None else {}
    panels = "".join(_byte_diff_panel(d, store, hashes) for d in result.get("divergences", []))
    accent = "#0f766e" if theme == "fortitude" else "#2a78d6"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CacheScope report</title><style>{_CSS}\n:root{{--accent:{accent}}}</style></head>
<body data-theme="{_esc(theme)}"><div class="wrap">
<h1>CacheScope report</h1><p class="sub">{_esc(stamp)} · predictions confirmed by measurement where available</p>
<h2>Block survival</h2><p class="muted">Rows are cache breakpoints, columns are turns. A recomputed cell is a miss — click it for the byte that did it. Never-cached (below the model minimum) is hatched and carries no waste.</p>
{_legend()}{_heatmap(result)}{panels}
<h2>Cost ledger</h2>{_ledger(result)}
<h2>Prediction versus measured</h2>{_pred_vs_measured(result)}
</div><script>{_JS}</script></body></html>"""
