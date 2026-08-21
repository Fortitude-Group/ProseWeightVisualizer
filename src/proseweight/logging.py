"""Structured logging (Principle IV observability).

A thin wrapper over the stdlib so every meaningful operation emits a traceable,
structured record. Secrets are never passed here.
"""

from __future__ import annotations

import json
import logging
import sys

_CONFIGURED = False


def get_logger(name: str = "proseweight") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root = logging.getLogger("proseweight")
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        _CONFIGURED = True
    return logging.getLogger(name)


def event(logger: logging.Logger, name: str, **fields) -> None:
    """Emit a structured event line. Callers must not pass secrets in fields."""
    logger.info("%s %s", name, json.dumps(fields, default=str, sort_keys=True))
