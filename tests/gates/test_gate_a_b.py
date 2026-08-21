"""Gate A (instrument validity) and Gate B (reproducibility) harness (SC-001/002).

Parameterised over a backend factory. Here it runs against the deterministic fake
backend that plants ground truth, which validates the harness and the assembly.
The SAME harness runs against ``HFMeasurementBackend`` on a GPU box to certify the
real instrument; only the backend factory changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _fakes import FakeBackend  # noqa: E402
from proseweight.config import RunConfig  # noqa: E402
from proseweight.probes.suite import load_suite  # noqa: E402
from proseweight.segmentation.pipeline import segment_prompt  # noqa: E402
from proseweight.verdict.orchestrator import run_verdict  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "data" / "suites" / "default-v1.yaml"
FIXTURE = ROOT / "data" / "fixtures" / "planted-ground-truth.md"


def _run(seed, backend_factory):
    source = FIXTURE.read_text(encoding="utf-8")
    suite = load_suite(SUITE)
    segs = segment_prompt(source)
    cfg = RunConfig(seed=seed, depth="deep_audit", posterior_samples=3000)
    bundle = backend_factory(seed).measure(source, segs, suite, cfg)
    return run_verdict(source, segs, suite, cfg, bundle)


def _planted(row):
    return "[LB]" in row.instruction.text, "[NOOP]" in row.instruction.text


def test_gate_a_ranks_load_bearing_above_no_ops():
    """SC-001: over many seeds, planted load-bearing must outrank planted no-ops
    and the no-ops must land in the noise floor, in >=90% of runs."""
    passes = 0
    trials = 12
    for seed in range(trials):
        v = _run(seed, lambda s: FakeBackend(seed=s))
        lb = [r for r in v.rows if _planted(r)[0]]
        noop = [r for r in v.rows if _planted(r)[1]]
        ranked = min(r.weight.weight for r in lb) > max(r.weight.weight for r in noop)
        floored = all(r.weight.is_noise_floor for r in noop)
        if ranked and floored:
            passes += 1
    assert passes / trials >= 0.90


def test_gate_b_same_seed_identical():
    a = _run(7, lambda s: FakeBackend(seed=s)).to_dict()
    b = _run(7, lambda s: FakeBackend(seed=s)).to_dict()
    assert a == b


def test_gate_b_cross_seed_classification_agreement():
    base = {r.instruction.text: r.label for r in _run(1, lambda s: FakeBackend(seed=s)).rows}
    agree_total = 0
    comparisons = 0
    for seed in (2, 3, 4):
        other = {r.instruction.text: r.label for r in _run(seed, lambda s: FakeBackend(seed=s)).rows}
        for k in base:
            comparisons += 1
            if base[k] == other[k]:
                agree_total += 1
    assert agree_total / comparisons >= 0.85
