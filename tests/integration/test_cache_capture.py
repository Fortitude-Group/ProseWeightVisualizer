"""US1 integration (T020): both capture paths into one store, and no off-machine egress.

The proxy is driven entirely in-process against a fake upstream ASGI app (via
httpx.ASGITransport), so the test proves capture works AND that traffic reaches only
the injected upstream — nothing leaves the machine (SC-005). The transcript path is
exercised alongside it into the same store, matching US1's Independent Test.
"""

from __future__ import annotations

import asyncio
import itertools
import json

import httpx

from proseweight.cache.core.store import CacheStore
from proseweight.cache.ingest.claude_code import ingest_transcript
from proseweight.cache.proxy.server import create_app

_seq = itertools.count(1)


def _fake_upstream() -> tuple[httpx.AsyncClient, dict[str, int]]:
    """An in-process Anthropic-shaped upstream. Returns a client bound to it plus a
    hit-counter proving all traffic terminated here (no real network)."""
    hits = {"count": 0}

    async def app(scope, receive, send):  # minimal ASGI
        assert scope["type"] == "http"
        # drain the request body
        more = True
        while more:
            msg = await receive()
            more = msg.get("more_body", False)
        hits["count"] += 1
        n = next(_seq)
        body = json.dumps({
            "id": f"msg_test_{n}", "type": "message", "role": "assistant",
            "model": "claude-opus-5", "content": [{"type": "text", "text": "ok"}],
            "usage": {
                "input_tokens": 10, "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 8000,
                "cache_creation": {"ephemeral_5m_input_tokens": 8000, "ephemeral_1h_input_tokens": 0},
            },
        }).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})

    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://upstream")
    return client, hits


def _synthetic_transcript(path) -> None:
    def line(mid, ts):
        return json.dumps({
            "type": "assistant", "timestamp": ts,
            "message": {"model": "claude-opus-5", "id": mid, "role": "assistant",
                        "content": [{"type": "text", "text": "hi"}],
                        "usage": {"input_tokens": 5, "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": 100,
                                  "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}}},
        })
    user = json.dumps({"type": "user", "timestamp": "2026-09-14T09:59:00Z", "message": {"role": "user"}})
    path.write_text(
        line("msg_t1", "2026-09-14T10:00:00Z") + "\n" + user + "\n" + line("msg_t2", "2026-09-14T10:01:00Z") + "\n",
        encoding="utf-8",
    )


def test_both_capture_paths_into_one_store_no_egress(tmp_path):
    store = CacheStore(tmp_path / "cache.db")
    client, hits = _fake_upstream()
    proxy = create_app(store, client=client)

    # --- proxy path: two requests, same prefix, one-byte change ---
    # Drive the proxy in-loop (single thread) so the store's connection stays on
    # its creating thread — mirrors production (uvicorn serves on one event loop).
    async def _drive() -> tuple[int, int, dict]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy), base_url="http://proxy"
        ) as tc:
            r1 = await tc.post("/v1/messages", content=b'{"model":"claude-opus-5","messages":[{"role":"user","content":"A"}]}')
            r2 = await tc.post("/v1/messages", content=b'{"model":"claude-opus-5","messages":[{"role":"user","content":"B"}]}')
            return r1.status_code, r2.status_code, r1.json()

    s1, s2, r1_json = asyncio.run(_drive())
    assert s1 == 200 and s2 == 200
    assert r1_json["usage"]["cache_read_input_tokens"] == 8000  # transparent pass-through

    # --- transcript path into the SAME store ---
    tpath = tmp_path / "session.jsonl"
    _synthetic_transcript(tpath)
    ids = ingest_transcript(tpath, store)
    assert len(ids) == 2

    # --- assertions: both sources present with the right grades ---
    rows = store.conn.execute("SELECT source_kind, confidence_grade FROM turns").fetchall()
    grades = {(r["source_kind"], r["confidence_grade"]) for r in rows}
    assert ("api_proxy", "exact") in grades
    assert ("claude_code_transcript", "reconstructed_low") in grades
    assert store.turn_count() == 4  # 2 proxy + 2 transcript

    # --- no egress: every proxied request terminated at the in-process fake upstream ---
    assert hits["count"] == 2
    store.close()
