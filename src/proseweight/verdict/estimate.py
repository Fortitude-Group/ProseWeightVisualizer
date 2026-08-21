"""Pre-run time/cost estimate (FR-019 / T034).

Shown before a run starts so the user can drop to quick scan or trim the suite
rather than discovering the cost afterwards. Quick scan ablates only the top
attention-pre-screened candidates; deep audit ablates every instruction N times.
"""

from __future__ import annotations

from dataclasses import dataclass

# rough per-probe subject+judge forward-pass wall time (seconds), consumer GPU.
DEFAULT_PER_PROBE_SECONDS = 1.2
QUICK_CANDIDATE_FRACTION = 0.3  # quick scan ablates ~top 30% of instructions


@dataclass
class RunEstimate:
    conditions: int  # number of (instruction-ablation) conditions run
    total_probe_runs: int
    seconds: float
    note: str

    @property
    def minutes(self) -> float:
        return self.seconds / 60.0

    def human(self) -> str:
        return f"~{self.minutes:.1f} min ({self.total_probe_runs} probe runs) — {self.note}"


def estimate_run(
    n_instructions: int,
    n_probes: int,
    depth: str,
    n_runs: int,
    per_probe_seconds: float = DEFAULT_PER_PROBE_SECONDS,
) -> RunEstimate:
    if depth == "deep_audit":
        conditions = n_instructions
        reps = n_runs
        note = f"deep audit: every instruction x {n_runs} runs"
    else:  # quick_scan
        conditions = max(1, round(n_instructions * QUICK_CANDIDATE_FRACTION))
        reps = 1
        note = "quick scan: attention-pre-screened top candidates only"
    # +1 baseline (full prompt) condition
    total_probe_runs = (conditions + 1) * n_probes * reps
    seconds = total_probe_runs * per_probe_seconds
    return RunEstimate(conditions, total_probe_runs, seconds, note)
