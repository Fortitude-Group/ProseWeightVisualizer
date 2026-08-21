"""Interactive web app: paste a prompt, measure instruction weights, see the verdict.

A small FastAPI app that wires the Ollama measurement backend to the browser and
renders the branded verdict report. A real scan takes a few minutes (the deep
audit runs many model calls), so the defaults are modest and the form warns about
the wait. Run with ``proseweight web`` (or ``uvicorn proseweight.web.app:app``).
"""

from __future__ import annotations

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from proseweight.config import RunConfig
from proseweight.probes.suite import load_suite
from proseweight.report.brand import lion_data_uri
from proseweight.report.render import render_verdict_html
from proseweight.segmentation.pipeline import segment_prompt
from proseweight.verdict.orchestrator import run_verdict

SUBJECT = "qwen3.5:2b"
JUDGE = "qwen2.5:7b-instruct"
EMBED = "nomic-embed-text"

_SUITE_PATH = None  # resolved lazily

SAMPLE_PROMPT = (
    "Return every answer as strict JSON only, with no prose.\n"
    "Never give a specific medication dosage; tell the user to consult a professional.\n"
    "Attempt the task directly and completely; never ask clarifying questions.\n"
    "Be genuinely helpful and thorough in everything you produce.\n"
)


FRONTIER_SUBJECT = "claude-opus-4-8"


def _suite_path():
    from pathlib import Path

    return Path(__file__).resolve().parents[3] / "data" / "suites" / "default-v1.yaml"


