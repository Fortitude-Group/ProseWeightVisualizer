"""Tests for the emphasis audit (US6) and position sensitivity (US7)."""

from __future__ import annotations

import numpy as np

from proseweight.config import RunConfig
from proseweight.duel.duel import PhrasingSignals
from proseweight.duel.emphasis import emphasis_variants, run_emphasis_audit
from proseweight.duel.position import POSITIONS, reposition, run_position_sweep


def test_emphasis_variants_cover_devices():
    v = emphasis_variants("Never defer.")
    assert v["caps"] == "NEVER DEFER."
    assert v["bold"] == "**Never defer.**"
    assert v["important"].startswith("IMPORTANT:")
    assert v["exclamation"].endswith("!")
    assert v["repetition"] == "Never defer. Never defer."
    assert v["list_item"].startswith("- ")
    assert set(v) == {"caps", "bold", "important", "exclamation", "repetition", "list_item"}


class CapsWinsBackend:
    """A model where ALL-CAPS phrasings comply more strongly; others tie the plain."""

    def measure_phrasing(self, phrasing, suite, cfg) -> PhrasingSignals:
        rng = np.random.default_rng(abs(hash(phrasing)) % 1000)
        if phrasing.isupper():
            judge = np.clip(rng.normal(0.9, 0.03, 12), 0, 1)
            passed = rng.random(12) > 0.1
        else:
            judge = np.clip(rng.normal(0.5, 0.03, 12), 0, 1)
            passed = rng.random(12) > 0.5
        return PhrasingSignals(judge=judge, passed=passed, noise_sd=0.03)


def test_emphasis_audit_detects_moving_device():
    results = run_emphasis_audit("please be thorough", CapsWinsBackend(), None, RunConfig(seed=1, posterior_samples=2000))
    by_device = {r.device: r for r in results}
    assert by_device["caps"].moved_weight is True
    # a device that only wraps the text without changing case should not "win" here
    assert by_device["bold"].moved_weight is False


def test_reposition_moves_instruction():
    prompt = "First line.\nMove me.\nLast line.\n"
    top = reposition(prompt, "Move me.", "top")
    bottom = reposition(prompt, "Move me.", "bottom")
    assert top.splitlines()[0] == "Move me."
    assert bottom.splitlines()[-1] == "Move me."
    # no duplication and no loss
    assert top.count("Move me.") == 1
    assert bottom.count("Move me.") == 1


class PositionBackendFake:
    """Weight depends on where the instruction sits (top scores highest)."""

    def measure_instruction_weight(self, prompt, instruction_text, suite, cfg):
        first = prompt.splitlines()[0].strip() == instruction_text.strip()
        w = 85.0 if first else 45.0
        return (w, w - 4, w + 4)


def test_position_sweep_reports_each_position():
    points = run_position_sweep(
        "A.\nMove me.\nB.\n", "Move me.", PositionBackendFake(), None, RunConfig()
    )
    assert [p.position for p in points] == list(POSITIONS)
    top = next(p for p in points if p.position == "top")
    bottom = next(p for p in points if p.position == "bottom")
    assert top.weight > bottom.weight  # this model is position-sensitive
    assert all(p.ci_low <= p.weight <= p.ci_high for p in points)
