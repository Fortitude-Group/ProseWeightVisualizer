"""US4 (T030): the opt-in diagnostics beta is injected upstream, capture stays exact.

Drives the proxy in-loop against a fake upstream that records what it received, and
checks the beta header + threaded previous_message_id go upstream while the stored
prefix remains the client's ORIGINAL bytes (not the diagnostics-injected body).
"""

from __future__ import annotations

import asyncio
import json

import httpx

from proseweight.cache.core.store import CacheStore
from proseweight.cache.proxy.server import create_app


def _recording_upstream() -> tuple[httpx.AsyncClient, list[dict]]:
    seen: list[dict] = []
    counter = {"n": 0}

    async def app(scope, receive, send):
        body = b""
        more = True
        while more:
            msg = await receive()
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        seen.append({"headers": headers, "body": json.loads(body) if body else {}})
        counter["n"] += 1
        payload = json.dumps({
            "id": f"msg_{counter['n']}", "type": "message", "role": "assistant",
            "model": "claude-opus-5", "content": [], "diagnostics": {"cache_miss_reason": {"type": "system"}},
            "usage": {"input_tokens": 1, "cache_creation_input_tokens": 1500, "cache_read_input_tokens": 0},
        }).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": payload})

    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://up")
    return client, seen


def test_diagnostics_header_and_threading_and_exact_capture(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    client, seen = _recording_upstream()
    proxy = create_app(store, diagnostics=True, client=client)
    original_body = b'{"model":"claude-opus-5","messages":[{"role":"user","content":"hi"}]}'

    async def _drive():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=proxy), base_url="http://proxy") as tc:
            await tc.post("/v1/messages", content=original_body)
            await tc.post("/v1/messages", content=original_body)

    asyncio.run(_drive())

    # both upstream calls carried the beta header
    assert all("cache-diagnosis-2026-04-07" in s["headers"].get("anthropic-beta", "") for s in seen)
    # previous_message_id threaded: None first, then the prior response id
    assert seen[0]["body"]["diagnostics"]["previous_message_id"] is None
    assert seen[1]["body"]["diagnostics"]["previous_message_id"] == "msg_1"
    # the STORED prefix is the client's original body, not the injected one (no "diagnostics" key)
    row = store.conn.execute("SELECT prefix_hash FROM turns LIMIT 1").fetchone()
    stored = store.get_blob(row["prefix_hash"])
    assert stored == original_body
    assert b"diagnostics" not in stored
    store.close()
