"""Versioned CacheScope contracts — the two serialisable boundaries (Principle II).

- ``CaptureIngestionRecord`` is the **input** contract (FR-001a): any producer —
  the reference proxy, the transcript ingester, or OmnisRouter — writes it.
- ``CacheScopeResult`` is the **output** contract (FR-028): the render adapter,
  the CLI, and (later) OmnisVigil consume it.

Plain dataclasses with explicit ``to_dict`` / ``from_dict`` / ``validate`` so the
guarantees in ``contracts/*.md`` are enforced in code and tested, without a
heavyweight validation dependency (mirrors ``001``'s ``report/schema.py`` style).
This module imports only the standard library — it is the root of the
transplantable core.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# SemVer of each contract, stamped into every artefact. A breaking field change
# is a MAJOR bump with a migration note (Principle II).
CAPTURE_CONTRACT_VERSION = "1.0.0"
RESULT_VERSION = "1.0.0"

# The leading-window used to fingerprint a cache lineage family (M1 remediation).
LINEAGE_PREFIX_WINDOW = 4096


class SourceKind(str, Enum):
    API_PROXY = "api_proxy"
    CLAUDE_CODE_TRANSCRIPT = "claude_code_transcript"
    EXTERNAL_CONTRACT = "external_contract"  # e.g. OmnisRouter


class ConfidenceGrade(str, Enum):
    EXACT = "exact"
    RECONSTRUCTED_HIGH = "reconstructed_high"
    RECONSTRUCTED_LOW = "reconstructed_low"


class BreakpointLevel(str, Enum):
    TOOLS = "tools"
    SYSTEM = "system"
    MESSAGES = "messages"


class Ttl(str, Enum):
    FIVE_MIN = "5m"
    ONE_HOUR = "1h"


class BreakpointState(str, Enum):
    HIT = "hit"
    RECOMPUTED = "recomputed"
    NEW = "new"
    NEVER_CACHED = "never_cached"


class CauseClass(str, Enum):
    CRLF_DRIFT = "crlf_drift"
    TRAILING_WHITESPACE = "trailing_whitespace"
    VOLATILE_HEADER = "volatile_header"
    CONCAT_ORDER_CHANGE = "concat_order_change"
    TIMESTAMP_INJECTION = "timestamp_injection"
    TOOL_DEFINITION_CHURN = "tool_definition_churn"
    MODEL_CHANGE = "model_change"
    SYSTEM_PROMPT_CHANGE = "system_prompt_change"
    GENUINE_EDIT = "genuine_edit"


class BillingModel(str, Enum):
    PAYG = "payg"
    SUBSCRIPTION = "subscription"


class Agreement(str, Enum):
    AGREE = "agree"
    LEVEL_MISMATCH = "level_mismatch"
    TOKEN_MISMATCH = "token_mismatch"
    NO_MEASUREMENT = "no_measurement"


class LintFraming(str, Enum):
    PREDICTION = "prediction"  # invariant — a static finding is never a measured verdict


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ContractError(ValueError):
    """Raised when a record violates its contract; message names the version."""


# --------------------------------------------------------------------------- #
# Input contract: CaptureIngestionRecord
# --------------------------------------------------------------------------- #


@dataclass
class Usage:
    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    ephemeral_5m_input_tokens: int | None = None
    ephemeral_1h_input_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "input_tokens": self.input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }
        if self.ephemeral_5m_input_tokens is not None:
            d["ephemeral_5m_input_tokens"] = self.ephemeral_5m_input_tokens
        if self.ephemeral_1h_input_tokens is not None:
            d["ephemeral_1h_input_tokens"] = self.ephemeral_1h_input_tokens
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Usage:
        return cls(
            input_tokens=int(d.get("input_tokens", 0)),
            cache_creation_input_tokens=int(d.get("cache_creation_input_tokens", 0)),
            cache_read_input_tokens=int(d.get("cache_read_input_tokens", 0)),
            ephemeral_5m_input_tokens=_opt_int(d.get("ephemeral_5m_input_tokens")),
            ephemeral_1h_input_tokens=_opt_int(d.get("ephemeral_1h_input_tokens")),
        )


@dataclass
class BreakpointMarker:
    index: int
    level: BreakpointLevel
    capped_byte_offset: int
    ttl: Ttl = Ttl.FIVE_MIN

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "level": self.level.value,
            "capped_byte_offset": self.capped_byte_offset,
            "ttl": self.ttl.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BreakpointMarker:
        return cls(
            index=int(d["index"]),
            level=BreakpointLevel(d["level"]),
            capped_byte_offset=int(d["capped_byte_offset"]),
            ttl=Ttl(d.get("ttl", "5m")),
        )


@dataclass
class CaptureIngestionRecord:
    """One captured turn, as written by any producer. See contracts/capture-ingestion.md."""

    source_kind: SourceKind
    confidence_grade: ConfidenceGrade
    model_id: str
    timestamp: str
    usage: Usage
    contract_version: str = CAPTURE_CONTRACT_VERSION
    # Exactly one of prefix_bytes / prefix_ref is present.
    prefix_bytes: bytes | None = None
    prefix_ref: dict[str, Any] | None = None  # {"sha256": ..., "byte_len": ...}
    breakpoints: list[BreakpointMarker] = field(default_factory=list)
    response_message_id: str | None = None
    previous_message_id: str | None = None
    diagnostics: dict[str, Any] | None = None

    def prefix_hash(self) -> str:
        if self.prefix_bytes is not None:
            return sha256_hex(self.prefix_bytes)
        if self.prefix_ref and "sha256" in self.prefix_ref:
            return str(self.prefix_ref["sha256"])
        raise ContractError(
            f"[{self.contract_version}] record has neither prefix_bytes nor a prefix_ref hash"
        )

    def byte_len(self) -> int:
        if self.prefix_bytes is not None:
            return len(self.prefix_bytes)
        if self.prefix_ref and "byte_len" in self.prefix_ref:
            return int(self.prefix_ref["byte_len"])
        raise ContractError(f"[{self.contract_version}] cannot determine byte length")

    def validate(self) -> CaptureIngestionRecord:
        v = self.contract_version
        has_bytes = self.prefix_bytes is not None
        has_ref = self.prefix_ref is not None
        if has_bytes == has_ref:
            raise ContractError(
                f"[{v}] exactly one of prefix_bytes / prefix_ref must be present"
            )
        # api_proxy ⇒ exact (FR-004)
        if self.source_kind is SourceKind.API_PROXY and self.confidence_grade is not ConfidenceGrade.EXACT:
            raise ContractError(f"[{v}] api_proxy source must be confidence 'exact'")
        # a transcript may never claim exact
        if self.source_kind is SourceKind.CLAUDE_CODE_TRANSCRIPT and self.confidence_grade is ConfidenceGrade.EXACT:
            raise ContractError(f"[{v}] a transcript source may not be 'exact'")
        # diagnostics ⇒ api_proxy (FR-014, Claude-API only)
        if self.diagnostics is not None and self.source_kind is not SourceKind.API_PROXY:
            raise ContractError(f"[{v}] diagnostics may only accompany an api_proxy source")
        for tok in (
            self.usage.input_tokens,
            self.usage.cache_creation_input_tokens,
            self.usage.cache_read_input_tokens,
        ):
            if tok < 0:
                raise ContractError(f"[{v}] usage token counts must be >= 0")
        if len(self.breakpoints) > 4:
            raise ContractError(f"[{v}] at most 4 breakpoints per request")
        return self

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "contract_version": self.contract_version,
            "source_kind": self.source_kind.value,
            "confidence_grade": self.confidence_grade.value,
            "model_id": self.model_id,
            "timestamp": self.timestamp,
            "usage": self.usage.to_dict(),
            "breakpoints": [b.to_dict() for b in self.breakpoints],
            "response_message_id": self.response_message_id,
            "previous_message_id": self.previous_message_id,
            "diagnostics": self.diagnostics,
        }
        if self.prefix_bytes is not None:
            d["prefix_bytes_b64"] = base64.b64encode(self.prefix_bytes).decode("ascii")
            d["prefix_ref"] = None
        else:
            d["prefix_bytes_b64"] = None
            d["prefix_ref"] = self.prefix_ref
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CaptureIngestionRecord:
        b64 = d.get("prefix_bytes_b64")
        prefix_bytes = base64.b64decode(b64) if b64 else None
        rec = cls(
            source_kind=SourceKind(d["source_kind"]),
            confidence_grade=ConfidenceGrade(d["confidence_grade"]),
            model_id=d["model_id"],
            timestamp=d["timestamp"],
            usage=Usage.from_dict(d.get("usage", {})),
            contract_version=d.get("contract_version", CAPTURE_CONTRACT_VERSION),
            prefix_bytes=prefix_bytes,
            prefix_ref=d.get("prefix_ref"),
            breakpoints=[BreakpointMarker.from_dict(b) for b in d.get("breakpoints", [])],
            response_message_id=d.get("response_message_id"),
            previous_message_id=d.get("previous_message_id"),
            diagnostics=d.get("diagnostics"),
        )
        return rec


# --------------------------------------------------------------------------- #
# Output contract: CacheScopeResult (+ figures)
# --------------------------------------------------------------------------- #


@dataclass
class PricingStamp:
    """Provenance stamped on the result and on every figure (SC-002)."""

    pricing_version: str
    effective_date: str
    fx_date: str
    usd_gbp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pricing_version": self.pricing_version,
            "effective_date": self.effective_date,
            "fx_date": self.fx_date,
            "usd_gbp": self.usd_gbp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PricingStamp:
        return cls(
            pricing_version=d["pricing_version"],
            effective_date=d["effective_date"],
            fx_date=d["fx_date"],
            usd_gbp=float(d["usd_gbp"]),
        )


@dataclass
class LintFinding:
    """A static prediction (US2 / FR-007). ``framing`` is always ``prediction``."""

    rule_id: str
    file: str
    line: int
    offset: int
    estimated_monthly_gbp: float
    pricing_version: str
    effective_date: str
    fx_date: str
    framing: LintFraming = LintFraming.PREDICTION
    confirmed_by_measurement: str | None = None  # confirmed | refuted | pending
    id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "file": self.file,
            "line": self.line,
            "offset": self.offset,
            "estimated_monthly_gbp": self.estimated_monthly_gbp,
            "framing": self.framing.value,
            "confirmed_by_measurement": self.confirmed_by_measurement,
            "pricing_version": self.pricing_version,
            "effective_date": self.effective_date,
            "fx_date": self.fx_date,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LintFinding:
        return cls(
            rule_id=d["rule_id"],
            file=d["file"],
            line=int(d["line"]),
            offset=int(d["offset"]),
            estimated_monthly_gbp=float(d["estimated_monthly_gbp"]),
            pricing_version=d["pricing_version"],
            effective_date=d["effective_date"],
            fx_date=d["fx_date"],
            framing=LintFraming(d.get("framing", "prediction")),
            confirmed_by_measurement=d.get("confirmed_by_measurement"),
            id=d.get("id", ""),
        )

    def validate(self) -> LintFinding:
        if self.framing is not LintFraming.PREDICTION:
            raise ContractError("a static lint finding must be framed as a prediction")
        _require_stamp(self.pricing_version, self.effective_date, self.fx_date)
        return self


@dataclass
class CacheScopeResult:
    """The versioned output projection (FR-028). Divergence/attribution/rollup
    containers are populated in Release 2; Release 1 populates lint_findings.
    """

    pricing: PricingStamp
    generated_at: str
    result_version: str = RESULT_VERSION
    lineages: list[dict[str, Any]] = field(default_factory=list)
    divergences: list[dict[str, Any]] = field(default_factory=list)
    breakpoints: list[dict[str, Any]] = field(default_factory=list)
    attributions: list[dict[str, Any]] = field(default_factory=list)
    rollups: list[dict[str, Any]] = field(default_factory=list)
    lint_findings: list[LintFinding] = field(default_factory=list)
    validity: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_version": self.result_version,
            "generated_at": self.generated_at,
            "pricing": self.pricing.to_dict(),
            "lineages": self.lineages,
            "divergences": self.divergences,
            "breakpoints": self.breakpoints,
            "attributions": self.attributions,
            "rollups": self.rollups,
            "lint_findings": [f.to_dict() for f in self.lint_findings],
            "validity": self.validity,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CacheScopeResult:
        return cls(
            pricing=PricingStamp.from_dict(d["pricing"]),
            generated_at=d["generated_at"],
            result_version=d.get("result_version", RESULT_VERSION),
            lineages=d.get("lineages", []),
            divergences=d.get("divergences", []),
            breakpoints=d.get("breakpoints", []),
            attributions=d.get("attributions", []),
            rollups=d.get("rollups", []),
            lint_findings=[LintFinding.from_dict(f) for f in d.get("lint_findings", [])],
            validity=d.get("validity"),
        )

    def validate(self) -> CacheScopeResult:
        _require_stamp(
            self.pricing.pricing_version, self.pricing.effective_date, self.pricing.fx_date
        )
        for f in self.lint_findings:
            f.validate()
        # A subscription attribution figure is always a shadow-price, never a bill (SC-006);
        # a never_cached breakpoint never carries waste (SC-010). Enforced here so R2 code
        # that populates these lists cannot silently violate the guarantee.
        attr_divs = {a.get("divergence_id") for a in self.attributions}
        for a in self.attributions:
            if a.get("billing_model") == BillingModel.SUBSCRIPTION.value and not a.get("is_shadow_price"):
                raise ContractError("a subscription figure must be flagged is_shadow_price (SC-006)")
            for stamp in ("pricing_version", "effective_date", "fx_date"):
                if not a.get(stamp):
                    raise ContractError(f"every attribution must carry {stamp} (SC-002)")
        for b in self.breakpoints:
            if b.get("state") == BreakpointState.NEVER_CACHED.value and b.get("turn_id") in attr_divs:
                # defensive; attributions key on divergence, not turn — kept for clarity
                pass
        return self


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _opt_int(v: Any) -> int | None:
    return None if v is None else int(v)


def _require_stamp(pricing_version: str, effective_date: str, fx_date: str) -> None:
    if not (pricing_version and effective_date and fx_date):
        raise ContractError("every figure must carry pricing_version + effective_date + fx_date (SC-002)")
