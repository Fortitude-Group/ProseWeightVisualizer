"""Watch-mode local HTTP API (US13 / FR-032, contracts/api.md).

Minimal, loopback, single-tenant. ``/health`` and ``/segment`` are fully
functional without model weights; ``/weight`` and ``/scan`` require the runtime
backend and return a clear error otherwise. The ANTHROPIC_API_KEY is read from
the server environment only and is never accepted in a request body.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from proseweight.report.schema import SCHEMA_VERSION
from proseweight.segmentation.pipeline import segment_prompt


class SegmentRequest(BaseModel):
    text: str


class WeightRequest(BaseModel):
    text: str
    instruction_id: str
    model: str | None = None
    suite: str = "default-v1"
    depth: str = "quick_scan"
    seed: int = 0


def create_app() -> FastAPI:
    app = FastAPI(title="proseweight", version=SCHEMA_VERSION)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "engine_version": "0.1.0", "schema_version": SCHEMA_VERSION}

    @app.post("/segment")
    def segment(req: SegmentRequest) -> dict[str, Any]:
        segs = segment_prompt(req.text)
        return {
            "instructions": [
                {
                    "id": s.id,
                    "text": s.text,
                    "start_offset": s.start_offset,
                    "end_offset": s.end_offset,
                    "block_type": s.block_type,
                }
                for s in segs
            ]
        }

    @app.post("/weight")
    def weight(req: WeightRequest) -> dict[str, Any]:
        # Requires the model runtime; surfaces a clear 409 rather than hanging.
        raise HTTPException(
            status_code=409,
            detail="model runtime not available; install proseweight[runtime] and load weights",
        )

    return app


app = create_app()
