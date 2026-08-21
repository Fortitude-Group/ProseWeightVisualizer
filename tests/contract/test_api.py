"""Contract tests for the watch-mode API (contracts/api.md)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from proseweight.api.server import create_app

client = TestClient(create_app())


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["schema_version"] == "1.0.0"


def test_segment_is_functional():
    r = client.post("/segment", json={"text": "Never defer. Be concise."})
    assert r.status_code == 200
    instrs = r.json()["instructions"]
    assert len(instrs) == 2
    assert instrs[0]["text"].strip().startswith("Never defer")


def test_weight_without_runtime_returns_409():
    r = client.post("/weight", json={"text": "Be concise.", "instruction_id": "i0"})
    assert r.status_code == 409
    assert "runtime" in r.json()["detail"].lower()


def test_key_never_accepted_in_body():
    # the request schema has no api-key field; extra fields are ignored by pydantic
    r = client.post(
        "/segment", json={"text": "Be concise.", "api_key": "should-be-ignored"}
    )
    assert r.status_code == 200
