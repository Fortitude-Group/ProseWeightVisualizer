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


def _suite_path():
    from pathlib import Path

    return Path(__file__).resolve().parents[3] / "data" / "suites" / "default-v1.yaml"


def _landing(prompt: str = SAMPLE_PROMPT) -> str:
    logo = lion_data_uri()
    tile = (
        f'<span class="logotile"><img src="{logo}" alt="Fortitude Omnis Group"></span>'
        if logo else ""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Prose Weight</title>
<style>
:root{{--ink:#0e1f1e;--muted:#5b6f71;--faint:#8aa0a1;--panel:#eef3f2;--card:#fff;--line:#d3e0df;
--teal:#155263;--mono:ui-monospace,"Cascadia Code",Consolas,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--panel);color:var(--ink);font-family:var(--sans);}}
.wrap{{max-width:820px;margin:0 auto;padding:0 20px 60px;}}
header{{background:var(--teal);color:#dff0f2;margin:0 -20px;padding:13px 20px;display:flex;align-items:center;gap:12px;}}
.logotile{{width:40px;height:40px;border-radius:7px;background:#eef4f3;display:flex;align-items:center;justify-content:center;}}
.logotile img{{width:30px;height:30px;display:block}}
.bt{{display:flex;flex-direction:column;line-height:1.08}}
.bt b{{font-weight:700;font-size:.94rem;letter-spacing:.055em;text-transform:uppercase;color:#fff}}
.bt i{{font-family:var(--mono);font-style:normal;font-size:.6rem;letter-spacing:.15em;text-transform:uppercase;color:#a9d2da;margin-top:2px}}
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
<header>{tile}<span class="bt"><b>Fortitude Omnis Group</b><i>Prose Weight · Readout</i></span></header>
<section class="panel">
<h1>Measure what your prompt actually does</h1>
<p class="lede">Paste a system prompt or instruction list. Each line is ablated against a probe
suite on a local model; you get back which instructions carry behavioural weight, with a
credible interval on every score. Ablation-led, run locally via Ollama.</p>
<form method="post" action="/scan" onsubmit="this.classList.add('busy')">
<label>System prompt / instructions</label>
<textarea name="prompt">{prompt}</textarea>
<div class="opts">
<div class="opt"><label>Probes</label><select name="probes"><option>4</option><option>6</option><option>12</option></select></div>
<div class="opt"><label>Samples (N)</label><select name="n"><option>2</option><option>3</option><option>5</option></select></div>
<div class="opt"><label>Depth</label><select name="depth"><option value="deep_audit">deep audit</option><option value="quick_scan">quick scan</option></select></div>
</div>
<button type="submit">Measure weights</button>
<div class="spin">Measuring… ablating each instruction across the probe suite on {SUBJECT}. This takes a few minutes; keep this tab open.</div>
</form>
<p class="note">Subject {SUBJECT} · judge {JUDGE} · embedder {EMBED}, all local.</p>
</section></div></body></html>"""


def create_app() -> FastAPI:
    app = FastAPI(title="Prose Weight Visualiser")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _landing()

    @app.post("/scan", response_class=HTMLResponse)
    def scan(
        prompt: str = Form(...),
        probes: int = Form(4),
        n: int = Form(2),
        depth: str = Form("deep_audit"),
    ) -> str:
        from proseweight.engine.ollama_backend import OllamaMeasurementBackend

        suite = load_suite(_suite_path())
        suite.probes = suite.probes[: max(1, probes)]
        segments = segment_prompt(prompt)
        if not segments:
            return _landing(prompt)
        cfg = RunConfig(subject_model=SUBJECT, seed=42, depth=depth, posterior_samples=3000, n_runs=n)
        backend = OllamaMeasurementBackend(SUBJECT, JUDGE, EMBED, seed=42, n_samples=n, temperature=0.7)
        bundle = backend.measure(prompt, segments, suite, cfg)
        verdict = run_verdict(prompt, segments, suite, cfg, bundle, run_id="web")
        return render_verdict_html(verdict, brand=True)

    return app


app = create_app()
