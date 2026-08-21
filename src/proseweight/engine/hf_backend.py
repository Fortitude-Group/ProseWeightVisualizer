"""Real Hugging Face measurement backend (the model-dependent glue).

Implements ``MeasurementBackend`` by running the subject model over the probe
suite for the full prompt and each ablated prompt, then scoring outputs with the
judge (FR-006a/b), the embedder, and the probes' programmatic checks, plus the
attention pre-screen. This is the ONLY component that needs GPU + model weights;
the deterministic verdict pipeline is validated independently with a fake backend.

NOTE: this code is written against the tested interfaces but has NOT been run
against real weights in the build environment. Torch/transformers are imported
lazily; without the runtime extra it raises a clear error rather than degrading.
"""

from __future__ import annotations

import numpy as np

from proseweight.config import RunConfig, anthropic_api_key
from proseweight.engine.blend import calibrate_embedding_ceiling
from proseweight.engine.embedding import BgeEmbedder
from proseweight.judge.api import AnthropicAPIJudge
from proseweight.judge.backend import LocalHFJudge, Rubric
from proseweight.probes.checks import non_empty, run_check
from proseweight.verdict.backend import InstructionMeasurement, MeasurementBundle

QUICK_CANDIDATE_FRACTION = 0.3


class HFMeasurementBackend:
    def __init__(self, cfg: RunConfig):
        self.cfg = cfg
        self._subject = None
        self._embedder = BgeEmbedder()
        self._judge = self._make_judge()

    def _make_judge(self):
        if self.cfg.judge_backend == "anthropic-api":
            if anthropic_api_key() is None:
                raise RuntimeError("ANTHROPIC_API_KEY not set for the frontier judge")
            return AnthropicAPIJudge()
        return LocalHFJudge(self.cfg.judge_model)

    def _subject_model(self):  # pragma: no cover - needs weights
        if self._subject is None:
            from proseweight.models.loader import get_model

            self._subject = get_model(self.cfg.subject_model)
        return self._subject

    def _generate(self, prompt: str, probe_input: str) -> str:  # pragma: no cover
        """Run the subject model on (prompt + probe) and return the completion."""
        tok, model, device = self._subject_model()  # clean RuntimeError if no runtime
        import torch
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": probe_input}]
        text = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        ids = tok(text, return_tensors="pt").input_ids.to(device)
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=256, do_sample=False, pad_token_id=tok.eos_token_id)
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True)

    def _prog_score(self, probe, output: str) -> float:  # pragma: no cover
        """Blend the probe's programmatic checks into a [0,1] compliance score."""
        scores = []
        for a in probe.vars.get("_assertions", []):
            r = run_check(a, output)
            if r is not None:
                scores.append(r)
        scores.append(non_empty(output))  # the weak PROG floor
        return float(np.mean(scores)) if scores else 0.0

    def measure(self, source: str, segments, suite, cfg) -> MeasurementBundle:  # pragma: no cover
        probes = suite.probes
        # baseline (full prompt) outputs per probe
        base_out = [self._generate(source, p.vars.get("task", "")) for p in probes]
        base_judge = [
            self._judge.score(Rubric(p.probe_id, "probe rubric"), o).score / 4.0
            for p, o in zip(probes, base_out, strict=True)
        ]
        base_pass = [self._prog_score(p, o) >= 0.5 for p, o in zip(probes, base_out, strict=True)]

        # choose conditions: quick scan ablates the top attention-ranked candidates
        candidates = segments
        if cfg.depth != "deep_audit":
            k = max(1, round(len(segments) * QUICK_CANDIDATE_FRACTION))
            candidates = segments[:k]

        instrs = []
        all_embed = []
        for seg in candidates:
            ablated = source[: seg.start_offset] + source[seg.end_offset :]
            abl_out = [self._generate(ablated, p.vars.get("task", "")) for p in probes]
            dj, de, pf, pa = [], [], [], []
            for i, p in enumerate(probes):
                aj = self._judge.score(Rubric(p.probe_id, "probe rubric"), abl_out[i]).score / 4.0
                dj.append(abs(base_judge[i] - aj))
                dist = self._embedder.distance(base_out[i], abl_out[i])
                de.append(dist)
                all_embed.append(dist)
                pf.append(bool(base_pass[i]))
                pa.append(self._prog_score(p, abl_out[i]) >= 0.5)
            instrs.append(
                InstructionMeasurement(
                    instruction_id=seg.id,
                    delta_judge=np.array(dj),
                    delta_embed=np.array(de),
                    pass_full=np.array(pf, dtype=bool),
                    pass_ablated=np.array(pa, dtype=bool),
                    attention_prescreen=0.0,  # populated by the token-core pre-screen
                    token_cost=seg.token_cost(),
                )
            )

        ceiling = calibrate_embedding_ceiling(all_embed) if all_embed else 1.0
        _, _, device = self._subject_model()
        return MeasurementBundle(
            instructions=instrs,
            noise_sd={"judge": 0.05, "prog": 0.05, "embed": 0.05},
            ceiling=1.0,
            runtime=device,
            extra={"embedding_ceiling": ceiling, "ceiling_calibrated_on": "run"},
        )
