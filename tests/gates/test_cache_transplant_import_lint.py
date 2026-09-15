"""Gate (T013 / SC-008 / FR-027): the transplantable core imports nothing forbidden.

`cache/core/` must not import the `001` weight linter nor any CacheScope adapter, so
the cost core can be lifted into OmnisVigil behind its contracts without modification.
Enforced by an AST scan — a forbidden import fails the build.
"""

from __future__ import annotations

import ast
from pathlib import Path

_CORE = Path(__file__).resolve().parents[2] / "src" / "proseweight" / "cache" / "core"

_FORBIDDEN_PREFIXES = (
    "proseweight.verdict",
    "proseweight.stats",
    "proseweight.report",       # rendering (incl. brand) is an adapter, never the core
    "proseweight.web",
    "proseweight.engine",
    "proseweight.segmentation",
    "proseweight.duel",
    "proseweight.grid",
    "proseweight.diff",
    "proseweight.decay",
    "proseweight.judge",
    "proseweight.probes",
    "proseweight.models",
    # CacheScope's own adapters must not be imported by the core
    "proseweight.cache.proxy",
    "proseweight.cache.ingest",
    "proseweight.cache.report",
    "proseweight.cache.ci",
    "proseweight.cache.cli",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                mods.add(node.module)
    return mods


def test_core_has_no_forbidden_imports():
    offenders: list[str] = []
    for py in _CORE.rglob("*.py"):
        for mod in _imported_modules(py):
            if any(mod == p or mod.startswith(p + ".") for p in _FORBIDDEN_PREFIXES):
                offenders.append(f"{py.name}: imports {mod}")
    assert not offenders, "transplant boundary violated (FR-027):\n" + "\n".join(offenders)


def test_core_files_present():
    names = {p.stem for p in _CORE.glob("*.py")}
    assert {"contracts", "store", "pricing", "lint", "api"} <= names
