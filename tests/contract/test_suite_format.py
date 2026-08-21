"""Contract tests for the probe-suite format + hash guard (contracts/probe-suite.md)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from proseweight.probes.quality import probe_quality
from proseweight.probes.suite import (
    SuiteError,
    canonical_hash,
    load_suite,
    parse_suite,
    signal_types_for,
)

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "data" / "suites" / "default-v1.yaml"
MANIFEST = ROOT / "data" / "suites" / "suite-versions.json"


def test_default_suite_loads_and_hash_matches_manifest():
    suite = load_suite(SUITE, MANIFEST)
    assert len(suite.probes) == 12
    assert suite.version == "1.0.0"


def test_every_shipped_probe_has_prog_check():
    suite = load_suite(SUITE)
    suite.validate_authoring()  # raises if any probe lacks a PROG check
    assert all(p.has_prog_check() for p in suite.probes)


def test_categories_spread():
    suite = load_suite(SUITE)
    cats = {p.category for p in suite.probes}
    assert cats == {"deferral", "format", "tone", "refusal", "constraint"}


def test_hash_guard_refuses_tampered_suite(tmp_path):
    cfg = {"metadata": {"suite_version": "1.0.0"}, "tests": []}
    good_hash = canonical_hash(cfg)
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"1.0.0": {"hash": good_hash}}))
    suite_file = tmp_path / "s.yaml"
    # tamper: add a probe so the content hash changes
    suite_file.write_text(
        "metadata: { suite_version: '1.0.0' }\n"
        "tests:\n  - description: X\n    metadata: { probe_id: X, category: format, signal_types: [PROG] }\n"
        "    assert:\n      - { type: is-json }\n"
    )
    with pytest.raises(SuiteError):
        load_suite(suite_file, manifest)


def test_unrecorded_version_refused(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"9.9.9": {"hash": "sha256:x"}}))
    suite_file = tmp_path / "s.yaml"
    suite_file.write_text("metadata: { suite_version: '1.0.0' }\ntests: []\n")
    with pytest.raises(SuiteError):
        load_suite(suite_file, manifest)


def test_signal_type_lookup():
    assert signal_types_for([{"type": "is-json"}, {"type": "llm-rubric"}]) == ("PROG", "JUDGE")
    assert signal_types_for([{"type": "similar"}]) == ("EMB",)


def test_byo_import_defaults_unclassified():
    cfg = {
        "tests": [
            {"description": "t1", "assert": [{"type": "regex", "value": "x"}]},
        ]
    }
    tmp = Path(__file__).parent / "_byo_tmp.yaml"
    tmp.write_text("")  # ensure file exists path handling
    suite = parse_suite(cfg, origin="byo")
    assert suite.origin == "byo"
    assert suite.probes[0].category == "unclassified"
    tmp.unlink(missing_ok=True)


def test_probe_quality_flags():
    # a saturated probe (everything passes) is flagged regardless of SNR
    q = probe_quality("P0", np.array([0.4, 0.5]), 0.05, np.array([0.99, 0.98, 1.0]))
    assert q.flag == "SATURATED"
    # low discrimination over enough runs
    q2 = probe_quality("P1", np.zeros(25) + 0.01, 0.05, np.array([0.5, 0.5]))
    assert q2.flag == "LOW_DISCRIMINATION"
