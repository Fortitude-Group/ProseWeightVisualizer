"""CacheScope transplantable core (FR-027).

This package MUST NOT import from the ``001`` weight linter
(``proseweight.{verdict,stats,report.brand,web,engine,segmentation}``) nor from
any CacheScope adapter (``proxy``, ``ingest``, ``report``, ``ci``). The boundary
is asserted by ``tests/gates/test_cache_transplant_import_lint.py`` (SC-008).

The only public surface is :mod:`proseweight.cache.core.api`.
"""
