#!/usr/bin/env python3
"""
Prose Weight Visualiser — two prompts enter, one browser tab shows where the model looks.

A minimal graphical front-end for prompt-token attention visualisation.
Enter two adversarial prompts (e.g. vivid vs beige directive), pick a local
open-weights model, and see each prompt rendered as a token heatmap:
warmer background = more attention received from the generated tokens.

Run:  python prose_weight_visualiser.py   then open http://127.0.0.1:7860
Deps: pip install torch transformers gradio accelerate

Caveat rendered in the UI, repeated here: attention shows where the model
LOOKS, not what it OBEYS. Behavioural influence is measured by A/B output
testing (promptfoo), not by staring at attention. This is the anatomy demo.
"""

import html

import torch
import gradio as gr

MODELS = [
    "Qwen/Qwen2.5-0.5B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "meta-llama/Llama-3.2-1B-Instruct",
    "gpt2",
]

_cache: dict = {}


def get_model(model_id: str):
    if model_id not in _cache:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        # bfloat16 (not float16) on GPU: Qwen2.5's large attention logits
        # overflow fp16's range and softmax them into NaN, corrupting the whole
        # forward pass. bf16 has fp32's exponent range, so no overflow.
        if device == "cuda":
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float32
        else:
            dtype = torch.float32
        tok = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(
            model_id, dtype=dtype, attn_implementation="eager"
        ).to(device)
        model.eval()
        _cache.clear()  # one model in memory at a time; 10GB is 10GB
        _cache[model_id] = (tok, model, device)
    return _cache[model_id]


@torch.no_grad()
def ablation_scores(model, full_ids, n_prompt, content_positions):
    """Causal influence per prompt token, by intervention rather than attention.
    For each content token: knock it out (attention_mask=0 → nothing can attend to
    it), re-run over prompt+completion, and measure how much the model's next-token
    distribution over the *generated* continuation shifts vs. the un-ablated baseline
    (mean KL across generated positions). Bigger = removing the word actually moved
    the output — i.e. what the model obeys, not merely where it looks."""
    length = full_ids.shape[1]
    n_gen = length - n_prompt
    scores = torch.zeros(n_prompt, dtype=torch.float32)
    if n_gen < 1 or not content_positions:
        return scores
    device = full_ids.device
    pids = torch.arange(length, device=device).unsqueeze(0)   # fixed positions
    pos = torch.arange(n_prompt - 1, length - 1, device=device)  # predict gen tokens
    base_lp = torch.log_softmax(
        model(full_ids, position_ids=pids).logits[0][pos].float(), dim=-1)
    base_p = base_lp.exp()
    ones = torch.ones_like(full_ids)
    for j in content_positions:
        m = ones.clone()
        m[0, j] = 0                                           # mask out token j
        abl_lp = torch.log_softmax(
            model(full_ids, attention_mask=m, position_ids=pids)
            .logits[0][pos].float(), dim=-1)
        kl = (base_p * (base_lp - abl_lp)).sum(-1).mean()     # KL(base || ablated)
        scores[j] = max(kl.item(), 0.0)
    return scores


