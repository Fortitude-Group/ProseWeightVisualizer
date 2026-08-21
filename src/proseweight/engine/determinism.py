"""Deterministic RNG + run-metadata plumbing.

Reproducibility (FR-017 / SC-002) rests on never touching global RNG state and
threading independent, seeded ``numpy.random.Generator`` streams. One
``SeedSequence`` spawns one child stream per instruction, so scores are
bit-identical across runs and platforms for a given seed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np


def child_generators(seed: int, count: int) -> list[np.random.Generator]:
    """Return ``count`` independent, deterministic generators for a seed.

    Uses ``SeedSequence.spawn`` so each stream is statistically independent yet
    fully reproducible. Never use ``np.random.seed`` (global state) anywhere.
    """
    root = np.random.SeedSequence(seed)
    return [np.random.default_rng(s) for s in root.spawn(count)]


def named_generator(seed: int, name: str) -> np.random.Generator:
    """A deterministic generator keyed by a string (e.g. a signal name).

    Folds a stable hash of ``name`` into the seed so different named streams do
    not collide, without depending on call order.
    """
    h = int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big")
    return np.random.default_rng(np.random.SeedSequence([seed, h]))


@dataclass
class RunMetadata:
    """The minimum needed to reproduce or diff any score (see research.md)."""

    seed: int
    posterior_samples: int  # S
    n_runs: int  # N per condition
    j_rescores: int  # J judge re-scores per output
    n_probes: int
    blend_weights: tuple[float, float, float]
    suite_version: str
    suite_hash: str
    subject_model: str
    subject_revision: str
    judge_backend: str
    reproducibility: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "S": self.posterior_samples,
            "N": self.n_runs,
            "J": self.j_rescores,
            "n_probes": self.n_probes,
            "blend_weights": list(self.blend_weights),
            "suite_version": self.suite_version,
            "suite_hash": self.suite_hash,
            "subject_model": self.subject_model,
            "subject_revision": self.subject_revision,
            "judge_backend": self.judge_backend,
            "reproducibility": self.reproducibility,
            **self.extra,
        }
