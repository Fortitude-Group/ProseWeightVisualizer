# Contract: Watch-mode Local HTTP API (Release 3)

**Stability**: public, SemVer'd. Local, single-tenant, loopback by default (`127.0.0.1`). Started via `proseweight serve`. Minimal by design — an enabler for editor/agent integrations, not a platform (FR-032).

All responses are the versioned report schema shapes ([report-schema.md](./report-schema.md)); `schema_version` is included. No auth (loopback, single-tenant); binding to a non-loopback host requires an explicit `--host` and prints a warning.

## Endpoints

### `GET /health`
`200 {"status":"ok","engine_version":"…","schema_version":"1.0.0"}`

### `POST /segment`
Body: `{ "text": "<prompt>" }` → `200 { "instructions": [Instruction, …] }`. Segmentation only; no run. Lets an editor show segment boundaries live.

### `POST /weight`
Query an instruction's weight (US13). Body:
```jsonc
{ "text": "<prompt>", "instruction_id": "i7",
  "model": "Qwen/Qwen2.5-1.5B-Instruct", "suite": "1.3.0",
  "depth": "quick_scan", "seed": 42 }
```
→ `200 { "weight": WeightScore }` — the weight, its components, and its credible interval. `depth: deep_audit` may stream progress (see below) or return `202` with a `run_id` to poll.

### `POST /scan`
Full verdict for a prompt (async). `202 { "run_id": "…" }`.

### `GET /runs/{run_id}`
`200 { "status": "running|complete|incomplete", "verdict": Verdict? }`. `verdict` present only when `status == complete`; an incomplete run is never returned as a finished verdict.

### `GET /runs/{run_id}/events` (optional, SSE)
Server-sent progress events for live UIs: `{ "phase": "segment|prescreen|ablate|judge|stats", "done": n, "total": m }`.

## Errors

Standard JSON error body `{ "error": { "code": "…", "message": "…" } }`. `400` bad input, `404` unknown run, `409` model/suite not available locally, `422` scoping/hash-guard failure (suite file doesn't match its tagged version), `500` engine error. The `ANTHROPIC_API_KEY` is read from the server environment only; it is never accepted in a request body.

## Determinism

A `/weight` or `/scan` with a fully-local judge and identical inputs+seed returns identical numbers (FR-017). Any run using `judge: anthropic` carries `reproducibility: "best_effort"` in its `run` block.