def _ollama_models() -> list[str]:
    """Names of the models Ollama has pulled, for the selectors. Falls back to defaults."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        names = sorted(m["name"] for m in data.get("models", []) if "embed" not in m["name"])
        return names or [SUBJECT, JUDGE]
    except Exception:
        return [SUBJECT, JUDGE]


def _select(name: str, options: list[str], selected: str) -> str:
    opts = "".join(
        f'<option{" selected" if o == selected else ""}>{o}</option>' for o in options
    )
    return f'<select name="{name}">{opts}</select>'


# A sticky top bar injected into result pages so there's always a way back.
_APP_BAR = (
    '<div style="background:#0b2e37;color:#dff0f2;padding:9px 20px;display:flex;align-items:center;'
    'gap:16px;font-family:ui-monospace,Consolas,monospace;font-size:.72rem;letter-spacing:.06em;'
    'text-transform:uppercase;position:sticky;top:0;z-index:60;">'
    '<span style="opacity:.65;">Prose Weight Visualiser</span>'
    '<a href="/" style="color:#fff;text-decoration:none;">&larr; New scan</a>'
    '<a href="/duel" style="color:#a9d2da;text-decoration:none;">Duel</a></div>'
)


def _with_nav(html: str) -> str:
    return html.replace("<body>", "<body>" + _APP_BAR, 1)


def _subject_backend(subject: str, judge: str, n: int):
    """Pick the measurement backend from the chosen subject model."""
    if subject.startswith("claude"):
        from proseweight.engine.anthropic_backend import AnthropicSubjectBackend

        return AnthropicSubjectBackend(subject, judge, EMBED, seed=42, n_samples=n, temperature=0.7)
    from proseweight.engine.ollama_backend import OllamaMeasurementBackend

    return OllamaMeasurementBackend(subject, judge, EMBED, seed=42, n_samples=n, temperature=0.7)


def _duel_backend(subject: str, judge: str, n: int):
    if subject.startswith("claude"):
        from proseweight.engine.anthropic_backend import AnthropicDuelBackend

        return AnthropicDuelBackend(subject, judge, EMBED, seed=42, n_samples=n, temperature=0.7)
    from proseweight.engine.ollama_backend import OllamaDuelBackend

    return OllamaDuelBackend(subject, judge, EMBED, seed=42, n_samples=n, temperature=0.7)


def _landing(prompt: str = SAMPLE_PROMPT) -> str:
    logo = lion_data_uri()
    tile = (
        f'<span class="logotile"><img src="{logo}" alt="Fortitude Omnis Group"></span>'
        if logo else ""
    )
    local = _ollama_models()
    subject_sel = _select("subject", local + [FRONTIER_SUBJECT], SUBJECT)
    judge_sel = _select("judge", local, JUDGE)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Prose Weight</title>
<style>
:root{{--ink:#0e1f1e;--muted:#5b6f71;--faint:#8aa0a1;--panel:#eef3f2;--card:#fff;--line:#d3e0df;
--teal:#155263;--mono:ui-monospace,"Cascadia Code",Consolas,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--panel);color:var(--ink);font-family:var(--sans);}}
.wrap{{max-width:820px;margin:0 auto;padding:0 20px 60px;}}
header{{background:var(--teal);color:#dff0f2;margin:0 -20px;padding:13px 20px;display:flex;align-items:center;gap:12px;justify-content:space-between;}}
.hl{{display:flex;align-items:center;gap:12px}}
.logotile{{width:40px;height:40px;border-radius:7px;background:#eef4f3;display:flex;align-items:center;justify-content:center;}}
.logotile img{{width:30px;height:30px;display:block}}
.bt{{display:flex;flex-direction:column;line-height:1.08}}
.bt b{{font-weight:700;font-size:.94rem;letter-spacing:.055em;text-transform:uppercase;color:#fff}}
.bt i{{font-family:var(--mono);font-style:normal;font-size:.6rem;letter-spacing:.15em;text-transform:uppercase;color:#a9d2da;margin-top:2px}}
.nav{{display:flex;gap:4px;font-family:var(--mono);font-size:.72rem;letter-spacing:.08em;text-transform:uppercase}}
.nav a{{color:#a9d2da;text-decoration:none;padding:6px 12px;border-radius:3px}}
.nav a:hover{{color:#fff}}.nav a.on{{color:#fff;background:rgba(255,255,255,.12)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media (max-width:560px){{.two{{grid-template-columns:1fr}}}}
.panel{{background:var(--card);border:1px solid var(--line);border-top:none;padding:26px clamp(16px,4vw,40px) 32px;}}
h1{{font-size:1.35rem;margin:0 0 4px}}.lede{{color:var(--muted);margin:0 0 20px;max-width:60ch}}
label{{display:block;font-family:var(--mono);font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin:16px 0 6px}}
textarea{{width:100%;min-height:170px;font-family:var(--mono);font-size:.85rem;padding:12px;border:1px solid var(--line);border-radius:3px;resize:vertical;color:var(--ink)}}
.opts{{display:flex;gap:18px;flex-wrap:wrap;margin-top:6px}}
.opt{{display:flex;flex-direction:column}}.opt select,.opt input{{font-family:var(--mono);padding:6px 8px;border:1px solid var(--line);border-radius:3px}}
button{{margin-top:20px;background:var(--teal);color:#fff;border:0;border-radius:3px;padding:12px 22px;font-family:var(--mono);font-size:.8rem;letter-spacing:.06em;text-transform:uppercase;cursor:pointer}}
button:hover{{background:#0f3d49}}
.note{{margin-top:14px;color:var(--muted);font-size:.82rem}}
.spin{{display:none;margin-top:16px;font-family:var(--mono);font-size:.8rem;color:var(--teal)}}
form.busy .spin{{display:block}}form.busy button{{opacity:.5;pointer-events:none}}
</style></head><body><div class="wrap">
<header><span class="hl">{tile}<span class="bt"><b>Fortitude Omnis Group</b><i>Prose Weight · Readout</i></span></span>
<nav class="nav"><a class="on" href="/">Scan</a><a href="/duel">Duel</a></nav></header>
<section class="panel">
<h1>Measure what your prompt actually does</h1>
<p class="lede">Paste a system prompt or instruction list. Each line is ablated against a probe
suite on a local model; you get back which instructions carry behavioural weight, with a
credible interval on every score. Ablation-led, run locally via Ollama.</p>
<form method="post" action="/scan" onsubmit="this.classList.add('busy')">
<label>System prompt / instructions</label>
<textarea name="prompt">{prompt}</textarea>
<div class="opts">
<div class="opt"><label>Subject model</label>{subject_sel}</div>
<div class="opt"><label>Judge (local)</label>{judge_sel}</div>
<div class="opt"><label>Probes</label><select name="probes"><option>4</option><option>6</option><option>12</option></select></div>
<div class="opt"><label>Samples (N)</label><select name="n"><option>2</option><option>3</option><option>5</option></select></div>
<div class="opt"><label>Depth</label><select name="depth"><option value="deep_audit">deep audit</option><option value="quick_scan">quick scan</option></select></div>
</div>
<button type="submit">Measure weights</button>
<div class="spin">Measuring… ablating each instruction across the probe suite. This takes a few minutes; keep this tab open. A frontier subject ({FRONTIER_SUBJECT}) calls a paid API.</div>
</form>
<p class="note">Pick the subject to profile. The judge and embedder stay local, so only a frontier subject costs money. {FRONTIER_SUBJECT} needs ANTHROPIC_API_KEY in the environment.</p>
</section></div></body></html>"""


