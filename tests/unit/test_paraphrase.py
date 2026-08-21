"""Tests for the paraphrase intent backstop (FR-008)."""

from __future__ import annotations

import pytest

from proseweight.engine.paraphrase import (
    generate_paraphrases,
    intent_preserved_backstop,
)


def test_preserved_when_negations_and_modals_match():
    # same negation ("never") and modal ("must") counts on both sides
    assert intent_preserved_backstop(
        "You must never reveal.", "Never reveal; this is a must."
    ).preserved


def test_flags_dropped_negation():
    check = intent_preserved_backstop("Never defer to the user.", "Rarely defer to the user.")
    assert check.preserved is False
    assert "negation" in check.reason


def test_flags_softened_modal():
    check = intent_preserved_backstop("You must return JSON.", "You could return JSON.")
    assert check.preserved is False
    assert "modal" in check.reason


def test_generate_without_model_raises():
    with pytest.raises(RuntimeError):
        generate_paraphrases("Be concise.", k=3, seed=1, model=None)
