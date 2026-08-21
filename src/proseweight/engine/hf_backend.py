"""Real Hugging Face measurement backend (the model-dependent glue).

Implements ``MeasurementBackend`` by running the subject model over the probe
suite for the full prompt and each ablated prompt, scoring outputs with the
judge (FR-006a/b), the embedder (research.md R4), and the probes' programmatic
checks, plus the attention pre-screen (engine.token_core). This is the ONLY
component that needs GPU + model weights; the deterministic verdict-assembly
pipeline (``proseweight.verdict.orchestrator``) is validated independently with a
fake backend.

Left as a wired skeleton: the per-probe generation loop and check execution are
marked where real inference plugs in. It raises a clear error until the runtime
extra + model weights are present, rather than silently degrading.
"""

from __future__ import annotations

from proseweight.verdict.backend import MeasurementBundle


class HFMeasurementBackend:
    def __init__(self, cfg):
        self.cfg = cfg

    def measure(self, source: str, segments, suite, cfg) -> MeasurementBundle:  # pragma: no cover
        raise NotImplementedError(
            "HFMeasurementBackend requires model weights + GPU (pip install "
            "'proseweight[runtime]'). The deterministic verdict pipeline is validated "
            "via the fake backend; wire subject generation, judge, embedder, and "
            "programmatic checks here to produce a MeasurementBundle."
        )
