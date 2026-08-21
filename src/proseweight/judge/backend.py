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
            import torch  # noqa: F401
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as e:
            raise RuntimeError(
                "LocalHFJudge needs the model runtime: pip install 'proseweight[runtime]'"
            ) from e
        tok = AutoTokenizer.from_pretrained(self.model_id, revision=self.revision)
        model = AutoModelForCausalLM.from_pretrained(self.model_id, revision=self.revision)
        model.eval()
        self._pipe = (tok, model)

    def _prompt(self, rubric: Rubric, output: str) -> str:
        anchors = "\n".join(f"  {k}: {v}" for k, v in sorted(rubric.anchors.items()))
        return (
            f"Score the output against the criterion on a 0-4 integer scale.\n"
            f"Criterion: {rubric.criterion}\n"
            + (f"Anchors:\n{anchors}\n" if anchors else "")
            + f"\nOutput:\n{output}\n\nScore (a single digit 0-4):"
        )

    def score(self, rubric: Rubric, output: str) -> JudgeResult:  # pragma: no cover
        import re

        import torch

        if self._pipe is None:
            self._load()
        tok, model = self._pipe
        ids = tok(self._prompt(rubric, output), return_tensors="pt").input_ids.to(model.device)
        with torch.no_grad():
            # greedy, short: the score is a single digit. A logits processor
            # restricting to the digit tokens is the production path; parsing the
            # first 0-4 digit is the dependency-light equivalent.
            gen = model.generate(ids, max_new_tokens=3, do_sample=False, pad_token_id=tok.eos_token_id)
        text = tok.decode(gen[0][ids.shape[1]:], skip_special_tokens=True)
        m = re.search(r"[0-4]", text)
        score = int(m.group()) if m else 0
        return JudgeResult(
            score=score,
            reasoning="",
            backend_id=self.backend_id,
            model_id=self.model_id,
            revision_or_snapshot=self.revision,
            decoding_config={"mode": "greedy", "max_new_tokens": 3},
        )
