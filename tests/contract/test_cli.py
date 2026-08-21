"""Contract tests for the CLI surface (contracts/cli.md)."""

from __future__ import annotations

from typer.testing import CliRunner

from proseweight.cli.main import app

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.output
    assert "export" in result.output


def test_scan_help_has_flags():
    result = runner.invoke(app, ["scan", "--help"])
    assert result.exit_code == 0
    for flag in ("--depth", "--seed", "--model", "--judge", "--json"):
        assert flag in result.output


def test_scan_without_runtime_errors_cleanly(tmp_path):
    p = tmp_path / "prompt.md"
    p.write_text("Never defer. Be concise.\n", encoding="utf-8")
    result = runner.invoke(app, ["scan", str(p)])
    # segmentation runs; the model backend raises a clear runtime error
    assert "Segmented into" in result.output
    assert result.exit_code != 0
    assert "runtime" in str(result.exception).lower()
