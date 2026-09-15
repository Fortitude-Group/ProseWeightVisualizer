# Contract: Capture-Ingestion Record (input)

**Stability**: public, SemVer'd. `contract_version` is stamped into every record; a breaking field
change is a MAJOR bump with a migration note. This is the **input** boundary (FR-001a): the versioned,
serialisable record that *any* producer writes so CacheScope can analyse it — the built-in reference
proxy, the Claude Code transcript ingester, and the sibling **OmnisRouter** product's byte-capture sink
(OmnisRouter-side emission is out of scope here; this contract reserves the shape for it, R2/R11).

The runtime boundary is language-neutral and on-disk (OmnisRouter is .NET; CacheScope is Python):
producers append records; CacheScope consumes them and never embeds a producer.

## Record

```jsonc
{
  "contract_version": "1.0.0",
  "source_kind": "api_proxy",          // api_proxy | claude_code_transcript | external_contract
  "confidence_grade": "exact",          // exact | reconstructed_high | reconstructed_low
  "model_id": "claude-opus-5",
  "timestamp": "2026-09-14T10:00:00Z",

  // Exactly one of prefix_bytes | prefix_ref. Proxy path sends bytes; a producer that already
  // content-addressed the prefix may send a ref (hash + length) and stream bytes out-of-band.
  "prefix_bytes_b64": "…",             // exact on-wire rendered prefix (tools→system→messages), base64
  "prefix_ref": null,                   // { "sha256": "…", "byte_len": 12345 }

  "usage": {
    "input_tokens": 1200,               // uncached (full price)
    "cache_creation_input_tokens": 0,   // ~1.25× write
    "cache_read_input_tokens": 8000,    // ~0.1× read
    "ephemeral_5m_input_tokens": 8000,  // optional TTL split, where the response reported it
    "ephemeral_1h_input_tokens": 0
  },

  "breakpoints": [                       // resolved cache_control positions, exact on proxy path
    { "index": 0, "level": "system", "capped_byte_offset": 40000, "ttl": "5m" }
  ],

  "response_message_id": "msg_01…",      // authoritative lineage edge (R4)
  "previous_message_id": null,           // threaded for the diagnostics beta (null on first turn)
  "diagnostics": null                    // raw response.diagnostics payload; PAYG proxy + opt-in beta only
}
```

## Rules

- **`source_kind = api_proxy` ⇒ `confidence_grade = exact`**; a transcript source may never claim
  `exact` (FR-004). `external_contract` producers state their own grade.
- **`diagnostics` non-null ⇒ `source_kind = api_proxy`** (the beta is Claude-API-only, FR-014). Its
  internal shape is passed through verbatim and interpreted defensively (payload sub-fields unverified,
  research R8) — an absent field is treated as "no measurement", never agreement (FR-015).
- **Exactly one** of `prefix_bytes_b64` / `prefix_ref` is present. Bytes are the exact on-wire prefix
  (SC-001 depends on byte fidelity); a ref must resolve to bytes CacheScope can read locally.
- **Nothing leaves the machine** (FR-005): a producer writes locally; there is no network egress in this
  contract.
- Unknown top-level fields are ignored (forward-compatible); a missing required field is rejected with
  the record's `contract_version` in the error.

## Producers (informative)

| Producer | Path | Confidence | Notes |
|---|---|---|---|
| Reference reverse proxy | R1, this repo | `exact` | base-URL override; tees exact bytes + usage |
| Claude Code transcript ingester | R1 basic / R3 byte-level | `reconstructed_*` | author's primary path |
| OmnisRouter byte-capture sink | out of scope (OmnisRouter repo) | `exact` | production source; emits this record |
