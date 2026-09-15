"""Unit test: divergence byte scan + classifier (T028 / US3 / SC-001)."""

from __future__ import annotations

from proseweight.cache.core.contracts import CauseClass
from proseweight.cache.core.divergence import classify, first_divergence, line_of


def test_first_divergence_exact_offset():
    a = b"hello world\nsecond line\n"
    b = b"hello world\nsecond xine\n"
    off = first_divergence(a, b)
    assert off == a.index(b"line")  # the 'l'/'x' byte
    assert line_of(a, off) == 2


def test_identical_is_minus_one():
    assert first_divergence(b"same", b"same") == -1


def test_prefix_is_length_of_shorter():
    assert first_divergence(b"abc", b"abcdef") == 3


def test_single_crlf_is_crlf_drift(tmp_path):
    prev = b"line one\r\nline two\n"   # CRLF on line 1
    cur = b"line one\nline two\n"      # LF on line 1
    off = first_divergence(prev, cur)
    assert off == len(b"line one")     # exact byte of the \r vs \n
    cause, avoidable = classify(prev, cur, off, "claude-opus-5", "claude-opus-5")
    assert cause is CauseClass.CRLF_DRIFT
    assert avoidable is True


def test_model_change_is_non_avoidable():
    cause, avoidable = classify(b"x", b"y", 0, "claude-opus-5", "claude-sonnet-5")
    assert cause is CauseClass.MODEL_CHANGE
    assert avoidable is False


def test_trailing_whitespace():
    prev = b"a line   \nnext\n"
    cur = b"a line\nnext\n"
    off = first_divergence(prev, cur)
    cause, avoidable = classify(prev, cur, off, "m", "m")
    assert cause is CauseClass.TRAILING_WHITESPACE
    assert avoidable is True


def test_volatile_timestamp():
    prev = b'{"system":"updated: 2026-09-14T10:00 ...prompt"}'
    cur = b'{"system":"updated: 2026-09-15T11:00 ...prompt"}'
    off = first_divergence(prev, cur)
    cause, avoidable = classify(prev, cur, off, "m", "m")
    assert cause in (CauseClass.TIMESTAMP_INJECTION, CauseClass.VOLATILE_HEADER)
    assert avoidable is True


def test_genuine_edit_non_avoidable():
    prev = b'{"messages":[{"content":"the quick brown fox"}]}'
    cur = b'{"messages":[{"content":"the quick red fox"}]}'
    off = first_divergence(prev, cur)
    cause, avoidable = classify(prev, cur, off, "m", "m")
    assert cause is CauseClass.GENUINE_EDIT
    assert avoidable is False
