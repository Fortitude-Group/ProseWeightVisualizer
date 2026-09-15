"""Contract test: CacheScopeResult (T007) — the output boundary guarantees (SC-002/003/006)."""

from __future__ import annotations

import pytest

from proseweight.cache.core.contracts import (
    BillingModel,
    CacheScopeResult,
    ContractError,
    LintFinding,
    LintFraming,
    PricingStamp,
)


def _stamp() -> PricingStamp:
    return PricingStamp("2026-09", "2026-09-01", "2026-09-01", 0.79)


def _result(**kw) -> CacheScopeResult:
    base = dict(pricing=_stamp(), generated_at="2026-09-14T10:00:00Z")
    base.update(kw)
    return CacheScopeResult(**base)


def test_result_stamped_and_valid_empty():
    _result().validate()  # a bare result with the pricing stamp validates


def test_lint_finding_must_be_prediction():
    f = LintFinding("crlf_drift", "CLAUDE.md", 1, 0, 1.0, "2026-09", "2026-09-01", "2026-09-01")
    assert f.framing is LintFraming.PREDICTION
    f.framing = LintFraming("prediction")
    _result(lint_findings=[f]).validate()


def test_subscription_attribution_must_be_shadow_price():
    attr = {
        "divergence_id": "div_1", "billing_model": BillingModel.SUBSCRIPTION.value,
        "wasted_tokens": 100, "wasted_gbp": 4.12, "is_shadow_price": False,
        "pricing_version": "2026-09", "effective_date": "2026-09-01", "fx_date": "2026-09-01",
    }
    with pytest.raises(ContractError):
        _result(attributions=[attr]).validate()


def test_attribution_must_be_stamped():
    attr = {
        "divergence_id": "div_1", "billing_model": BillingModel.PAYG.value,
        "wasted_tokens": 100, "wasted_gbp": 4.12, "is_shadow_price": False,
        "pricing_version": "", "effective_date": "2026-09-01", "fx_date": "2026-09-01",
    }
    with pytest.raises(ContractError):
        _result(attributions=[attr]).validate()


def test_roundtrip():
    f = LintFinding("crlf_drift", "CLAUDE.md", 1, 0, 1.0, "2026-09", "2026-09-01", "2026-09-01")
    r = _result(lint_findings=[f]).validate()
    back = CacheScopeResult.from_dict(r.to_dict()).validate()
    assert back.result_version == "1.0.0"
    assert back.lint_findings[0].rule_id == "crlf_drift"
