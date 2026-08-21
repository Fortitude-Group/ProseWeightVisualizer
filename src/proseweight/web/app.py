"""Interactive web app: paste a prompt, measure instruction weights, see the verdict.

A small FastAPI app that wires the measurement backend to the browser and renders
the branded verdict report. The Scan and Duel input pages are the instrument's
control panel: header and form live inside one cohesive faceplate card so they
share a width, with the run settings grouped as labelled controls. A real scan
takes a few minutes; the forms warn about the wait. Run with ``proseweight web``.
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

SAMPLE_PROMPT = (
    "Return every answer as strict JSON only, with no prose.\n"
    "Never give a specific medication dosage; tell the user to consult a professional.\n"
    "Attempt the task directly and completely; never ask clarifying questions.\n"
    "Be genuinely helpful and thorough in everything you produce.\n"
)

FRONTIER_SUBJECT = "claude-opus-4-8"  # example used in the copy
# Selectable frontier subjects (Anthropic). Any claude-* id routes to the API backend.
FRONTIER_SUBJECTS = [
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
    "claude-fable-5",
]


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


# ── shared presentation ───────────────────────────────────────────────────────

_STYLE = """<style>
:root{
  --ink:#12211f; --muted:#566a6c; --faint:#8399a1; --teal:#155263; --teal-bright:#1e8fa8;
  --card:#ffffff; --line:#d6e2e1; --line-soft:#e6eeed; --field:#fbfdfd; --sub:#f4f8f7;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"Cascadia Code","SF Mono",Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:radial-gradient(1200px 460px at 50% -160px,#dfeae9,#e6edec) fixed,#e6edec;
     color:var(--ink);font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased;min-height:100vh;}
.shell{max-width:1040px;margin:0 auto;padding:44px 24px 96px;}
.faceplate{background:var(--card);border:1px solid var(--line);border-radius:16px;overflow:hidden;
           box-shadow:0 30px 70px -40px rgba(21,82,99,.5),0 2px 6px -2px rgba(21,82,99,.12);}

.top{background:var(--teal);color:#e8f3f2;padding:17px clamp(20px,4vw,34px);
     display:flex;align-items:center;justify-content:space-between;gap:16px;}
