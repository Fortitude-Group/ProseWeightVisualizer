"""Tests for per-model result storage + verdict (de)serialization (T008)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _builders import make_verdict  # noqa: E402
from proseweight.report.serde import verdict_from_dict  # noqa: E402
from proseweight.report.store import load_verdict, model_slug, save_verdict  # noqa: E402


def test_verdict_dict_roundtrip():
    v = make_verdict([("Never defer.", 90, 0.99), ("Be nice.", 20, 0.80)])
    again = verdict_from_dict(v.to_dict())
    assert again.to_dict() == v.to_dict()


def test_save_and_load_verdict(tmp_path):
    v = make_verdict([("X.", 80, 0.99)], run_id="r42")
    path = save_verdict(v, tmp_path)
    assert path.exists()
    assert model_slug("Qwen/Qwen2.5-1.5B-Instruct") in str(path)
    loaded = load_verdict(path)
    assert loaded.to_dict() == v.to_dict()


def test_per_model_paths_are_separate(tmp_path):
    a = make_verdict([("X.", 80, 0.99)], model="Qwen/Qwen2.5-0.5B-Instruct", run_id="r1")
    b = make_verdict([("X.", 80, 0.99)], model="meta-llama/Llama-3.2-1B-Instruct", run_id="r1")
    pa = save_verdict(a, tmp_path)
    pb = save_verdict(b, tmp_path)
    assert pa != pb
    assert pa.parent.parent != pb.parent.parent  # different model dirs