@torch.no_grad()
def analyze(model_id: str, prompt: str, use_chat: bool, max_new: int):
    tok, model, device = get_model(model_id)

    # `span` marks the char range of the user's own prompt inside the templated
    # input, so the fight can be scored on content tokens only (not the system
    # preamble, role markers, or <|im_*|> scaffolding around it).
    offsets = span = None
    if use_chat and tok.chat_template:
        templated = tok.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True, tokenize=False,
        )
        enc = tok(templated, return_tensors="pt", add_special_tokens=False,
                  return_offsets_mapping=tok.is_fast)
        input_ids = enc["input_ids"].to(device)
        if tok.is_fast:
            offsets = enc["offset_mapping"][0].tolist()
            start = templated.rfind(prompt)  # last copy = the user turn
            if start != -1:
                span = (start, start + len(prompt))
    else:
        input_ids = tok(prompt, return_tensors="pt").input_ids.to(device)

    n_prompt = input_ids.shape[1]
    out = model.generate(
        input_ids, max_new_tokens=int(max_new), do_sample=False,
        output_attentions=True, return_dict_in_generate=True,
        pad_token_id=tok.eos_token_id,
    )

    step_vecs = []
    for step_attn in out.attentions[1:]:  # generated tokens looking back
        per_layer = torch.stack(
            [a[0, :, -1, :n_prompt].mean(dim=0).float().cpu() for a in step_attn]
        )
        step_vecs.append(per_layer.mean(dim=0))  # one vector per generation step
    # (steps, n_prompt): per-step attention, kept so the dots view can animate
    # the running build-up. Aggregate score = mean over steps (as before).
    step_scores = (torch.stack(step_vecs) if step_vecs
                   else torch.zeros(1, n_prompt, dtype=torch.float32))
    scores = step_scores.mean(dim=0)

    ids = input_ids[0].tolist()
    tokens = tok.convert_ids_to_tokens(input_ids[0])
    specials = set(tok.all_special_ids)
    # A token is "content" if it carries text, isn't a special token, and (in
    # chat mode) falls inside the user's prompt span. Everything else — the
    # attention-sink first token, role/section scaffolding, structural newlines —
    # is excluded from scoring so the duel reflects the prompts, not the wrapper.
    is_content = []
    for i, (tid, t) in enumerate(zip(ids, tokens)):
        has_text = clean(t).strip() != ""
        if span and offsets is not None:
            s, e = offsets[i]
            in_span = e > s and s >= span[0] and e <= span[1]
            is_content.append(has_text and tid not in specials and in_span)
        else:
            is_content.append(has_text and tid not in specials and i != 0)

    completion = tok.decode(out.sequences[0, n_prompt:], skip_special_tokens=True)
    content_positions = [i for i, c in enumerate(is_content) if c]
    causal = ablation_scores(model, out.sequences, n_prompt, content_positions)
    return tokens, scores, completion, is_content, step_scores, causal


# ── Visual theme: colours, fonts, layout ─────────────────────────────────────
BRAND, BRAND_MID, BRAND_LIGHT = "#155263", "#1a6b80", "#2a9db8"
BRAND_900, BRAND_800, BRAND_50 = "#082830", "#0f3d4a", "#edf8fb"
INK, BODY, MUTED, BORDER = "#0f172a", "#475569", "#64748b", "#e2e8f0"
HEAT_RGB = "42,157,184"   # brand-light; used with alpha for the attention heat
SANS = "'Inter', system-ui, sans-serif"
CARD = (f"background:#fff; border:1px solid {BORDER}; border-radius:16px; "
        f"padding:20px; box-shadow:0 1px 2px rgba(15,23,42,.04), "
        f"0 8px 24px rgba(15,23,42,.06); font-family:{SANS}; color:{INK};")
GUARD = (
    f'<div style="font-family:{SANS}; color:#b91c1c; background:#fef2f2; '
    f'border:1px solid #fecaca; padding:16px; border-radius:16px;">Attention came '
    'back non-finite (NaN/Inf): the model was numerically unstable in this precision '
    '(typically fp16 overflow). Try a bf16-capable GPU or another model.</div>'
)


def clean(token: str) -> str:
    return (token.replace("Ġ", " ").replace("▁", " ")
                 .replace("Ċ", "\n").replace("Ā", ""))


def show_ws(token: str) -> str:
    """Cleaned token with whitespace made visible, for table cells that would
    otherwise collapse to nothing (Gradio's .prose wrapper shrink-wraps them)."""
    return clean(token).replace(" ", "·").replace("\n", "⏎") or "∅"


def heat_text(token: str) -> str:
    """Token for the heatmap strip: normal tokens read as prose, but a
    whitespace-only token (a lone space or newline) gets a visible glyph so a
    hot, otherwise-blank token isn't an invisible gap."""
    c = clean(token)
    if not c.strip():
        c = c.replace(" ", "·").replace("\t", "·")
    return html.escape(c).replace("\n", "⏎<br>")


