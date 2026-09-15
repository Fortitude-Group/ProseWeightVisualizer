"""Integration test: CI cache-lint gate (T045 / US8 / SC-007)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from proseweight.cache.ci.lint import make_baseline, run_gate
from proseweight.cache.core.contracts import LintFinding
from proseweight.cache.core.pricing import Pricing
from proseweight.cli.main import app

runner = CliRunner()


def _finding(rule, line, gbp=4.0) -> LintFinding:
    return LintFinding(rule, "CLAUDE.md", line, 0, gbp, "2026-09", "2026-09-01", "2026-09-01")


def test_gate_unit_clean_regression_and_confound():
    p = Pricing.load()
    base = make_baseline([_finding("crlf_drift", 1)], "claude-opus-5", p)
    # clean: same finding, no new one
    assert run_gate([_finding("crlf_drift", 1)], base, "claude-opus-5", p).exit_code == 0
    # regression: a new finding
    g = run_gate([_finding("crlf_drift", 1), _finding("trailing_whitespace", 2)], base, "claude-opus-5", p)
    assert g.exit_code == 1
    assert any("£" in m for m in g.messages)
    # confound: different model
    assert run_gate([_finding("crlf_drift", 1)], base, "claude-sonnet-5", p).exit_code == 3


def test_gate_via_cli(tmp_path):
    clean = tmp_path / "CLAUDE.md"
    clean.write_bytes(b"a clean line\nanother clean line\n")
    bl = tmp_path / "baseline.json"

    # create baseline from the clean file
    r = runner.invoke(app, ["cache", "lint", str(clean), "--baseline", str(bl), "--update-baseline"])
    assert r.exit_code == 0 and bl.exists()

    # benign: same clean file -> exit 0
    r = runner.invoke(app, ["cache", "lint", str(clean), "--baseline", str(bl)])
    assert r.exit_code == 0

    # regression: convert to CRLF -> exit 1 with the estimated £ in the message
    clean.write_bytes(b"a clean line\r\nanother clean line\r\n")
    r = runner.invoke(app, ["cache", "lint", str(clean), "--baseline", str(bl)])
    assert r.exit_code == 1
    assert "FAILED" in r.output and "£" in r.output


def test_gate_confound_via_cli(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_bytes(b"a clean line\n")
    bl = tmp_path / "baseline.json"
    # a baseline stamped with a different pricing version
    bl.write_text(json.dumps({"baseline_version": "1.0.0", "model": "claude-opus-5",
                              "pricing_version": "2019-01", "signatures": []}), encoding="utf-8")
    r = runner.invoke(app, ["cache", "lint", str(f), "--baseline", str(bl)])
    assert r.exit_code == 3
    assert "confound" in r.output.lower()
