"""Judge backend boundary (FR-006a/b, research.md R4).

The judge scores an output against a per-probe rubric on a fixed 0-4 integer
scale. ``LocalHFJudge`` (default, cross-family) and ``AnthropicAPIJudge`` (opt-in)
implement the same protocol so the backend is swappable. Both score the full and
ablated outputs *independently* (never comparatively) to avoid position bias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Rubric:
    probe_id: str
    criterion: str
    anchors: dict[int, str] = field(default_factory=dict)  # score -> anchor text


@dataclass(frozen=True)
class JudgeResult:
    score: int  # 0-4
    reasoning: str
    backend_id: str  # "local-hf" | "anthropic-api"
    model_id: str
    revision_or_snapshot: str
    decoding_config: dict
    best_effort: bool = False


class JudgeBackend(Protocol):
    backend_id: str

    def score(self, rubric: Rubric, output: str) -> JudgeResult: ...


class LocalHFJudge:
    """Default judge: a separate local model (Llama-3.1-8B-Instruct, 4-bit).

    Cross-family by design (subject is Qwen) to avoid same-family favouritism.
    Grammar-constrained to a 0-4 integer via a logits processor. Requires the
    ``runtime`` extra; raises a clear error if unavailable.
    """

    backend_id = "local-hf"

    def __init__(self, model_id: str, revision: str = "unpinned"):
        self.model_id = model_id
        self.revision = revision
        self._pipe = None

    def _load(self):  # pragma: no cover - needs model weights
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as e:
            raise RuntimeError(
                "LocalHFJudge needs the model runtime: pip install 'proseweight[runtime]'"
            ) from e
        tok = AutoTokenizer.from_pretrained(self.model_id, revision=self.revision)
        model = AutoModelForCausalLM.from_pretrained(self.model_id, revision=self.revision)
        model.eval()
        self._pipe = (tok, model)

    def score(self, rubric: Rubric, output: str) -> JudgeResult:  # pragma: no cover
        raise NotImplementedError(
            "LocalHFJudge scoring requires model weights; implemented in the runtime extra"
        )