def heat_css(ratio: float) -> str:
    """0..1+ ratio-vs-mean → brand-teal wash. 1.0 = average attention.
    Alpha caps at .9 so slate ink stays legible on the hottest tokens."""
    alpha = min(0.9, max(0.0, (ratio - 0.4) / 3.0))
    return f"background: rgba({HEAT_RGB},{alpha:.2f});"


def _heat_card(tokens, scores, is_content, completion, rank_title, note="") -> str:
    # Guard: surface numerical breakdown honestly rather than rendering NaN cells
    # (masking it would fabricate a signal from a corrupted forward pass).
    if not torch.isfinite(scores).all():
        return GUARD
    content_idx = [i for i, c in enumerate(is_content) if c]
    if not content_idx:
        return "<em>no content tokens found in this prompt</em>"

    # Normalise against the mean of content tokens only, so structural sinks
    # (role markers, boundary newlines, the first-token sink) don't skew the scale.
    mean = scores[content_idx].mean().item() or 1e-9
    ratios = (scores / mean).tolist()

    spans = []
    for i, (t, r) in enumerate(zip(tokens, ratios)):
        text = heat_text(t)
        if is_content[i]:
            spans.append(
                f'<span title="{r:.2f}x mean" style="{heat_css(r)}'
                f'padding:2px 1px; border-radius:4px;">{text}</span>'
            )
        else:
            # scaffolding / sink: shown dimmed for context, excluded from the fight
            spans.append(
                f'<span title="scaffolding (excluded)" '
                f'style="opacity:.3;">{text}</span>'
            )

    ranked = sorted(((tokens[i], ratios[i]) for i in content_idx),
                    key=lambda x: -x[1])[:8]
    td = "padding:2px 12px 2px 0; white-space:nowrap; border:none;"
    rows = "".join(
        f"<tr><td style='{td}'>"
        f"<code style='background:{BRAND_50}; color:{BRAND}; padding:1px 6px; "
        f"border-radius:5px; font-size:.9em;'>{html.escape(show_ws(t))}</code></td>"
        f"<td style='text-align:right; white-space:nowrap; border:none; "
        f"color:{BODY}; font-variant-numeric:tabular-nums;'>{r:.2f}&times;</td></tr>"
        for t, r in ranked
    )
    note_html = (f'<div style="font-size:.82em; color:{MUTED}; margin-top:10px; '
                 f'line-height:1.5;">{note}</div>') if note else ""

    return f"""
    <div style="{CARD} line-height:1.9;">
      <div style="font-size:1.02em;">{''.join(spans)}</div>
      {note_html}
      <hr style="border:none; border-top:1px solid {BORDER}; margin:14px 0;">
      <details open>
        <summary style="cursor:pointer; color:{MUTED}; font-weight:600;
                        font-size:.85em;">{rank_title}</summary>
        <table style="margin-top:8px; font-size:.9em; width:auto;
                      border-collapse:collapse;">{rows}</table>
      </details>
      <details>
        <summary style="cursor:pointer; color:{MUTED}; font-weight:600;
                        font-size:.85em; margin-top:8px;">model output</summary>
        <pre style="white-space:pre-wrap; font-size:.85em; color:{BODY};
                    margin-top:6px;">{html.escape(completion)}</pre>
      </details>
    </div>
    """


def render_html(tokens, scores, completion, is_content) -> str:
    return _heat_card(tokens, scores, is_content, completion, "most-attended tokens")


def render_causal(tokens, causal, completion, is_content) -> str:
    return _heat_card(
        tokens, causal, is_content, completion, "most-influential tokens",
        note="Each content word is masked in turn and the model re-run; the shade "
             "shows how much its output distribution shifts without that word (mean "
             "KL). This is a real intervention — closer to <em>what the model "
             "obeys</em> than where it merely looks.")


