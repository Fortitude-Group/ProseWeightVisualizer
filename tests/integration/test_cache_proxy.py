"""Integration tests for the recording reverse proxy (US1 / T015).

Fully offline: the proxy's upstream ``httpx.AsyncClient`` is injected with an
``httpx.ASGITransport`` pointed at a tiny in-process fake-upstream Starlette
app, and the proxy itself is driven the same way. No real network is used.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from proseweight.cache.core.contracts import ConfidenceGrade, SourceKind
from proseweight.cache.core.store import CacheStore
from proseweight.cache.proxy.server import create_app


def _fake_response(message_id: str) -> dict[str, Any]:
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "hi"}],
        "model": "claude-opus-5",
        "usage": {
            "input_tokens": 10,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 8000,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 8000,
                "ephemeral_1h_input_tokens": 0,
            },
        },
    }


def _make_fake_upstream() -> Starlette:
    """A canned Anthropic-shaped /v1/messages. Each call gets a fresh
    message id (the real API never repeats one) so two captures land as two
    distinct turns rather than colliding on the store's turn-id key."""
    counter = {"n": 0}

    async def messages(request: Request) -> JSONResponse:
        await request.body()
        counter["n"] += 1
        return JSONResponse(_fake_response(f"msg_test_{counter['n']}"))

    return Starlette(routes=[Route("/v1/messages", messages, methods=["POST"])])


async def _post_two(store: CacheStore, body1: bytes, body2: bytes) -> tuple[httpx.Response, httpx.Response]:
    fake_app = _make_fake_upstream()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fake_app), base_url="http://fake-upstream.local"
    ) as fake_client:
        app = create_app(store, client=fake_client)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://proxy.local"
        ) as proxy_client:
            r1 = await proxy_client.post(
                "/v1/messages", content=body1, headers={"content-type": "application/json"}
            )
            r2 = await proxy_client.post(
                "/v1/messages", content=body2, headers={"content-type": "application/json"}
            )
    return r1, r2


def test_proxy_captures_two_turns_and_passes_through(tmp_path: Path) -> None:
    store = CacheStore(tmp_path / "cache.sqlite3")

    payload1 = {"model": "claude-opus-5", "messages": [{"role": "user", "content": "Hello there."}]}
    payload2 = {"model": "claude-opus-5", "messages": [{"role": "user", "content": "Hello there!"}]}
    body1 = json.dumps(payload1).encode()
    body2 = json.dumps(payload2).encode()
    assert len(body1) == len(body2)
    assert body1 != body2  # one-byte-changed body

    r1, r2 = asyncio.run(_post_two(store, body1, body2))

    # The response returned to the caller is the fake upstream's JSON, unchanged.
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == _fake_response("msg_test_1")
    assert r2.json() == _fake_response("msg_test_2")

    assert store.turn_count() == 2

    rows = store.conn.execute("SELECT * FROM turns ORDER BY response_message_id").fetchall()
    assert len(rows) == 2

    for row, body in zip(rows, (body1, body2), strict=True):
        assert row["model_id"] == "claude-opus-5"
        assert row["confidence_grade"] == ConfidenceGrade.EXACT.value
        assert row["source_kind"] == SourceKind.API_PROXY.value
        assert row["cache_read_input_tokens"] == 8000
        assert row["cache_creation_input_tokens"] == 0
        assert row["input_tokens"] == 10
        assert row["ephemeral_5m_input_tokens"] == 8000
        assert row["ephemeral_1h_input_tokens"] == 0
        blob = store.get_blob(row["prefix_hash"])
        assert blob == body  # exact on-wire request bytes, unmodified

    store.close()
