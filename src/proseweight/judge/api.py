"""Opt-in frontier API judge (FR-006b, research.md R4 / task T020a).

Uses ``claude-haiku-4-5`` via forced structured output. The key comes from the
``ANTHROPIC_API_KEY`` environment variable ONLY — never a request field, config,
or CLI flag, and it is never logged. When this backend is used, the run is
flagged best-effort and same-seed reproducibility (SC-002) is waived.
"""

from __future__ import annotations

from proseweight.config import anthropic_api_key
from proseweight.judge.backend import JudgeResult, Rubric

DEFAULT_API_JUDGE_MODEL = "claude-haiku-4-5"


class AnthropicAPIJudge:
    backend_id = "anthropic-api"

    def __init__(self, model_id: str = DEFAULT_API_JUDGE_MODEL):
        self.model_id = model_id
        self._client = None

    def _ensure_client(self):
        if anthropic_api_key() is None:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set in the environment; the frontier judge "
                "reads the key from the environment only."
            )
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "AnthropicAPIJudge needs: pip install 'proseweight[runtime]'"
            ) from e
        if self._client is None:  # pragma: no cover - needs network + key
            self._client = anthropic.Anthropic()  # reads key from env
        return self._client

    def score(self, rubric: Rubric, output: str) -> JudgeResult:  # pragma: no cover
        client = self._ensure_client()
        message = client.messages.create(
            model=self.model_id,
            max_tokens=300,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Score this output on the criterion, 0-4 integer.\n"
                        f"Criterion: {rubric.criterion}\n\nOutput:\n{output}\n\n"
                        'Reply as JSON: {"reasoning": "...", "score": <int 0-4>}'
                    ),
                }
            ],
        )
        import json

        text = message.content[0].text
        data = json.loads(text)
        return JudgeResult(
            score=int(data["score"]),
            reasoning=str(data.get("reasoning", "")),
            backend_id=self.backend_id,
            model_id=self.model_id,
            revision_or_snapshot="api-snapshot",
            decoding_config={"temperature": 0},
            best_effort=True,  # reproducibility waived for API-judged runs
        )