def _cumulative_frames(step_scores, max_frames: int = 40):
    """Running mean over generation steps → the build-up the dots animate.
    Frame k = mean attention over steps 0..k; the last frame equals the
    aggregate score. Down-sampled to keep the SVG small."""
    s = step_scores.shape[0]
    cum_mean = torch.cumsum(step_scores, dim=0) / torch.arange(
        1, s + 1, dtype=torch.float32).unsqueeze(1)
    if s > max_frames:
        idx = torch.linspace(0, s - 1, max_frames).round().long()
        cum_mean = cum_mean[idx]
    return cum_mean  # (frames, n_prompt)


DOT_DUR = "5s"          # one full build-up pass
DOT_ITER = "1"          # play once when the tab opens, then freeze on the final frame
SVG_W, MAXR, PAD, FONT = 640, 26, 12, 12
ROW_H = 2 * MAXR + FONT + 16


def render_dots(tokens, scores, completion, is_content, step_scores) -> str:
    if not torch.isfinite(scores).all():
        return GUARD
    content_idx = [i for i, c in enumerate(is_content) if c]
    if not content_idx:
        return "<em>no content tokens found in this prompt</em>"

    content_mean = scores[content_idx].mean().item() or 1e-9
    frames = _cumulative_frames(step_scores) / content_mean   # ratios per frame
    final_ratio = scores / content_mean
    rcap = max(final_ratio[content_idx].max().item(), 1e-9)   # biggest dot = MAXR

    # flow layout: circles left→right, wrapping like prose
    x, row, placed = PAD, 0, []
    for i in content_idx:
        label = show_ws(tokens[i])
        cellw = max(2 * MAXR + 8, len(label) * 7 + 12)
        if x + cellw > SVG_W - PAD and x > PAD:
            row, x = row + 1, PAD
        placed.append((i, label, x, row, cellw))
        x += cellw
    height = PAD + (row + 1) * ROW_H + 14

    # unique id so A's and B's keyframes/anim don't collide on the same page
    uid = "d" + format(abs(hash((tuple(tokens), completion))) % (1 << 32), "x")

    keyframes, nodes = [], []
    n_frames = frames.shape[0]
    for k, (i, label, cell_x, r, cellw) in enumerate(placed):
        cx = cell_x + cellw / 2
        cy = PAD + r * ROW_H + MAXR
        # Circles are drawn at MAXR and CSS-scaled per frame (scale = radius/MAXR),
        # so the build-up is a transform animation — robust to Gradio's hidden-tab
        # innerHTML insertion (CSS restarts on display:none→block; SMIL doesn't).
        stops = ["0%{transform:scale(0);fill-opacity:0}"]
        for f in range(n_frames):
            ratio = max(frames[f, i].item(), 0.0)
            scale = (min(ratio, rcap) / rcap) ** 0.5
            op = min(1.0, max(0.0, (ratio - 0.4) / 3.0))
            pct = (f + 1) / n_frames * 100
            stops.append(f"{pct:.1f}%{{transform:scale({scale:.3f});fill-opacity:{op:.2f}}}")
        name = f"{uid}_{k}"
        keyframes.append(f"@keyframes {name}{{{''.join(stops)}}}")
        anim = f"{name} {DOT_DUR} linear {DOT_ITER} forwards"
        tip = html.escape(
            f"{label}: ×{final_ratio[i].item():.2f} vs content mean "
            f"· {scores[i].item() * 100:.2f}% of attention"
        )
        # data-anim mirrors the animation so JS can restart it when the tab is
        # (re)opened — Gradio doesn't reliably re-trigger CSS anims on tab switch.
        nodes.append(
            f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{MAXR}" fill="{BRAND}" '
            f'data-anim="{anim}" '
            f'style="transform-box:fill-box; transform-origin:center; fill-opacity:0; '
            f'animation:{anim};"><title>{tip}</title></circle>'
            f'<text x="{cx:.0f}" y="{cy + MAXR + FONT:.0f}" text-anchor="middle" '
            f'font-size="{FONT}" fill="{BODY}" font-family="Inter,system-ui,sans-serif">'
            f'{html.escape(label)}</text>'
        )

    bar_w = SVG_W - 2 * PAD
    keyframes.append(f"@keyframes {uid}_bar{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}")
    bar_anim = f"{uid}_bar {DOT_DUR} linear {DOT_ITER} forwards"
    bar = (
        f'<rect x="{PAD}" y="{height - 9}" width="{bar_w}" height="3" rx="1.5" fill="{BORDER}"/>'
        f'<rect x="{PAD}" y="{height - 9}" width="{bar_w}" height="3" rx="1.5" fill="{BRAND}" '
        f'data-anim="{bar_anim}" '
        f'style="transform-box:fill-box; transform-origin:left; animation:{bar_anim};"/>'
    )
    svg = (
        f'<style>{"".join(keyframes)}</style>'
        f'<svg viewBox="0 0 {SVG_W} {height}" width="100%" '
        f'style="max-width:{SVG_W}px;" xmlns="http://www.w3.org/2000/svg">'
        f'{"".join(nodes)}{bar}</svg>'
    )
    return (
        f'<div style="{CARD}">{svg}'
        f'<details style="color:{MUTED}; margin-top:10px;">'
        f'<summary style="cursor:pointer; font-weight:600; font-size:.85em;">'
        f'model output</summary>'
        f'<pre style="white-space:pre-wrap; font-size:.85em; color:{BODY}; '
        f'margin-top:6px;">{html.escape(completion)}</pre></details></div>'
    )


