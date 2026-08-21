"""Tests for pairwise conflict detection (T040) and the cost estimate (T034)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _builders import make_row  # noqa: E402
from proseweight.verdict.conflict import candidate_pairs, detect_conflicts  # noqa: E402
from proseweight.verdict.estimate import estimate_run  # noqa: E402


def test_candidate_pairs_excludes_noise_floor():
    rows = [
        make_row("A", 90, 0.99, offset=0),
        make_row("B", 80, 0.99, offset=1),
        make_row("C", 3, 0.70, offset=2),  # noise floor -> excluded
    ]
    pairs = candidate_pairs(rows)
    ids = {p for pair in pairs for p in pair}
    assert "i2" not in ids
    assert len(pairs) == 1  # only (A,B)


def test_detect_conflicts_flags_fighting_pair():
    rows = [make_row("A", 90, 0.99, offset=0), make_row("B", 80, 0.99, offset=1)]
    # interaction returns a large delta for this one pair
    conflicts = detect_conflicts(rows, lambda a, b: 0.4)
    assert len(conflicts) == 1
    assert {conflicts[0].instruction_a_id, conflicts[0].instruction_b_id} == {"i0", "i1"}


def test_detect_conflicts_ignores_weak_interaction():
    rows = [make_row("A", 90, 0.99, offset=0), make_row("B", 80, 0.99, offset=1)]
    assert detect_conflicts(rows, lambda a, b: 0.01) == []


def test_quick_scan_cheaper_than_deep():
    quick = estimate_run(50, 12, "quick_scan", n_runs=30)
    deep = estimate_run(50, 12, "deep_audit", n_runs=30)
    assert quick.seconds < deep.seconds
    assert quick.total_probe_runs < deep.total_probe_runs
    assert "quick scan" in quick.note


def test_estimate_human_readable():
    est = estimate_run(50, 12, "quick_scan", n_runs=30)
    assert "min" in est.human()
    assert est.minutes > 0
