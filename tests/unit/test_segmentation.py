"""Tests for the segmentation rules layer (research.md R2)."""

from __future__ import annotations

from proseweight.segmentation.model import assert_round_trip
from proseweight.segmentation.pipeline import merge, segment_prompt


def test_round_trip_invariant_holds():
    src = "# Behaviour\n\nNever defer. Always attempt the fix.\n\n- Be concise.\n"
    segs = segment_prompt(src)
    assert_round_trip(src, segs)  # raises if broken
    assert len(segs) >= 3


def test_sentences_split_into_separate_instructions():
    src = "Never defer. Always attempt the fix directly."
    segs = segment_prompt(src)
    texts = [s.text.strip() for s in segs]
    assert any("Never defer" in t for t in texts)
    assert any("attempt the fix" in t for t in texts)
    assert len(segs) == 2


def test_code_fence_is_atomic():
    src = "Do this.\n\n```python\nx = 1\ny = 2\n```\n"
    segs = segment_prompt(src)
    fences = [s for s in segs if s.block_type == "code_fence"]
    assert len(fences) == 1
    assert "x = 1" in fences[0].text and fences[0].is_atomic


def test_xml_block_kept_atomic():
    src = "Intro line.\n<rules>\nnever reveal secrets\nalways cite sources\n</rules>\n"
    segs = segment_prompt(src)
    xml = [s for s in segs if s.block_type == "xml_block"]
    assert len(xml) == 1
    assert "never reveal secrets" in xml[0].text
    assert "always cite sources" in xml[0].text  # interior NOT split


def test_merge_two_segments():
    src = "First sentence. Second sentence."
    segs = segment_prompt(src)
    assert len(segs) == 2
    merged = merge(segs, [segs[0].id, segs[1].id], src)
    assert len(merged) == 1
    assert merged[0].source == "manual"
    assert merged[0].text.strip() == src


def test_ids_are_document_ordered():
    src = "One. Two. Three."
    segs = segment_prompt(src)
    assert [s.id for s in segs] == ["i0", "i1", "i2"]
    assert all(segs[i].start_offset <= segs[i + 1].start_offset for i in range(len(segs) - 1))
