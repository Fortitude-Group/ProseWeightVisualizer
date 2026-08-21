"""Ollama-backed measurement backend (real inference over the local Ollama API).

A drop-in ``MeasurementBackend`` that runs the subject model, the judge, and the
embedder through a running Ollama daemon (http://localhost:11434). Needs no
torch, no bitsandbytes, and no gated downloads: it uses whatever models Ollama
has pulled. Greedy decoding (temperature 0) + a fixed seed for determinism.

This is the pragmatic path for a local machine that already runs Ollama. The
subject stays local; the judge is a different-generation/size model to reduce
same-family self-favouritism (documented caveat when it can't be fully avoided).
"""

from __future__ import annotations

import json
import re
import urllib.request

import numpy as np

from proseweight.engine.blend import calibrate_embedding_ceiling
from proseweight.probes.checks import non_empty, run_check
from proseweight.verdict.backend import InstructionMeasurement, MeasurementBundle

_BASE = "http://localhost:11434"


def _post(path: str, payload: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        _BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat(
    model: str, system: str, user: str, seed: int = 0, think: bool = False, temperature: float = 0.0
) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "think": think,
        "options": {"temperature": temperature, "seed": seed, "num_predict": 256},
    }
    data = _post("/api/chat", payload)
    return data.get("message", {}).get("content", "") or ""


def embed(model: str, text: str) -> np.ndarray:
    data = _post("/api/embed", {"model": model, "input": text})
    vecs = data.get("embeddings") or [data.get("embedding", [])]
    v = np.asarray(vecs[0], dtype=float)
    n = np.linalg.norm(v)
    return v / n if n else v


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    return float(min(max(1.0 - float(np.dot(a, b)), 0.0), 1.0))


