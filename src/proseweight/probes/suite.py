"""Probe-suite loader, promptfoo mapping, and the semver+sha256 hash guard.

A suite file is a valid promptfoo config. Every result records
``{suite_version, suite_hash, promptfoo_schema_ref}``. A file tagged ``vX`` that
does not hash-match the manifest is refused, not silently attributed
(contracts/probe-suite.md).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROMPTFOO_SCHEMA_REF = "0.122.0"

# promptfoo assert type -> our signal class.
_ASSERT_SIGNAL = {
    "is-json": "PROG",
    "contains": "PROG",
    "contains-all": "PROG",
    "regex": "PROG",
    "javascript": "PROG",
    "python": "PROG",
    "is-refusal": "PROG",
    "not-is-refusal": "PROG",
    "llm-rubric": "JUDGE",
    "g-eval": "JUDGE",
    "factuality": "JUDGE",
    "answer-relevance": "JUDGE",
    "similar": "EMB",
}


class SuiteError(ValueError):
    """Raised on a hash-guard mismatch or an invalid suite file."""


@dataclass(frozen=True)
class Probe:
    probe_id: str
    category: str
    vars: dict[str, Any]
    signal_types: tuple[str, ...]
    assertions: tuple = ()  # raw promptfoo assert dicts, for real check/judge use

    def has_prog_check(self) -> bool:
        return "PROG" in self.signal_types

    @property
    def task(self) -> str:
        return str(self.vars.get("task", ""))

    @property
    def judge_criteria(self) -> list[str]:
        """The llm-rubric criterion strings (what the judge actually scores)."""
        return [str(a.get("value", "")) for a in self.assertions if a.get("type") == "llm-rubric"]

    @property
    def prog_assertions(self) -> list[dict]:
        """Python-runnable programmatic assertions (excludes file:// js/py checks)."""
        out = []
        for a in self.assertions:
            t = a.get("type", "")
            base = t[4:] if t.startswith("not-") else t
            if base in ("is-json", "is-refusal", "contains", "contains-all", "regex"):
                out.append(a)
        return out


@dataclass
class ProbeSuite:
    version: str
    content_hash: str
    probes: list[Probe]
    origin: str = "shipped"  # shipped | byo
    promptfoo_schema_ref: str = PROMPTFOO_SCHEMA_REF

    def validate_authoring(self) -> None:
        """Every shipped probe must carry >=1 weak PROG check (FR-006c)."""
        if self.origin != "shipped":
            return
        missing = [p.probe_id for p in self.probes if not p.has_prog_check()]
        if missing:
            raise SuiteError(
                f"shipped probes missing a required PROG check: {missing} "
                "(needed so the fixed blend stays uniform)"
            )


def canonical_hash(config: dict[str, Any]) -> str:
    """sha256 over a canonicalised serialisation (stable key order)."""
    blob = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def signal_types_for(assertions: list[dict[str, Any]]) -> tuple[str, ...]:
    seen = []
    for a in assertions:
        sig = _ASSERT_SIGNAL.get(a.get("type", ""))
        if sig and sig not in seen:
            seen.append(sig)
    return tuple(seen)


def parse_suite(config: dict[str, Any], origin: str = "shipped") -> ProbeSuite:
    meta = config.get("metadata", {}) or {}
    version = str(meta.get("suite_version", "0.0.0"))
    probes: list[Probe] = []
    for test in config.get("tests", []) or []:
        tmeta = test.get("metadata", {}) or {}
        pid = tmeta.get("probe_id") or test.get("description", f"P{len(probes) + 1:02d}")
        category = tmeta.get("category", "unclassified")
        assertions = test.get("assert", []) or []
        sigs = tuple(tmeta.get("signal_types", ())) or signal_types_for(assertions)
        probes.append(Probe(pid, category, test.get("vars", {}) or {}, sigs, tuple(assertions)))
    return ProbeSuite(
        version=version,
        content_hash=canonical_hash(config),
        probes=probes,
        origin=origin,
    )


def load_suite(path: str | Path, manifest_path: str | Path | None = None) -> ProbeSuite:
    """Load a suite YAML and enforce the hash guard against the manifest."""
    path = Path(path)
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    suite = parse_suite(config, origin="shipped")
    suite.validate_authoring()
    if manifest_path is not None:
        _enforce_hash_guard(suite, Path(manifest_path))
    return suite


def load_byo_suite(path: str | Path) -> ProbeSuite:
    """Import a user's promptfoo suite. Probes default to category=unclassified."""
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return parse_suite(config, origin="byo")


def _enforce_hash_guard(suite: ProbeSuite, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = manifest.get(suite.version)
    if recorded is None:
        raise SuiteError(
            f"suite version {suite.version} is not in the manifest; refuse to "
            "attribute results to an unrecorded version"
        )
    if recorded.get("hash") != suite.content_hash:
        raise SuiteError(
            f"suite tagged {suite.version} does not hash-match the manifest "
            f"(file={suite.content_hash}, manifest={recorded.get('hash')})"
        )
