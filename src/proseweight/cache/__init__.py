"""CacheScope — the empirical prompt-cache profiler (feature 002).

A sibling of the ``001`` weight linter. Captures real Claude traffic locally,
byte-diffs why each cache miss happened within a cache lineage, maps it onto
Anthropic's real breakpoints, reconciles prediction against measured usage, and
prices the avoidable waste.

The transplantable engine lives in :mod:`proseweight.cache.core` and imports
nothing from the ``001`` weight linter (FR-027); everything else is a consumer
of its two versioned contracts.
"""