def prompt_stats(scores, is_content):
    """Cross-prompt-comparable numbers for the scoreboard. `share` = the % of
    the model's attention that landed on this prompt's content tokens (raw, not
    per-prompt-normalised, so A and B are comparable). `per_tok` divides that by
    the token count to isolate per-word intensity from sheer length."""
    idx = [i for i, c in enumerate(is_content) if c]
    if not idx or not torch.isfinite(scores).all():
        return None
    share = 100.0 * scores[idx].sum().item()
    return {"share": share, "per_tok": share / len(idx), "n": len(idx)}


def render_scoreboard(a, b):
    if not (a and b):          # need both prompts scored to compare
        return ""
    winner = ("A" if a["share"] > b["share"]
              else "B" if b["share"] > a["share"] else None)

    def figure(label, share, side):
        won = winner == side
        lost = winner is not None and not won
        colour = BRAND if won else (MUTED if lost else INK)
        weight = 800 if won else 700
        opacity = ".55" if lost else "1"
        trophy = ' <span style="font-size:1.6rem;">🏆</span>' if won else ""
        return (
            f'<div style="opacity:{opacity}; min-width:150px;">'
            f'<div style="font-size:.72rem; font-weight:600; text-transform:uppercase; '
            f'letter-spacing:.12em; color:{MUTED}; margin-bottom:8px;">{label}</div>'
            f'<div style="font-size:3.2rem; font-weight:{weight}; color:{colour}; '
            f'line-height:1; font-variant-numeric:tabular-nums;">'
            f'{share:.1f}%{trophy}</div></div>'
        )

    return (
        '<div style="text-align:center;">'
        f'<div style="{CARD} display:inline-block; padding:24px 40px; text-align:center;">'
        '<div style="font-size:.72rem; font-weight:600; text-transform:uppercase; '
        f'letter-spacing:.15em; color:{BRAND}; margin-bottom:18px;">'
        'attention scoreboard</div>'
        '<div style="display:flex; align-items:center; justify-content:center; gap:36px;">'
        f'{figure("A (vivid)", a["share"], "A")}'
        f'<div style="font-size:1rem; font-weight:600; color:{MUTED};">vs</div>'
        f'{figure("B (beige)", b["share"], "B")}'
        '</div>'
        f'<div style="font-size:.8em; color:{MUTED}; margin-top:18px; max-width:46ch;">'
        'content attention share — how much of the model’s gaze each prompt held. '
        'Where it <em>looked</em>, not what it <em>obeyed</em>.'
        '</div></div></div>'
    )