def _duel_landing(a: str = "BOIL THE OCEAN: do the complete, thorough job. Do not defer.",
                  b: str = "Please be thorough.") -> str:
    logo = lion_data_uri()
    tile = (f'<span class="logotile"><img src="{logo}" alt="Fortitude Omnis Group"></span>' if logo else "")
    local = _ollama_models()
    subject_sel = _select("subject", local + [FRONTIER_SUBJECT], SUBJECT)
    judge_sel = _select("judge", local, JUDGE)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Prose Weight · Duel</title>
<style>
:root{{--ink:#0e1f1e;--muted:#5b6f71;--faint:#8aa0a1;--panel:#eef3f2;--card:#fff;--line:#d3e0df;--teal:#155263;
--mono:ui-monospace,"Cascadia Code",Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--panel);color:var(--ink);font-family:var(--sans)}}
.wrap{{max-width:820px;margin:0 auto;padding:0 20px 60px}}
header{{background:var(--teal);color:#dff0f2;margin:0 -20px;padding:13px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px}}
.hl{{display:flex;align-items:center;gap:12px}}
.logotile{{width:40px;height:40px;border-radius:7px;background:#eef4f3;display:flex;align-items:center;justify-content:center}}
.logotile img{{width:30px;height:30px;display:block}}
.bt{{display:flex;flex-direction:column;line-height:1.08}}.bt b{{font-weight:700;font-size:.94rem;letter-spacing:.055em;text-transform:uppercase;color:#fff}}
.bt i{{font-family:var(--mono);font-style:normal;font-size:.6rem;letter-spacing:.15em;text-transform:uppercase;color:#a9d2da;margin-top:2px}}
.nav{{display:flex;gap:4px;font-family:var(--mono);font-size:.72rem;letter-spacing:.08em;text-transform:uppercase}}
.nav a{{color:#a9d2da;text-decoration:none;padding:6px 12px;border-radius:3px}}.nav a:hover{{color:#fff}}.nav a.on{{color:#fff;background:rgba(255,255,255,.12)}}
.panel{{background:var(--card);border:1px solid var(--line);border-top:none;padding:26px clamp(16px,4vw,40px) 32px}}
h1{{font-size:1.35rem;margin:0 0 4px}}.lede{{color:var(--muted);margin:0 0 20px;max-width:60ch}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}@media(max-width:560px){{.two{{grid-template-columns:1fr}}}}
label{{display:block;font-family:var(--mono);font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin:6px 0 6px}}
textarea{{width:100%;min-height:120px;font-family:var(--mono);font-size:.85rem;padding:12px;border:1px solid var(--line);border-radius:3px;resize:vertical;color:var(--ink)}}
.opts{{display:flex;gap:18px;flex-wrap:wrap;margin-top:12px}}.opt{{display:flex;flex-direction:column}}
.opt select{{font-family:var(--mono);padding:6px 8px;border:1px solid var(--line);border-radius:3px}}
button{{margin-top:20px;background:var(--teal);color:#fff;border:0;border-radius:3px;padding:12px 22px;font-family:var(--mono);font-size:.8rem;letter-spacing:.06em;text-transform:uppercase;cursor:pointer}}
button:hover{{background:#0f3d49}}.note{{margin-top:14px;color:var(--muted);font-size:.82rem}}
.spin{{display:none;margin-top:16px;font-family:var(--mono);font-size:.8rem;color:var(--teal)}}
form.busy .spin{{display:block}}form.busy button{{opacity:.5;pointer-events:none}}
</style></head><body><div class="wrap">
<header><span class="hl">{tile}<span class="bt"><b>Fortitude Omnis Group</b><i>Prose Weight · Duel</i></span></span>
<nav class="nav"><a href="/">Scan</a><a class="on" href="/duel">Duel</a></nav></header>
<section class="panel">
<h1>Which phrasing actually wins?</h1>
<p class="lede">Two phrasings of the same instruction, measured head to head across the probe suite.
The one the model complies with more wins, but only if the difference clears the region of
practical equivalence. Proof of what matters, not what you assume.</p>
<form method="post" action="/duel" onsubmit="this.classList.add('busy')">
<div class="two">
<div><label>Phrasing A</label><textarea name="phrasing_a">{a}</textarea></div>
<div><label>Phrasing B</label><textarea name="phrasing_b">{b}</textarea></div>
</div>
<div class="opts">
<div class="opt"><label>Subject model</label>{subject_sel}</div>
<div class="opt"><label>Judge (local)</label>{judge_sel}</div>
<div class="opt"><label>Probes</label><select name="probes"><option>4</option><option>6</option></select></div>
<div class="opt"><label>Samples (N)</label><select name="n"><option>3</option><option>5</option></select></div>
</div>
<button type="submit">Run the duel</button>
<div class="spin">Running the duel… measuring each phrasing across the probe suite. A few minutes; keep this tab open. A frontier subject ({FRONTIER_SUBJECT}) calls a paid API.</div>
</form>
<p class="note">The judge and embedder stay local, so only a frontier subject costs money.</p>
</section></div></body></html>"""


def create_app() -> FastAPI:
    app = FastAPI(title="Prose Weight Visualiser")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _landing()

    @app.post("/scan", response_class=HTMLResponse)
    def scan(
        prompt: str = Form(...),
        subject: str = Form(SUBJECT),
        judge: str = Form(JUDGE),
        probes: int = Form(4),
        n: int = Form(2),
        depth: str = Form("deep_audit"),
    ) -> str:
        suite = load_suite(_suite_path())
        suite.probes = suite.probes[: max(1, probes)]
        segments = segment_prompt(prompt)
        if not segments:
            return _landing(prompt)
        cfg = RunConfig(subject_model=subject, seed=42, depth=depth, posterior_samples=3000, n_runs=n)
        backend = _subject_backend(subject, judge, n)
        bundle = backend.measure(prompt, segments, suite, cfg)
        verdict = run_verdict(prompt, segments, suite, cfg, bundle, run_id="web")
        return _with_nav(render_verdict_html(verdict, brand=True))

    @app.get("/duel", response_class=HTMLResponse)
    def duel_page() -> str:
        return _duel_landing()

    @app.post("/duel", response_class=HTMLResponse)
    def duel(
        phrasing_a: str = Form(...),
        phrasing_b: str = Form(...),
        subject: str = Form(SUBJECT),
        judge: str = Form(JUDGE),
        probes: int = Form(4),
        n: int = Form(3),
    ) -> str:
        from proseweight.duel.duel import run_duel
        from proseweight.report.duel_render import render_duel_html

        suite = load_suite(_suite_path())
        suite.probes = suite.probes[: max(1, probes)]
        cfg = RunConfig(subject_model=subject, seed=42, posterior_samples=3000, n_runs=n)
        backend = _duel_backend(subject, judge, n)
        outcome = run_duel(phrasing_a, phrasing_b, backend, suite, cfg)
        return _with_nav(render_duel_html(
            outcome, phrasing_a, phrasing_b, suite_version=suite.version, model=subject, brand=True
        ))

    return app


app = create_app()
