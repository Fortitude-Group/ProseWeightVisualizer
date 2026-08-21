"""Frontier-subject measurement backend (behavioural-only, no attention).

Runs the ablation against a closed API model (e.g. claude-opus-4-8) as the
SUBJECT, while keeping the judge and embedder local via Ollama. This is the
"thin optional adapter for behavioural-only signals via API models" the spec
earmarked as future work: no attention access, not seed-deterministic, so every
run is flagged best-effort and the same-seed reproducibility guarantee is waived.
Only the subject generations hit the paid API; judging and embedding stay free
and local, and the judge being a different model avoids self-judging.

The API key is read from ``ANTHROPIC_API_KEY`` in the environment only.
"""

from __future__ import annotations

from proseweight.engine.ollama_backend import OllamaMeasurementBackend

DEFAULT_SUBJECT = "claude-opus-4-8"
_MAX_TOKENS = 256


class AnthropicSubjectBackend(OllamaMeasurementBackend):
    def __init__(self, subject_model: str, judge_model: str, embed_model: str, **kw):
        # The Ollama subject slot is unused; subject generation is overridden below.
        super().__init__("(anthropic-subject)", judge_model, embed_model, **kw)
        self.api_model = subject_model
        self._client = None

    def _api(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        return self._client

    def _gen_samples(self, prompt: str, task: str) -> list[str]:
        # NOTE: the installed anthropic SDK (1.0.0) has no `temperature` parameter.
        # The API is non-seeded and non-deterministic by default, so repeated calls
        # still vary, which is what N>1 samples need. Runs are flagged best-effort.
        client = self._api()
        kwargs = {"model": self.api_model, "max_tokens": _MAX_TOKENS,
                  "messages": [{"role": "user", "content": task}]}
        if prompt and prompt.strip():  # the bare calibration condition has no system prompt
            kwargs["system"] = prompt
        outs: list[str] = []
        for _ in range(self.n_samples):
            msg = client.messages.create(**kwargs)
            outs.append("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))
        return outs

    def measure(self, source, segments, suite, cfg):
        bundle = super().measure(source, segments, suite, cfg)
        bundle.runtime = "anthropic-api"
        bundle.extra["best_effort"] = True  # no seed => reproducibility waived
        return bundle
