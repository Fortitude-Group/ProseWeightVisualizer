"""Local base-URL recording reverse proxy (US1).

A self-contained consumer of the ``cache.core`` contracts: it sits in front of
the real Anthropic API, forwards every request/response byte-for-byte, and —
for ``POST /v1/messages`` that succeed — captures the exact on-wire request
body plus the response's usage block as a :class:`CaptureIngestionRecord`
(``source_kind=API_PROXY``, ``confidence_grade=EXACT``, FR-004).

Capture is best-effort and must never break the proxied response: failures
are swallowed after logging, and the client always gets the upstream's
status, headers, and body unchanged.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from proseweight.cache.core import api
from proseweight.cache.core.contracts import (
    CaptureIngestionRecord,
    ConfidenceGrade,
    SourceKind,
    Usage,
)
from proseweight.cache.core.store import CacheStore

logger = logging.getLogger(__name__)

# Headers that are per-hop, not per-resource — never forwarded either direction.
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def _filtered_headers(headers: Headers | httpx.Headers, *, drop: set[str]) -> list[tuple[str, str]]:
    return [(k, v) for k, v in headers.items() if k.lower() not in drop]


def _safe_json(data: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(data)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _opt_int(v: Any) -> int | None:
    return None if v is None else int(v)


def _usage_from_dict(u: dict[str, Any]) -> Usage:
    cache_creation = u.get("cache_creation") or {}
    return Usage(
        input_tokens=int(u.get("input_tokens", 0)),
        cache_creation_input_tokens=int(u.get("cache_creation_input_tokens", 0)),
        cache_read_input_tokens=int(u.get("cache_read_input_tokens", 0)),
        ephemeral_5m_input_tokens=_opt_int(cache_creation.get("ephemeral_5m_input_tokens")),
        ephemeral_1h_input_tokens=_opt_int(cache_creation.get("ephemeral_1h_input_tokens")),
    )


def _capture(
    *,
    store: CacheStore,
    prefix_bytes: bytes,
    model_id: str | None,
    usage_dict: dict[str, Any] | None,
    response_message_id: str | None,
    diagnostics: dict[str, Any] | None,
) -> None:
    """Build and ingest a capture record. Never raises — capture must not
    break the proxied response (FR-001a)."""
    if not model_id or not usage_dict:
        return
    try:
        record = CaptureIngestionRecord(
            source_kind=SourceKind.API_PROXY,
            confidence_grade=ConfidenceGrade.EXACT,
            model_id=model_id,
            timestamp=datetime.now(UTC).isoformat(),
            usage=_usage_from_dict(usage_dict),
            prefix_bytes=prefix_bytes,
            response_message_id=response_message_id,
            previous_message_id=None,
            diagnostics=diagnostics,
            breakpoints=[],
        )
        api.ingest(record, store)
    except Exception:
        logger.exception("cache proxy: capture failed; proxied response is unaffected")


class _SseUsageScout:
    """Best-effort scan of an SSE byte stream for the ``message_start``
    event's model / message id / usage — the input-side usage Anthropic
    reports up front. Never blocks or delays forwarded chunks; parsing
    failures are swallowed."""

    def __init__(self) -> None:
        self._buf = b""
        self.model_id: str | None = None
        self.response_message_id: str | None = None
        self.usage: dict[str, Any] | None = None

    def feed(self, chunk: bytes) -> None:
        if self.usage is not None:
            return
        self._buf += chunk
        while b"\n\n" in self._buf:
            event, self._buf = self._buf.split(b"\n\n", 1)
            self._consume_event(event)

    def _consume_event(self, event: bytes) -> None:
        data_lines = [
            line[len(b"data:") :].strip() for line in event.split(b"\n") if line.startswith(b"data:")
        ]
        if not data_lines:
            return
        try:
            payload = json.loads(b"\n".join(data_lines))
        except Exception:
            return
        if not isinstance(payload, dict) or payload.get("type") != "message_start":
            return
        message = payload.get("message") or {}
        self.model_id = message.get("model")
        self.response_message_id = message.get("id")
        self.usage = message.get("usage")


def create_app(
    store: CacheStore,
    upstream: str = "https://api.anthropic.com",
    diagnostics: bool = False,
    client: httpx.AsyncClient | None = None,
) -> Starlette:
    """Build the proxy ASGI app.

    ``client`` lets tests inject an ``httpx.AsyncClient`` backed by
    ``httpx.ASGITransport`` pointed at a fake upstream, so no real network
    is used. When omitted, a real client targeting ``upstream`` is built and
    owned (closed on shutdown).
    """
    owned_client = client is None
    http_client = client if client is not None else httpx.AsyncClient(base_url=upstream)

    async def _forward(request: Request) -> Response:
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        body = await request.body()
        req_headers = _filtered_headers(request.headers, drop=_HOP_BY_HOP | {"host"})

        upstream_request = http_client.build_request(
            request.method, path, content=body, headers=req_headers
        )
        upstream_response = await http_client.send(upstream_request, stream=True)

        is_capture_target = (
            request.method == "POST"
            and path.split("?", 1)[0] == "/v1/messages"
            and upstream_response.status_code == 200
        )
        content_type = upstream_response.headers.get("content-type", "")
        is_sse = "text/event-stream" in content_type
        resp_headers = _filtered_headers(upstream_response.headers, drop=_HOP_BY_HOP)

        if is_capture_target and is_sse:
            return await _stream_and_capture(
                upstream_response=upstream_response,
                resp_headers=resp_headers,
                request_body=body,
                store=store,
            )

        resp_body = await upstream_response.aread()
        await upstream_response.aclose()

        if is_capture_target:
            _capture_buffered(
                request_body=body,
                response_body=resp_body,
                store=store,
                diagnostics_enabled=diagnostics,
            )

        return Response(
            content=resp_body,
            status_code=upstream_response.status_code,
            headers=dict(resp_headers),
        )

    @asynccontextmanager
    async def _lifespan(_app: Starlette) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owned_client:
                await http_client.aclose()

    app = Starlette(
        routes=[Route("/{path:path}", _forward, methods=_ALL_METHODS)],
        lifespan=_lifespan,
    )
    return app


def _capture_buffered(
    *,
    request_body: bytes,
    response_body: bytes,
    store: CacheStore,
    diagnostics_enabled: bool,
) -> None:
    req_json = _safe_json(request_body) or {}
    response_json = _safe_json(response_body)
    if response_json is None:
        return
    diag = None
    if diagnostics_enabled and "diagnostics" in response_json:
        diag = response_json["diagnostics"]
    _capture(
        store=store,
        prefix_bytes=request_body,
        model_id=req_json.get("model"),
        usage_dict=response_json.get("usage"),
        response_message_id=response_json.get("id"),
        diagnostics=diag,
    )


async def _stream_and_capture(
    *,
    upstream_response: httpx.Response,
    resp_headers: Iterable[tuple[str, str]],
    request_body: bytes,
    store: CacheStore,
) -> StreamingResponse:
    scout = _SseUsageScout()

    async def body_iter() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream_response.aiter_bytes():
                scout.feed(chunk)
                yield chunk
        finally:
            await upstream_response.aclose()
            req_json = _safe_json(request_body) or {}
            # Diagnostics live on a full JSON response body, not the SSE
            # event stream, so a streamed capture never carries them.
            _capture(
                store=store,
                prefix_bytes=request_body,
                model_id=scout.model_id or req_json.get("model"),
                usage_dict=scout.usage,
                response_message_id=scout.response_message_id,
                diagnostics=None,
            )

    return StreamingResponse(
        body_iter(),
        status_code=upstream_response.status_code,
        headers=dict(resp_headers),
    )


def run(
    store_db_path: str,
    host: str = "127.0.0.1",
    port: int = 8790,
    upstream: str = "https://api.anthropic.com",
    diagnostics: bool = False,
) -> None:
    """Build the app against a real ``CacheStore`` and run it under uvicorn,
    bound to ``host`` (default loopback-only). Importable without starting
    a server, so it stays test-friendly."""
    store = CacheStore(store_db_path)
    app = create_app(store, upstream=upstream, diagnostics=diagnostics)
    uvicorn.run(app, host=host, port=port)
