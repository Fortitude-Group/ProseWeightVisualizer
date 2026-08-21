# Single entry point: install the deterministic core, lint, and test.
# The model runtime (torch/transformers/etc.) is the optional [runtime] extra and
# is not required for the core test suite.
$ErrorActionPreference = "Stop"
$py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -m pip install -e . -q
& $py -m ruff check src tests
& $py -m pytest -q
