"""Run configuration + environment access.

The ``ANTHROPIC_API_KEY`` is read from the environment only, never from a config
file, a CLI flag, or a request body, and is never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_SUBJECT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_JUDGE_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


@dataclass
class RunConfig:
    subject_model: str = DEFAULT_SUBJECT_MODEL
    judge_backend: str = "local-hf"  # local-hf | anthropic-api
    judge_model: str = DEFAULT_JUDGE_MODEL
    suite: str = "default-v1"
    seed: int = 0
    depth: str = "quick_scan"  # quick_scan | deep_audit
    n_runs: int = 20
    j_rescores: int = 5
    posterior_samples: int = 4000
    paraphrase_k: int = 5
    load_bearing_drop: float = 15.0
    dead_weight_budget_tokens: int = 40
    extra: dict = field(default_factory=dict)

    @property
    def uses_api_judge(self) -> bool:
        return self.judge_backend == "anthropic-api"


def anthropic_api_key() -> str | None:
    """Return the API key from the environment, or None. Never log the value."""
    return os.environ.get("ANTHROPIC_API_KEY")
