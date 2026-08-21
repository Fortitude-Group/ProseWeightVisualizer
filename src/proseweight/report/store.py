"""Per-model result storage (T008 / data-model.md).

Verdicts are stored per model so the Release-2 grid can hold several side by side:
``<root>/results/<model-slug>/<run_id>/verdict.json``. Single-tenant, local files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from proseweight.report.schema import Verdict
from proseweight.report.serde import verdict_from_dict


def model_slug(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model_id).strip("-").lower()


def verdict_path(root: str | Path, verdict: Verdict) -> Path:
    slug = model_slug(verdict.run.subject_model.model_id)
    return Path(root) / "results" / slug / verdict.run.run_id / "verdict.json"


def save_verdict(verdict: Verdict, root: str | Path) -> Path:
    verdict.validate()
    out = verdict_path(root, verdict)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(verdict.to_dict(), indent=2), encoding="utf-8")
    return out


def load_verdict(path: str | Path) -> Verdict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    v = verdict_from_dict(d)
    v.validate()
    return v
