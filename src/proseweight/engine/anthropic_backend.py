"""Frontier-subject measurement (behavioural-only, no attention).

Runs the ablation, or a phrasing duel, against a closed API model (e.g.
claude-opus-4-8) as the SUBJECT, while keeping the judge and embedder local via
Ollama. This is the "thin adapter for behavioural-only signals via API models"
the spec earmarked as future work: no attention access, not seed-deterministic,
so every run is flagged best-effort. Only the subject generations hit the paid
API; judging and embedding stay free and local, and the judge being a different
model avoids self-judging.

The API key is read from ``ANTHROPIC_API_KEY`` in the environment only.
"""

from __future__ import annotations

from proseweight.engine.ollama_backend import OllamaDuelBackend, OllamaMeasurementBackend

DEFAULT_SUBJECT = "claude-opus-4-8"
_MAX_TOKENS = 256


class _AnthropicSubject:
    """Mixin: generate the subject's completions via the Anthropic API, with usage tracking."""

    def _init_anthropic(self, api_model: str) -> None:
        self.api_model = api_model
        self._client = None
        self.usage = {"calls": 0, "input": 0, "output": 0}

    def _api(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        return self._client

    def _gen_samples(self, prompt: str, task: str) -> list[str]:
        # The installed SDK has no `temperature` parameter; the API is non-seeded, so
        # repeated calls still vary (what N>1 needs). The bare condition sends no system.
        client = self._api()
        kwargs = {"model": self.api_model, "max_tokens": _MAX_TOKENS,
                  "messages": [{"role": "user", "content": task}]}
        if prompt and prompt.strip():
            kwargs["system"] = prompt
        outs: list[str] = []
        for _ in range(self.n_samples):
            msg = client.messages.create(**kwargs)
            self.usage["calls"] += 1
            self.usage["input"] += msg.usage.input_tokens
            self.usage["output"] += msg.usage.output_tokens
            outs.append("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))
        return outs


class AnthropicSubjectBackend(_AnthropicSubject, OllamaMeasurementBackend):
    def __init__(self, subject_model: str, judge_model: str, embed_model: str, **kw):
        super().__init__("(anthropic-subject)", judge_model, embed_model, **kw)
        self._init_anthropic(subject_model)

    def measure(self, source, segments, suite, cfg):
        bundle = super().measure(source, segments, suite, cfg)
        bundle.runtime = "anthropic-api"
        bundle.extra["best_effort"] = True  # no seed => reproducibility waived
        bundle.extra["api_usage"] = dict(self.usage)
        return bundle


class AnthropicDuelBackend(_AnthropicSubject, OllamaDuelBackend):
    def __init__(self, subject_model: str, judge_model: str, embed_model: str, **kw):
        super().__init__("(anthropic-subject)", judge_model, embed_model, **kw)
        self._init_anthropic(subject_model)
