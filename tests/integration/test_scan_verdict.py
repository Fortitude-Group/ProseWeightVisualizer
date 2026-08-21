"""US1 verdict-assembly integration tests, and Gate A/B logic at the assembly level.

These exercise the deterministic pipeline (segment -> measure -> stats -> blend ->
classify -> headline) with a fake backend that plants ground truth. True Gate A/B
additionally require real model runs; this proves the assembly is correct and
reproducible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _fakes import FakeBackend  # noqa: E402
from proseweight.config import RunConfig  # noqa: E402
from proseweight.probes.suite import load_suite  # noqa: E402
from proseweight.report.schema import Classification  # noqa: E402
from proseweight.segmentation.pipeline import segment_prompt  # noqa: E402
from proseweight.verdict.orchestrator import run_verdict  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "data" / "suites" / "default-v1.yaml"

PLANTED = (
    "[LB] Never defer; attempt the fix directly.\n"
    "[NOOP] Be helpful and thorough in all your responses.\n"
    "[LB] Always return output as strict JSON with no prose.\n"
    "[NOOP] Remember that quality matters a great deal here.\n"
)


def _run(seed=42):
    suite = load_suite(SUITE)
    segs = segment_prompt(PLANTED)
    cfg = RunConfig(seed=seed, depth="deep_audit", posterior_samples=3000)
    bundle = FakeBackend(seed=seed).measure(PLANTED, segs, suite, cfg)
    return run_verdict(PLANTED, segs, suite, cfg, bundle)


def test_verdict_validates():
    _run().validate()  # raises on any schema-guarantee breach


def test_gate_a_ranking_lb_above_noop():
    v = _run()
    by_id = {r.instruction.id: r for r in v.rows}
    lb = [r for r in v.rows if "[LB]" in r.instruction.text]
    noop = [r for r in v.rows if "[NOOP]" in r.instruction.text]
    assert min(r.weight.weight for r in lb) > max(r.weight.weight for r in noop)
    # planted no-ops must land in the noise-floor state
    assert all(r.weight.is_noise_floor for r in noop)
    assert not any(r.weight.is_noise_floor for r in lb)
    assert by_id  # sanity


def test_load_bearing_classified():
    v = _run()
    lb = [r for r in v.rows if "[LB]" in r.instruction.text]
    assert all(r.label == Classification.LOAD_BEARING for r in lb)


def test_headline_matches_noise_rows():
    v = _run()
    noise = sum(1 for r in v.rows if r.weight.is_noise_floor)
    assert abs(v.noise_floor_headline_pct - 100.0 * noise / len(v.rows)) < 0.2


def test_dead_weight_lists_noise_floor_with_cost():
    v = _run()
    dead_ids = {d.instruction_id for d in v.dead_weight}
    noise_ids = {r.instruction.id for r in v.rows if r.weight.is_noise_floor}
    assert dead_ids == noise_ids
    assert all(d.token_cost > 0 for d in v.dead_weight)


def test_gate_b_reproducible_same_seed():
    a = _run(seed=7).to_dict()
    b = _run(seed=7).to_dict()
    assert a == b


def test_gate_b_different_seed_same_classification():
    a = {r.instruction.text: r.label for r in _run(seed=1).rows}
    b = {r.instruction.text: r.label for r in _run(seed=2).rows}
    # classification agreement on load-bearing/decorative across seeds
    agree = sum(1 for k in a if a[k] == b[k])
    assert agree / len(a) >= 0.85


@pytest.mark.parametrize("seed", [0, 1, 99])
def test_every_score_has_interval(seed):
    v = _run(seed=seed)
    for r in v.rows:
        assert r.weight.ci_low <= r.weight.weight <= r.weight.ci_high
        assert 0.0 <= r.weight.pd <= 1.0