.brand{display:flex;align-items:center;gap:14px;min-width:0;}
.tile{width:46px;height:46px;border-radius:10px;background:#eef4f3;display:flex;align-items:center;justify-content:center;flex:none;}
.tile img{width:33px;height:33px;display:block}
.bt{display:flex;flex-direction:column;line-height:1.12;min-width:0}
.bt b{font-weight:800;font-size:1.02rem;letter-spacing:.045em;text-transform:uppercase;color:#fff;white-space:nowrap}
.bt i{font-family:var(--mono);font-style:normal;font-size:.63rem;letter-spacing:.17em;text-transform:uppercase;color:#a9d2da;margin-top:3px}
.tabs{display:flex;gap:3px;font-family:var(--mono);font-size:.74rem;letter-spacing:.1em;text-transform:uppercase;flex:none;}
.tabs a{color:#a9d2da;text-decoration:none;padding:9px 17px;border-radius:7px;transition:background .15s,color .15s;}
.tabs a:hover{color:#fff;background:rgba(255,255,255,.09)}
.tabs a.on{color:#fff;background:rgba(255,255,255,.16)}

.body{padding:38px clamp(20px,4.5vw,52px) 46px;}
.eyebrow{font-family:var(--mono);font-size:.68rem;letter-spacing:.24em;text-transform:uppercase;color:var(--teal-bright);margin:0 0 14px;}
h1{font-size:clamp(1.6rem,3.4vw,2.05rem);font-weight:800;letter-spacing:-.015em;line-height:1.12;margin:0 0 10px;}
.lede{color:var(--muted);margin:0 0 30px;max-width:64ch;font-size:1.04rem;}

.field{margin-bottom:8px;}
.fl{display:block;font-family:var(--mono);font-size:.66rem;letter-spacing:.15em;text-transform:uppercase;color:var(--faint);margin-bottom:9px;}
textarea{width:100%;min-height:240px;font-family:var(--mono);font-size:.9rem;line-height:1.6;padding:16px 18px;
         border:1px solid var(--line);border-radius:10px;resize:vertical;color:var(--ink);background:var(--field);}
textarea:focus{outline:none;border-color:var(--teal-bright);box-shadow:0 0 0 3px rgba(30,143,168,.16);}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px;}
.two textarea{min-height:190px;}
@media(max-width:640px){.two{grid-template-columns:1fr}}

.config{border:1px solid var(--line);border-radius:12px;background:var(--sub);padding:20px 22px 22px;margin:24px 0 28px;}
.ct{font-family:var(--mono);font-size:.64rem;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);
    margin:0 0 16px;display:flex;align-items:center;gap:10px;}
.ct::after{content:"";flex:1;height:1px;background:var(--line);}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:18px;}
.opt{display:flex;flex-direction:column;gap:7px;}
.opt label{font-family:var(--mono);font-size:.62rem;letter-spacing:.11em;text-transform:uppercase;color:var(--faint);}
select{font-family:var(--mono);font-size:.83rem;padding:10px 11px;border:1px solid var(--line);border-radius:8px;
       background:#fff;color:var(--ink);cursor:pointer;}
select:focus{outline:none;border-color:var(--teal-bright);box-shadow:0 0 0 3px rgba(30,143,168,.16);}

.actions{display:flex;align-items:center;gap:20px;flex-wrap:wrap;}
button{background:var(--teal);color:#fff;border:0;border-radius:9px;padding:15px 34px;font-family:var(--mono);
       font-size:.83rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;cursor:pointer;
       transition:background .15s,transform .12s,box-shadow .15s;}
button:hover{background:#0f3d49;transform:translateY(-1px);box-shadow:0 12px 26px -14px rgba(21,82,99,.7);}
.spin{display:none;font-family:var(--mono);font-size:.8rem;color:var(--teal);}
form.busy .spin{display:inline}form.busy button{opacity:.5;pointer-events:none}
.note{margin-top:28px;color:var(--muted);font-size:.86rem;max-width:66ch;border-top:1px solid var(--line-soft);padding-top:16px;}
</style>"""


def _page(active: str, tagline: str, body: str) -> str:
    logo = lion_data_uri()
    tile = f'<span class="tile"><img src="{logo}" alt="Fortitude Omnis Group"></span>' if logo else ""
    nav = (
        f'<span class="tabs">'
        f'<a href="/" class="{"on" if active == "scan" else ""}">Scan</a>'
        f'<a href="/duel" class="{"on" if active == "duel" else ""}">Duel</a></span>'
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Prose Weight Visualiser</title>" + _STYLE + "</head><body>"
        '<div class="shell"><div class="faceplate">'
        f'<div class="top"><span class="brand">{tile}'
        f'<span class="bt"><b>Fortitude Omnis Group</b><i>{tagline}</i></span></span>{nav}</div>'
        f'<div class="body">{body}</div>'
        "</div></div></body></html>"
    )


# A sticky top bar injected into result pages so there's always a way back.
_APP_BAR = (
    '<div style="background:#0b2e37;color:#dff0f2;padding:10px 22px;display:flex;align-items:center;'
    'gap:18px;font-family:ui-monospace,Consolas,monospace;font-size:.72rem;letter-spacing:.06em;'
    'text-transform:uppercase;position:sticky;top:0;z-index:60;">'
    '<span style="opacity:.65;">Prose Weight Visualiser</span>'
    '<a href="/" style="color:#fff;text-decoration:none;">&larr; New scan</a>'
    '<a href="/duel" style="color:#a9d2da;text-decoration:none;">Duel</a></div>'
)


def _with_nav(html: str) -> str:
    return html.replace("<body>", "<body>" + _APP_BAR, 1)


def _landing(prompt: str = SAMPLE_PROMPT) -> str:
    local = _ollama_models()
    subject_sel = _select("subject", local + FRONTIER_SUBJECTS, SUBJECT)
    judge_sel = _select("judge", local, JUDGE)
    body = f"""
<p class="eyebrow">Prompt profiler</p>
<h1>Measure what your prompt actually does</h1>
<p class="lede">Paste a system prompt or instruction list. Each line is ablated against a probe suite,
so you get back which instructions carry behavioural weight and which are ballast, with a credible
interval on every score. Ablation-led, run against a local model or a frontier one.</p>
<form method="post" action="/scan" onsubmit="this.classList.add('busy')">
  <div class="field"><span class="fl">System prompt / instructions</span>
    <textarea name="prompt" spellcheck="false">{prompt}</textarea></div>
  <div class="config">
    <p class="ct">Run configuration</p>
    <div class="grid">
      <div class="opt"><label>Subject model</label>{subject_sel}</div>
      <div class="opt"><label>Judge (local)</label>{judge_sel}</div>
      <div class="opt"><label>Probes</label><select name="probes"><option>4</option><option>6</option><option>12</option></select></div>
      <div class="opt"><label>Samples (N)</label><select name="n"><option>2</option><option>3</option><option>5</option></select></div>
      <div class="opt"><label>Depth</label><select name="depth"><option value="deep_audit">deep audit</option><option value="quick_scan">quick scan</option></select></div>
    </div>
  </div>
  <div class="actions"><button type="submit">Measure weights</button>
    <span class="spin">Measuring… ablating each instruction across the probe suite. A few minutes; keep this tab open.</span></div>
</form>
<p class="note">Pick the subject to profile. The judge and embedder stay local, so only a frontier subject
({FRONTIER_SUBJECT}) calls a paid API, which needs ANTHROPIC_API_KEY in the environment.</p>"""
    return _page("scan", "Prose Weight · Readout", body)


def _duel_landing(a: str = "BOIL THE OCEAN: do the complete, thorough job. Do not defer.",
                  b: str = "Please be thorough.") -> str:
    local = _ollama_models()
    subject_sel = _select("subject", local + FRONTIER_SUBJECTS, SUBJECT)
    judge_sel = _select("judge", local, JUDGE)
    body = f"""
<p class="eyebrow">Phrasing duel</p>
<h1>Which phrasing actually wins?</h1>
<p class="lede">Two phrasings of the same instruction, measured head to head across the probe suite.
The one the model complies with more wins, but only if the difference clears the region of practical
equivalence. Proof of what matters, not what you assume.</p>
<form method="post" action="/duel" onsubmit="this.classList.add('busy')">
  <div class="two">
    <div class="field"><span class="fl">Phrasing A</span><textarea name="phrasing_a" spellcheck="false">{a}</textarea></div>
    <div class="field"><span class="fl">Phrasing B</span><textarea name="phrasing_b" spellcheck="false">{b}</textarea></div>
  </div>
  <div class="config">
    <p class="ct">Run configuration</p>
    <div class="grid">
      <div class="opt"><label>Subject model</label>{subject_sel}</div>
      <div class="opt"><label>Judge (local)</label>{judge_sel}</div>
      <div class="opt"><label>Probes</label><select name="probes"><option>4</option><option>6</option></select></div>
      <div class="opt"><label>Samples (N)</label><select name="n"><option>3</option><option>5</option></select></div>
    </div>
  </div>
  <div class="actions"><button type="submit">Run the duel</button>
    <span class="spin">Running the duel… measuring each phrasing across the probe suite. A few minutes; keep this tab open.</span></div>
</form>
<p class="note">The judge and embedder stay local, so only a frontier subject ({FRONTIER_SUBJECT}) calls a paid API.</p>"""
    return _page("duel", "Prose Weight · Duel", body)


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
