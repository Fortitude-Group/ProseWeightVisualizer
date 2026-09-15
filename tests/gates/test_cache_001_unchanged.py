"""Gate (T014 / SC-009 / FR-029): CacheScope is additive and non-breaking to `001`.

The full `001` suite passing under `pytest` is the primary SC-009 evidence; this gate
adds fast canaries: the `001` report contract is untouched (version + key symbols),
and importing the CacheScope core does not drag in the heavy model runtime — proof the
core is light and decoupled.
"""

from __future__ import annotations

import sys


def test_001_report_contract_untouched():
    from proseweight.report import schema

    # canary: a change here would mean the 001 contract was modified
    assert schema.SCHEMA_VERSION == "1.0.0"
    for symbol in ("Verdict", "Classification", "RunMeta", "WeightScore"):
        assert hasattr(schema, symbol), f"001 report schema lost {symbol}"


def test_cache_core_does_not_import_model_runtime():
    # importing the core must not pull torch/transformers/gradio (heavy 001 runtime extras)
    for heavy in ("torch", "transformers", "gradio"):
        sys.modules.pop(heavy, None)
    import importlib

    importlib.import_module("proseweight.cache.core.api")
    importlib.import_module("proseweight.cache.core.lint")
    for heavy in ("torch", "transformers", "gradio"):
        assert heavy not in sys.modules, f"cache core unexpectedly imported {heavy}"
