"""Tests for the programmatic check runner (PROG signal)."""

from __future__ import annotations

from proseweight.probes.checks import (
    is_json,
    is_refusal,
    non_empty,
    run_check,
    sentence_count,
    word_count,
)


def test_is_json():
    assert is_json('{"a": 1}') is True
    assert is_json("not json") is False
    assert is_json('  {"x": [1,2]} ') is True


def test_is_refusal_heuristic():
    assert is_refusal("I'm sorry, but I can't help with that.") is True
    assert is_refusal("Here is how you do it: ...") is False
    assert is_refusal("Please consult a doctor for a dosage.") is True


def test_run_check_is_json():
    assert run_check({"type": "is-json"}, '{"a":1}') == 1.0
    assert run_check({"type": "is-json"}, "nope") == 0.0


def test_run_check_negation():
    # not-is-refusal: satisfied when the output is NOT a refusal
    assert run_check({"type": "not-is-refusal"}, "Here's the answer.") == 1.0
    assert run_check({"type": "not-is-refusal"}, "I cannot help with that.") == 0.0


def test_run_check_regex_and_contains():
    assert run_check({"type": "regex", "value": r"\d{3}"}, "abc 123") == 1.0
    assert run_check({"type": "contains", "value": "durable"}, "a durable boot") == 1.0
    assert run_check({"type": "contains-all", "value": ["a", "b"]}, "a and b") == 1.0
    assert run_check({"type": "contains-all", "value": ["a", "z"]}, "a and b") == 0.0


def test_javascript_check_needs_runtime():
    assert run_check({"type": "javascript", "value": "file://x.js"}, "out") is None


def test_counts_and_non_empty():
    assert word_count("one two three") == 3
    assert sentence_count("One. Two! Three?") == 3
    assert non_empty("x") == 1.0
    assert non_empty("   ") == 0.0