def duel(model_id, prompt_a, prompt_b, use_chat, max_new,
         progress=gr.Progress()):
    # clear last run's output first, so the progress indicator sits over empty
    # space instead of overlaying stale results (and drops any old dots SVGs)
    yield "", "", "", "", "", "", ""
    texts, dots, causal, stats = {}, {}, {}, {}
    for label, prompt in (("A", prompt_a), ("B", prompt_b)):
        if not prompt.strip():
            texts[label] = dots[label] = causal[label] = "<em>empty prompt</em>"
            stats[label] = None
            continue
        progress(0.1 if label == "A" else 0.6, desc=f"running prompt {label}...")
        tokens, scores, completion, is_content, step_scores, cscores = analyze(
            model_id, prompt, use_chat, max_new)
        # attention views + causal ablation all come from the one loaded model
        texts[label] = render_html(tokens, scores, completion, is_content)
        dots[label] = render_dots(tokens, scores, completion, is_content, step_scores)
        causal[label] = render_causal(tokens, cscores, completion, is_content)
        stats[label] = prompt_stats(scores, is_content)
    board = render_scoreboard(stats["A"], stats["B"])
    yield (board, texts["A"], texts["B"], dots["A"], dots["B"],
           causal["A"], causal["B"])


DEFAULT_A = ("BOIL THE OCEAN. Every function, every edge case, every test. "
             "Nothing deferred, nothing stubbed. Write a slugify function with tests.")
DEFAULT_B = ("Please aim for completeness. Write a slugify function with tests.")

APP_THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.cyan,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
).set(
    body_background_fill="#f8fafc",
    body_text_color=INK,
    block_border_color=BORDER,
    block_label_text_color=MUTED,
    input_border_color=BORDER,
    button_primary_background_fill=BRAND,
    button_primary_background_fill_hover=BRAND_MID,
    button_primary_text_color="#ffffff",
    button_primary_border_color=BRAND,
)

APP_CSS = f"""
/* fixed width so the page doesn't grow when results appear — always the
   width of the full results layout (capped to the viewport on small screens) */
.gradio-container {{ width: 1180px !important; max-width: 100% !important;
  margin: 0 auto !important; background: #f8fafc !important;
  font-family: {SANS} !important; }}
.gradio-container p, .gradio-container label, .gradio-container span,
.gradio-container button, .gradio-container input, .gradio-container textarea
  {{ font-family: {SANS}; }}

#pwv-hero {{ position: relative; overflow: hidden; border: none !important;
  border-radius: 20px !important; padding: 44px 40px !important; margin: 6px 0 12px;
  background: linear-gradient(135deg, {BRAND_900} 0%, {BRAND_800} 55%, #0f172a 100%) !important; }}
#pwv-hero .dotgrid {{ position: absolute; inset: 0; pointer-events: none;
  background-image: radial-gradient(circle, rgba(79,188,217,.18) 1px, transparent 1px);
  background-size: 24px 24px;
  -webkit-mask-image: radial-gradient(ellipse 70% 60% at 50% 40%, #000 30%, transparent 75%);
          mask-image: radial-gradient(ellipse 70% 60% at 50% 40%, #000 30%, transparent 75%); }}
#pwv-hero .inner {{ position: relative; }}
#pwv-hero h1 {{ color: #fff; font-size: 2.6rem; font-weight: 800;
  letter-spacing: -.02em; margin: .5rem 0 .6rem; line-height: 1.05; }}
#pwv-hero .grad-text {{ background: linear-gradient(115deg, #4fbcd9, #8dd4e9, #c5eaf5);
  -webkit-background-clip: text; background-clip: text; color: transparent; }}
#pwv-hero .eyebrow {{ display: inline-flex; align-items: center; gap: .5rem;
  font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .15em;
  color: #8dd4e9; background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.15);
  padding: .35rem .85rem; border-radius: 999px; }}
#pwv-hero .eyebrow .d {{ width: 6px; height: 6px; border-radius: 999px; background: {BRAND_LIGHT}; }}
#pwv-hero .sub {{ color: rgba(197,234,245,.82); font-size: 1.02rem; line-height: 1.6;
  max-width: 64ch; margin: .1rem 0 .7rem; }}
#pwv-hero .caveat {{ color: rgba(141,212,233,.72); font-size: .85rem; font-style: italic; margin: 0; }}

#fight-btn, #fight-btn button {{ border-radius: 12px !important; font-weight: 600 !important;
  transition: transform .18s ease, box-shadow .18s ease !important; }}
#fight-btn:hover, #fight-btn button:hover {{ transform: translateY(-2px);
  box-shadow: 0 12px 26px rgba(21,82,99,.28) !important; }}
#fight-btn:active, #fight-btn button:active {{ transform: translateY(1px) scale(.994); }}

.tab-nav button.selected {{ color: {BRAND} !important; border-bottom-color: {BRAND} !important; }}
:focus-visible {{ outline: 2px solid {BRAND_LIGHT} !important; outline-offset: 3px; border-radius: 4px; }}
"""

