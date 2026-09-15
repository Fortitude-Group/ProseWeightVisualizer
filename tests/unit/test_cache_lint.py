"""Unit test: static lint (T023 / US2) — three seeded findings, framed as predictions (SC-004)."""

from __future__ import annotations

from proseweight.cache.core.api import lint as run_lint
from proseweight.cache.core.contracts import LintFraming
from proseweight.cache.core.lint import lint_bytes
from proseweight.cache.core.pricing import Pricing


def test_three_seeded_findings():
    # line 1 CRLF, line 2 trailing whitespace, line 3 volatile header
    data = b"ok line\r\ntrailing   \nupdated: 2026-09-14\n"
    findings = lint_bytes(data, "CLAUDE.md", Pricing.load())
    rules = {f.rule_id for f in findings}
    assert "crlf_drift" in rules
    assert "trailing_whitespace" in rules
    assert "volatile_header" in rules
    # the volatile header is on line 3
    vh = next(f for f in findings if f.rule_id == "volatile_header")
    assert vh.line == 3


def test_all_findings_are_predictions_and_stamped():
    data = b"x\r\n"
    findings = lint_bytes(data, "CLAUDE.md", Pricing.load())
    assert findings
    for f in findings:
        assert f.framing is LintFraming.PREDICTION
        assert f.estimated_monthly_gbp >= 0.0
        assert f.pricing_version and f.effective_date and f.fx_date


def test_lint_via_api_returns_valid_result(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_bytes(b"a line\r\nclean\n")
    result = run_lint([str(p)])
    result.validate()
    assert any(f.rule_id == "crlf_drift" for f in result.lint_findings)


def test_clean_file_no_findings(tmp_path):
    p = tmp_path / "clean.md"
    p.write_bytes(b"a clean line\nanother clean line\n")
    findings = lint_bytes(p.read_bytes(), str(p), Pricing.load())
    assert findings == []


def test_concat_order_flagged_for_unsorted_set(tmp_path):
    b = tmp_path / "b.md"
    a = tmp_path / "a.md"
    b.write_bytes(b"clean\n")
    a.write_bytes(b"clean\n")
    findings = run_lint([str(b), str(a)]).lint_findings  # given b before a → unsorted
    assert any(f.rule_id == "concat_order" for f in findings)
