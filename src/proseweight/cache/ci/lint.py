"""CI cache-lint gate (US8 / FR-025): fail a commit that makes a file cache-hostile.

A consumer of the static lint (``cache.core.lint``); not part of the core. Compares
the current findings for the target files against a checked-in baseline and fails the
build when a NEW cache-hostile finding appears, with the estimated monthly cost of the
regression in the message.

Exit codes (contracts/cli.md):
  0  no new cache-hostile findings
  1  a regression — new finding(s); message names them and the estimated monthly £
  2  usage/config error (raised by the caller)
  3  pricing/model mismatch vs the baseline — a confound, reported distinctly, never
     a false regression or a silent pass
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from proseweight.cache.core.contracts import LintFinding
from proseweight.cache.core.pricing import Pricing

BASELINE_VERSION = "1.0.0"


def _sig(f: LintFinding) -> str:
    return f"{f.rule_id}:{f.file}:{f.line}"


def make_baseline(findings: list[LintFinding], model: str, pricing: Pricing) -> dict:
    stamp = pricing.stamp()
    return {
        "baseline_version": BASELINE_VERSION,
        "model": model,
        "pricing_version": stamp.pricing_version,
        "signatures": sorted(_sig(f) for f in findings),
    }


@dataclass
class GateResult:
    exit_code: int
    messages: list[str]

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def run_gate(
    current: list[LintFinding], baseline: dict, model: str, pricing: Pricing
) -> GateResult:
    stamp = pricing.stamp()
    # Confound: a different pricing version or model makes any comparison apples-to-oranges.
    if baseline.get("pricing_version") != stamp.pricing_version or baseline.get("model") != model:
        return GateResult(
            3,
            [
                "Baseline scoping mismatch (confound, not a regression):",
                f"  baseline pricing/model = {baseline.get('pricing_version')}/{baseline.get('model')}",
                f"  current  pricing/model = {stamp.pricing_version}/{model}",
                "  Re-baseline with --update-baseline once the pricing/model is settled.",
            ],
        )
    known = set(baseline.get("signatures", []))
    new = [f for f in current if _sig(f) not in known]
    if not new:
        return GateResult(0, [f"OK: no new cache-hostile findings ({len(current)} known, within baseline)."])
    total = round(sum(f.estimated_monthly_gbp for f in new), 2)
    msgs = [f"FAILED: {len(new)} new cache-hostile finding(s), est £{total:.2f}/month:"]
    msgs += [f"  {f.rule_id}  {f.file}:{f.line}  (est £{f.estimated_monthly_gbp:.2f}/mo)" for f in new]
    return GateResult(1, msgs)


def load_baseline(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_baseline(path: str | Path, baseline: dict) -> None:
    Path(path).write_text(json.dumps(baseline, indent=2), encoding="utf-8")