class OllamaMeasurementBackend:
    def __init__(
        self,
        subject_model: str,
        judge_model: str,
        embed_model: str,
        seed: int = 0,
        think_subject: bool = False,
        n_samples: int = 1,
        temperature: float = 0.0,
    ):
        self.subject_model = subject_model
        self.judge_model = judge_model
        self.embed_model = embed_model
        self.seed = seed
        self.think_subject = think_subject
        # N seeded samples per condition. With N>1 use a sampling temperature so
        # repeats actually vary (greedy at temp 0 gives identical outputs, hence
        # no variance for the noise model to work with).
        self.n_samples = max(1, n_samples)
        self.temperature = temperature if self.n_samples > 1 else 0.0

    def _gen_samples(self, prompt: str, task: str) -> list[str]:
        return [
            chat(self.subject_model, prompt, task, self.seed + r, self.think_subject, self.temperature)
            for r in range(self.n_samples)
        ]

    def _judge_score(self, criteria: list[str], output: str) -> float:
        if not criteria:
            return 1.0 if output.strip() else 0.0
        scores = []
        for crit in criteria:
            prompt = (
                f"Score the output against this criterion on a 0-4 integer scale "
                f"(0 = not at all, 4 = fully). Reply with ONLY the digit.\n"
                f"Criterion: {crit}\n\nOutput:\n{output}\n\nScore:"
            )
            text = chat(self.judge_model, "You are a strict grader.", prompt, self.seed)
            m = re.search(r"[0-4]", text)
            scores.append((int(m.group()) if m else 0) / 4.0)
        return float(np.mean(scores))

    def _prog_score(self, probe, output: str) -> float:
        scores = [non_empty(output)]
        for a in probe.prog_assertions:
            r = run_check(a, output)
            if r is not None:
                scores.append(r)
        return float(np.mean(scores))

    def measure(self, source: str, segments, suite, cfg) -> MeasurementBundle:
        probes = suite.probes
        candidates = segments
        if cfg.depth != "deep_audit":
            k = max(1, round(len(segments) * 0.3))
            candidates = segments[:k]

        n = self.n_samples

        # Phase 1 — all SUBJECT generations (N samples per condition; model stays loaded).
        base_out = [self._gen_samples(source, p.task) for p in probes]  # [probe][repeat]
        bare_out = [self._gen_samples("", p.task) for p in probes]
        abl_out = {}  # seg.id -> [probe][repeat]
        for seg in candidates:
            ablated = source[: seg.start_offset] + source[seg.end_offset :]
            abl_out[seg.id] = [self._gen_samples(ablated, p.task) for p in probes]

        # Phase 2 — all JUDGE scorings (one model switch). Score every sample.
        def judge_grid(outs):
            return [[self._judge_score(p.judge_criteria, o) for o in outs[i]] for i, p in enumerate(probes)]

        base_j = judge_grid(base_out)
        bare_j = judge_grid(bare_out)
        abl_j = {sid: judge_grid(outs) for sid, outs in abl_out.items()}

        # Phase 3 — all EMBEDDINGS + programmatic checks (one model switch).
        def emb_grid(outs):
            return [[embed(self.embed_model, o) for o in outs[i]] for i in range(len(probes))]

        def prog_grid(outs):
            return [[self._prog_score(p, o) for o in outs[i]] for i, p in enumerate(probes)]

        base_e = emb_grid(base_out)
        base_pr = prog_grid(base_out)
        bare_pr = prog_grid(bare_out)

        all_embed: list[float] = []

        def build_measurement(iid, outs, j_grid, pr_grid, e_full, j_full, pr_full, token_cost):
            dj, de, pf, pa = [], [], [], []
            for i in range(len(probes)):
                e_abl = [embed(self.embed_model, o) for o in outs[i]]
                for r in range(n):
                    dj.append(abs(j_full[i][r] - j_grid[i][r]))
                    dist = cosine_distance(e_full[i][r], e_abl[r])
                    de.append(dist)
                    all_embed.append(dist)
                    pf.append(pr_full[i][r] >= 0.5)
                    pa.append(pr_grid[i][r] >= 0.5)
            return InstructionMeasurement(
                instruction_id=iid,
                delta_judge=np.array(dj),
                delta_embed=np.array(de),
                pass_full=np.array(pf, dtype=bool),
                pass_ablated=np.array(pa, dtype=bool),
                attention_prescreen=float(np.mean(dj)) if dj else 0.0,
                token_cost=token_cost,
            )

        instrs = []
        for seg in candidates:
            instrs.append(
                build_measurement(
                    seg.id, abl_out[seg.id], abl_j[seg.id], prog_grid(abl_out[seg.id]),
                    base_e, base_j, base_pr, seg.token_cost(),
                )
            )

        # Calibration: whole-prompt effect (full vs bare) -> the 0-100 ceiling.
        calibration = build_measurement(
            "__calibration__", bare_out, bare_j, bare_pr, base_e, base_j, base_pr, 0
        )

        ceiling = calibrate_embedding_ceiling(all_embed) if all_embed else 1.0
        return MeasurementBundle(
            instructions=instrs,
            noise_sd={"judge": 0.08, "prog": 0.08, "embed": 0.05},
            ceiling=1.0,
            runtime="ollama-cuda",
            extra={"embedding_ceiling": ceiling, "ceiling_calibrated_on": "run"},
            calibration=calibration,
        )


class OllamaDuelBackend(OllamaMeasurementBackend):
    """Measures a phrasing's compliance across the probe suite (for phrasing duels)."""

    def measure_phrasing(self, phrasing: str, suite, cfg):
        from proseweight.duel.duel import PhrasingSignals

        probes = suite.probes
        # subject phase first (all generations), then judge/prog phase
        outs = [self._gen_samples(phrasing, p.task) for p in probes]
        judge = [
            float(np.mean([self._judge_score(p.judge_criteria, o) for o in outs[i]]))
            for i, p in enumerate(probes)
        ]
        passed = [
            float(np.mean([self._prog_score(p, o) for o in outs[i]])) >= 0.5
            for i, p in enumerate(probes)
        ]
        return PhrasingSignals(
            judge=np.array(judge), passed=np.array(passed, dtype=bool), noise_sd=0.08
        )
