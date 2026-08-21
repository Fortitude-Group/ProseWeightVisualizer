"""End-to-end CLI tests for the model-free commands: export, diff, lint."""

from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _builders import make_verdict  # noqa: E402
from proseweight.ci.lint import Baseline  # noqa: E402
from proseweight.cli.main import app  # noqa: E402

runner = CliRunner()


def _save(verdict, tmp_path, name):
    import json

    p = tmp_path / name
    p.write_text(json.dumps(verdict.to_dict(), indent=2), encoding="utf-8")
    return p


def test_export_writes_html_and_png(tmp_path):
    v = make_verdict([("Never defer.", 90, 0.99), ("Be nice.", 3, 0.7)])
    rp = _save(v, tmp_path, "v.json")
    res = runner.invoke(
        app, ["export", str(rp), "--html", str(tmp_path / "o.html"), "--png", str(tmp_path / "o.png")]
    )
    assert res.exit_code == 0
    assert (tmp_path / "o.html").exists()
    assert (tmp_path / "o.png").exists()
    assert "below the noise floor" in (tmp_path / "o.html").read_text(encoding="utf-8")


def test_diff_reports_regression(tmp_path):
    v1 = make_verdict([("Never defer.", 90, 0.99)])
    v2 = make_verdict([("Never defer.", 60, 0.99)])
    p1, p2 = _save(v1, tmp_path, "v1.json"), _save(v2, tmp_path, "v2.json")
    res = runner.invoke(app, ["diff", str(p1), str(p2)])
    assert res.exit_code == 0
    assert "1 regression" in res.output


def test_lint_exit_codes(tmp_path):
    base_v = make_verdict([("Never defer.", 90, 0.99), ("Be brief.", 40, 0.99)])
    base = Baseline.from_verdict(base_v, "CLAUDE.md")
    base.save(tmp_path / "weights.json")

    benign = _save(make_verdict([("Never defer.", 88, 0.99), ("Be brief.", 41, 0.99)]), tmp_path, "ok.json")
    assert runner.invoke(app, ["lint", str(benign), "--baseline", str(tmp_path / "weights.json")]).exit_code == 0

    regressed = _save(make_verdict([("Never defer.", 60, 0.99), ("Be brief.", 40, 0.99)]), tmp_path, "bad.json")
    r = runner.invoke(app, ["lint", str(regressed), "--baseline", str(tmp_path / "weights.json")])
    assert r.exit_code == 1
    assert "regression" in r.output
