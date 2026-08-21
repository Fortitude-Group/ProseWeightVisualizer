"""Tests for deterministic RNG plumbing (FR-017)."""

from __future__ import annotations

from proseweight.engine.determinism import child_generators, named_generator


def test_child_generators_reproducible():
    a = [g.random(3).tolist() for g in child_generators(42, 4)]
    b = [g.random(3).tolist() for g in child_generators(42, 4)]
    assert a == b


def test_child_generators_independent_streams():
    gens = child_generators(42, 2)
    assert gens[0].random(5).tolist() != gens[1].random(5).tolist()


def test_named_generator_stable_and_distinct():
    assert named_generator(1, "judge").random(3).tolist() == (
        named_generator(1, "judge").random(3).tolist()
    )
    assert named_generator(1, "judge").random(3).tolist() != (
        named_generator(1, "embed").random(3).tolist()
    )