HERO_HTML = (
    '<div class="dotgrid"></div><div class="inner">'
    '<span class="eyebrow"><span class="d"></span>Prompt attention · research tool</span>'
    '<h1>Prose Weight <span class="grad-text">Visualiser</span></h1>'
    '<p class="sub">Two prompts compete. Warmer highlight = more attention received '
    "from the model's generated tokens (mean over layers, heads, steps). Chat "
    'scaffolding is dimmed and excluded — the fight is scored on your prompt\'s '
    'content tokens only.</p>'
    '<p class="caveat">Attention shows where the model looks, not what it obeys.</p>'
    '</div>'
)

with gr.Blocks(title="Prose Weight Visualiser", theme=APP_THEME,
               css=APP_CSS) as app:
    gr.HTML(HERO_HTML, elem_id="pwv-hero")
    with gr.Row():
        model_dd = gr.Dropdown(MODELS, value=MODELS[0], label="model",
                               allow_custom_value=True)
        chat_cb = gr.Checkbox(value=True, label="use chat template")
        max_new = gr.Slider(10, 120, value=50, step=10, label="tokens to generate")
    with gr.Row():
        prompt_a = gr.Textbox(value=DEFAULT_A, label="prompt A (vivid)", lines=4)
        prompt_b = gr.Textbox(value=DEFAULT_B, label="prompt B (beige)", lines=4)
    run_btn = gr.Button("Fight", variant="primary", elem_id="fight-btn")
    scoreboard = gr.HTML()
    with gr.Tabs():
        with gr.Tab("Text heatmap"):
            with gr.Row():
                text_a = gr.HTML(label="A")
                text_b = gr.HTML(label="B")
        with gr.Tab("Attention dots") as dots_tab:
            gr.Markdown("*Dots grow as each generated token is processed; area "
                        "= attention received; hover a dot for its value. The "
                        "build-up replays each time you open this tab.*")
            with gr.Row():
                dots_a = gr.HTML(label="A")
                dots_b = gr.HTML(label="B")
        with gr.Tab("Causal influence"):
            gr.Markdown("*Ablation, not attention: each content word is masked and "
                        "the model re-run — the shade shows how much the output "
                        "shifts without it (mean KL). Where the prompt actually "
                        "moves the model, vs. where it merely looks. (Adds one "
                        "forward pass per word, so it's slower than the tabs above.)*")
            with gr.Row():
                causal_a = gr.HTML(label="A")
                causal_b = gr.HTML(label="B")

    # Restart the CSS build-up: none → force reflow → reapply. Fixes SVG anims not
    # re-triggering when Gradio reveals a previously-hidden tab.
    RESTART_JS = """() => {
      document.querySelectorAll('[data-anim]').forEach(el => {
        const a = el.getAttribute('data-anim');
        el.style.animation = 'none';
        el.getBoundingClientRect();
        el.style.animation = a;
      });
    }"""
    run_btn.click(duel, [model_dd, prompt_a, prompt_b, chat_cb, max_new],
                  [scoreboard, text_a, text_b, dots_a, dots_b, causal_a, causal_b]
                  ).then(None, None, None, js=RESTART_JS)
    dots_tab.select(None, None, None, js=RESTART_JS)

if __name__ == "__main__":
    app.launch()
