"""Unit test: Pricing (T011) — non-monotonic minimums, per-model read rate, stamps."""

from __future__ import annotations

from proseweight.cache.core.pricing import DEFAULT_TABLE, Pricing


def test_non_monotonic_minimums_preserved():
    p = Pricing.load()
    assert p.for_model("claude-opus-5").min_cacheable_tokens == 512
    assert p.for_model("claude-opus-4-8").min_cacheable_tokens == 1024
    assert p.for_model("claude-opus-4-7").min_cacheable_tokens == 2048
    assert p.for_model("claude-opus-4-6").min_cacheable_tokens == 4096  # non-monotonic vs 4-7/4-8


def test_per_model_read_multiplier():
    p = Pricing.load()
    assert p.for_model("claude-opus-5").read_mult == 0.1
    assert p.for_model("claude-fable-5-1").read_mult == 0.025  # not a global constant


def test_unknown_model_falls_back():
    p = Pricing.load()
    mp = p.for_model("some-future-model")
    assert mp.min_cacheable_tokens == p.for_model(DEFAULT_TABLE["fallback_model"]).min_cacheable_tokens


def test_stamp_present():
    stamp = Pricing.load().stamp()
    assert stamp.pricing_version and stamp.effective_date and stamp.fx_date


def test_edit_reflected(tmp_path):
    import json

    t = dict(DEFAULT_TABLE)
    t["usd_gbp"] = 0.5
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(t), encoding="utf-8")
    assert Pricing.load(path).usd_gbp == 0.5


def test_waste_formula_gbp():
    p = Pricing.load()
    mp = p.for_model("claude-opus-5")
    # 1M recomputed tokens, opus-5 ($5/MTok, 1.25 write, 0.1 read), fx 0.79
    # 1 * 5 * (1.25-0.1) * 0.79 = 4.5425
    assert abs(mp.waste_gbp(1_000_000, 0.79) - 4.5425) < 1e-6
