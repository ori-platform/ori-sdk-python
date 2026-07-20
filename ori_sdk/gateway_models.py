# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Strict logical payload models for the Ori gateway API v1 contract.

These models intentionally exclude MQTT authentication and encryption envelopes.
Transport security remains owned by ori-runtime and ori-gateway.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping, TypeAlias, cast

ExportType = Literal[
    "health",
    "sensor_history",
    "action_log",
    "reasoning_log",
    "tier_c_decision_log",
]
RuntimeNodeStatus = Literal["healthy", "degraded"]

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = (
    JsonScalar | list["JsonValue"] | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
)
JsonObject: TypeAlias = Mapping[str, JsonValue]

EXPORT_TYPES = frozenset(
    {
        "health",
        "sensor_history",
        "action_log",
        "reasoning_log",
        "tier_c_decision_log",
    }
)
RUNTIME_NODE_STATUSES = frozenset({"healthy", "degraded"})
MAX_REQUEST_ID_BYTES = 128
MAX_EXPORT_PAGE_ITEMS = 1_000
MAX_ACTIVE_TRIGGERS = 64
MAX_ACTIVE_TRIGGER_BYTES = 128
MAX_ACTION_EVENT_TYPE_BYTES = 64
MAX_HEARTBEAT_FUTURE_SKEW_MS = 5 * 60 * 1_000

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PAGE_TOKEN_RE = re.compile(r"^[0-9]+$")
_ACTION_EVENT_TYPE_RE = re.compile(r"^[A-Z_]*$")
_CHAIN_HEAD_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _require_non_empty_string(value: object, field_name: str) -> str:
    text = _require_string(value, field_name)
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _require_optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, field_name)


def _require_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    for key in value:
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")
    return cast(Mapping[str, object], value)


def _reject_unknown_fields(
    payload: Mapping[str, object], allowed: frozenset[str], field_name: str
) -> None:
    for key in payload:
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")
    unknown = sorted(set(payload) - allowed)
    if unknown:
        rendered = ", ".join(repr(key) for key in unknown)
        raise ValueError(f"{field_name} contains unknown fields: {rendered}")


def _freeze_json(
    value: object,
    field_name: str,
    active_container_ids: set[int] | None = None,
) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must contain only finite numbers")
        return value
    if not isinstance(value, (Mapping, list, tuple)):
        raise ValueError(f"{field_name} must contain only JSON-compatible values")

    active_ids = active_container_ids if active_container_ids is not None else set()
    container_id = id(value)
    if container_id in active_ids:
        raise ValueError(f"{field_name} contains a cyclic reference")
    active_ids.add(container_id)
    try:
        if isinstance(value, Mapping):
            mapping = _require_mapping(value, field_name)
            return MappingProxyType(
                {
                    key: _freeze_json(item, f"{field_name}.{key}", active_ids)
                    for key, item in mapping.items()
                }
            )
        sequence = cast(list[object] | tuple[object, ...], value)
        return tuple(
            _freeze_json(item, f"{field_name}[]", active_ids) for item in sequence
        )
    finally:
        active_ids.remove(container_id)


def _thaw_json(
    value: JsonValue,
    field_name: str,
    active_container_ids: set[int] | None = None,
) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must contain only finite numbers")
        return value
    if not isinstance(value, (Mapping, list, tuple)):
        raise ValueError(f"{field_name} must contain only JSON-compatible values")

    active_ids = active_container_ids if active_container_ids is not None else set()
    container_id = id(value)
    if container_id in active_ids:
        raise ValueError(f"{field_name} contains a cyclic reference")
    active_ids.add(container_id)
    try:
        if isinstance(value, Mapping):
            return {
                key: _thaw_json(item, f"{field_name}.{key}", active_ids)
                for key, item in value.items()
            }
        return [_thaw_json(item, f"{field_name}[]", active_ids) for item in value]
    finally:
        active_ids.remove(container_id)


def _freeze_json_object(value: object, field_name: str) -> JsonObject:
    frozen = _freeze_json(value, field_name)
    if not isinstance(frozen, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return frozen


def _thaw_json_object(value: JsonObject, field_name: str) -> dict[str, object]:
    thawed = _thaw_json(value, field_name)
    if not isinstance(thawed, dict):
        raise ValueError(f"{field_name} must be an object")
    return cast(dict[str, object], thawed)


def _freeze_json_objects(value: object, field_name: str) -> tuple[JsonObject, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be an array")
    return tuple(_freeze_json_object(item, f"{field_name}[]") for item in value)


def _validate_mqtt_device_id(device_id: object) -> str:
    value = _require_string(device_id, "device_id")
    if not value:
        raise ValueError("device_id must not be empty")
    if value.strip() != value:
        raise ValueError("device_id must not contain leading or trailing whitespace")
    if any(character in value for character in "/+#|"):
        raise ValueError(
            "device_id must not contain MQTT topic separators, wildcards, "
            "or auth delimiters"
        )
    return value


def _validate_mqtt_request_id(value: object, field_name: str = "request_id") -> str:
    identifier = _require_string(value, field_name)
    if not identifier:
        raise ValueError(f"{field_name} must not be empty")
    if identifier.strip() != identifier:
        raise ValueError(
            f"{field_name} must not contain leading or trailing whitespace"
        )
    if not identifier.isascii():
        raise ValueError(
            f"{field_name} must contain only ASCII letters, digits, hyphen, "
            "or underscore"
        )
    if len(identifier) > MAX_REQUEST_ID_BYTES:
        raise ValueError(f"{field_name} must not exceed {MAX_REQUEST_ID_BYTES} bytes")
    if not _REQUEST_ID_RE.fullmatch(identifier):
        raise ValueError(
            f"{field_name} must contain only ASCII letters, digits, hyphen, "
            "or underscore"
        )
    return identifier


def _validate_export_type(value: object) -> ExportType:
    export_type = _require_string(value, "export_type")
    if export_type not in EXPORT_TYPES:
        expected = ", ".join(sorted(EXPORT_TYPES))
        raise ValueError(f"export_type must be one of {expected}")
    return cast(ExportType, export_type)


def _validate_page_token(value: object, field_name: str) -> str:
    token = _require_string(value, field_name)
    if token:
        if not _PAGE_TOKEN_RE.fullmatch(token):
            raise ValueError(
                f"{field_name} must be empty or a non-negative integer offset"
            )
        try:
            int(token)
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must be empty or a non-negative integer offset"
            ) from exc
    return token


def _validate_export_params(
    export_type: ExportType,
    params: JsonObject,
    since_ms: int | None,
    until_ms: int | None,
) -> None:
    if export_type == "sensor_history":
        if since_ms is None or until_ms is None:
            raise ValueError("since_ms and until_ms are required for sensor_history")
        sensor_id = params.get("sensor_id")
        if not isinstance(sensor_id, str) or not sensor_id.strip():
            raise ValueError("params.sensor_id must be a non-empty string")
        bucket_ms = params.get("bucket_ms", 0)
        if isinstance(bucket_ms, bool) or not isinstance(bucket_ms, int):
            raise ValueError("params.bucket_ms must be an integer")
        if bucket_ms < 0:
            raise ValueError("params.bucket_ms must be >= 0")
    elif export_type == "action_log" and "tier" in params:
        tier = params["tier"]
        if tier not in {"A", "B", "C", "D"}:
            raise ValueError("params.tier must be one of A, B, C, D")
    elif export_type == "reasoning_log":
        tier_used = params.get("tier_used")
        if tier_used is not None and tier_used not in {"rule", "local_slm", "gateway"}:
            raise ValueError("params.tier_used must be one of rule, local_slm, gateway")
        action_tier = params.get("action_tier")
        if action_tier is not None and action_tier not in {"A", "B", "C", "D"}:
            raise ValueError("params.action_tier must be one of A, B, C, D")
        reasoning_status = params.get("reasoning_status")
        if reasoning_status is not None and reasoning_status not in {
            "complete",
            "incomplete",
            "skipped",
        }:
            raise ValueError(
                "params.reasoning_status must be complete, incomplete, or skipped"
            )
        correlation_id = params.get("correlation_id")
        if correlation_id is not None and not isinstance(correlation_id, str):
            raise ValueError("params.correlation_id must be a string")


@dataclass(frozen=True, slots=True)
class RuntimeNodeHeartbeatEvidence:
    """Evidence-chain liveness signal carried by a runtime heartbeat."""

    chain_head_hash: str
    attestation_gap_count: int
    available: bool
    action_event_type: str

    def __post_init__(self) -> None:
        chain_head_hash = _require_string(self.chain_head_hash, "chain_head_hash")
        if chain_head_hash and not _CHAIN_HEAD_HASH_RE.fullmatch(chain_head_hash):
            raise ValueError(
                "chain_head_hash must be 64 lowercase hexadecimal characters or empty"
            )
        gap_count = _require_int(self.attestation_gap_count, "attestation_gap_count")
        if gap_count < 0:
            raise ValueError("attestation_gap_count must be >= 0")
        available = _require_bool(self.available, "available")
        action_event_type = _require_string(self.action_event_type, "action_event_type")
        if len(action_event_type.encode("utf-8")) > MAX_ACTION_EVENT_TYPE_BYTES:
            raise ValueError(
                f"action_event_type must not exceed {MAX_ACTION_EVENT_TYPE_BYTES} bytes"
            )
        if not _ACTION_EVENT_TYPE_RE.fullmatch(action_event_type):
            raise ValueError("action_event_type must be empty or SCREAMING_SNAKE_CASE")
        object.__setattr__(self, "chain_head_hash", chain_head_hash)
        object.__setattr__(self, "attestation_gap_count", gap_count)
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "action_event_type", action_event_type)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RuntimeNodeHeartbeatEvidence:
        _reject_unknown_fields(
            payload,
            frozenset(
                {
                    "chain_head_hash",
                    "attestation_gap_count",
                    "available",
                    "action_event_type",
                }
            ),
            "evidence",
        )
        return cls(
            chain_head_hash=_require_string(
                payload.get("chain_head_hash"), "chain_head_hash"
            ),
            attestation_gap_count=_require_int(
                payload.get("attestation_gap_count"), "attestation_gap_count"
            ),
            available=_require_bool(payload.get("available"), "available"),
            action_event_type=_require_string(
                payload.get("action_event_type"), "action_event_type"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_head_hash": self.chain_head_hash,
            "attestation_gap_count": self.attestation_gap_count,
            "available": self.available,
            "action_event_type": self.action_event_type,
        }


@dataclass(frozen=True, slots=True)
class RuntimeNodeHeartbeat:
    """Logical runtime-node heartbeat after transport verification."""

    device_id: str
    status: RuntimeNodeStatus
    last_seen_ms: int
    gateway_seen_ms: int
    active_triggers: tuple[str, ...] = ()
    evidence: RuntimeNodeHeartbeatEvidence | None = None

    def __post_init__(self) -> None:
        device_id = _validate_mqtt_device_id(self.device_id)
        status = _require_string(self.status, "status")
        if status not in RUNTIME_NODE_STATUSES:
            raise ValueError("status must be healthy or degraded")
        last_seen_ms = _require_int(self.last_seen_ms, "last_seen_ms")
        if last_seen_ms <= 0:
            raise ValueError("last_seen_ms must be positive")
        now_ms = time.time_ns() // 1_000_000
        if last_seen_ms > now_ms + MAX_HEARTBEAT_FUTURE_SKEW_MS:
            raise ValueError("last_seen_ms is too far in the future")
        gateway_seen_ms = _require_int(self.gateway_seen_ms, "gateway_seen_ms")
        if not isinstance(self.active_triggers, (list, tuple)):
            raise ValueError("active_triggers must be an array")
        if len(self.active_triggers) > MAX_ACTIVE_TRIGGERS:
            raise ValueError(
                f"active_triggers must not contain more than {MAX_ACTIVE_TRIGGERS} entries"
            )
        active_triggers: list[str] = []
        for trigger in self.active_triggers:
            trigger_name = _require_string(trigger, "active_triggers[]")
            if not trigger_name or trigger_name.strip() != trigger_name:
                raise ValueError(
                    "active_triggers entries must be non-empty and trimmed"
                )
            if len(trigger_name.encode("utf-8")) > MAX_ACTIVE_TRIGGER_BYTES:
                raise ValueError(
                    "active_triggers entries must not exceed "
                    f"{MAX_ACTIVE_TRIGGER_BYTES} bytes"
                )
            active_triggers.append(trigger_name)
        if self.evidence is not None and not isinstance(
            self.evidence, RuntimeNodeHeartbeatEvidence
        ):
            raise ValueError("evidence must be RuntimeNodeHeartbeatEvidence or None")
        object.__setattr__(self, "device_id", device_id)
        object.__setattr__(self, "status", cast(RuntimeNodeStatus, status))
        object.__setattr__(self, "last_seen_ms", last_seen_ms)
        object.__setattr__(self, "gateway_seen_ms", gateway_seen_ms)
        object.__setattr__(self, "active_triggers", tuple(active_triggers))

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RuntimeNodeHeartbeat:
        _reject_unknown_fields(
            payload,
            frozenset(
                {
                    "device_id",
                    "status",
                    "last_seen_ms",
                    "gateway_seen_ms",
                    "active_triggers",
                    "evidence",
                }
            ),
            "runtime heartbeat",
        )
        triggers = payload.get("active_triggers")
        if not isinstance(triggers, list):
            raise ValueError("active_triggers must be an array")
        evidence_payload = payload.get("evidence")
        evidence = (
            None
            if evidence_payload is None
            else RuntimeNodeHeartbeatEvidence.from_dict(
                _require_mapping(evidence_payload, "evidence")
            )
        )
        status = _require_string(payload.get("status"), "status")
        return cls(
            device_id=_require_string(payload.get("device_id"), "device_id"),
            status=cast(RuntimeNodeStatus, status),
            last_seen_ms=_require_int(payload.get("last_seen_ms"), "last_seen_ms"),
            gateway_seen_ms=_require_int(
                payload.get("gateway_seen_ms"), "gateway_seen_ms"
            ),
            active_triggers=tuple(
                _require_string(trigger, "active_triggers[]") for trigger in triggers
            ),
            evidence=evidence,
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "device_id": self.device_id,
            "status": self.status,
            "last_seen_ms": self.last_seen_ms,
            "gateway_seen_ms": self.gateway_seen_ms,
            "active_triggers": list(self.active_triggers),
        }
        if self.evidence is not None:
            result["evidence"] = self.evidence.to_dict()
        return result


@dataclass(frozen=True, slots=True)
class RuntimeExportRequest:
    """Read-only request for a bounded runtime-owned export."""

    request_id: str
    export_type: ExportType
    device_id: str
    since_ms: int | None = None
    until_ms: int | None = None
    limit: int = 100
    page_token: str = ""
    params: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        request_id = _validate_mqtt_request_id(self.request_id)
        export_type = _validate_export_type(self.export_type)
        device_id = _validate_mqtt_device_id(self.device_id)
        since_ms = _require_optional_int(self.since_ms, "since_ms")
        until_ms = _require_optional_int(self.until_ms, "until_ms")
        if since_ms is not None and since_ms < 0:
            raise ValueError("since_ms must be >= 0")
        if until_ms is not None and until_ms < 0:
            raise ValueError("until_ms must be >= 0")
        if since_ms is not None and until_ms is not None and until_ms < since_ms:
            raise ValueError("until_ms must be >= since_ms")
        limit = _require_int(self.limit, "limit")
        # The runtime accepts any positive request limit and bounds response pages.
        if limit < 1:
            raise ValueError("limit must be >= 1")
        page_token = _validate_page_token(self.page_token, "page_token")
        params = _freeze_json_object(self.params, "params")
        _validate_export_params(export_type, params, since_ms, until_ms)
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "export_type", export_type)
        object.__setattr__(self, "device_id", device_id)
        object.__setattr__(self, "since_ms", since_ms)
        object.__setattr__(self, "until_ms", until_ms)
        object.__setattr__(self, "limit", limit)
        object.__setattr__(self, "page_token", page_token)
        object.__setattr__(self, "params", params)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RuntimeExportRequest:
        _reject_unknown_fields(
            payload,
            frozenset(
                {
                    "request_id",
                    "export_type",
                    "device_id",
                    "since_ms",
                    "until_ms",
                    "limit",
                    "page_token",
                    "params",
                }
            ),
            "export request",
        )
        export_type = _require_string(payload.get("export_type"), "export_type")
        return cls(
            request_id=_require_string(payload.get("request_id"), "request_id"),
            export_type=cast(ExportType, export_type),
            device_id=_require_string(payload.get("device_id"), "device_id"),
            since_ms=_require_optional_int(payload.get("since_ms"), "since_ms"),
            until_ms=_require_optional_int(payload.get("until_ms"), "until_ms"),
            limit=_require_int(payload.get("limit", 100), "limit"),
            page_token=_require_string(payload.get("page_token", ""), "page_token"),
            params=_freeze_json_object(payload.get("params", {}), "params"),
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "request_id": self.request_id,
            "export_type": self.export_type,
            "device_id": self.device_id,
            "limit": self.limit,
            "page_token": self.page_token,
            "params": _thaw_json_object(self.params, "params"),
        }
        if self.since_ms is not None:
            result["since_ms"] = self.since_ms
        if self.until_ms is not None:
            result["until_ms"] = self.until_ms
        return result


@dataclass(frozen=True, slots=True)
class RuntimeExportResponse:
    """Bounded runtime export page or correlated error envelope."""

    request_id: str
    export_type: str
    device_id: str
    items: tuple[JsonObject, ...] = ()
    next_page_token: str = ""
    complete: bool = True
    error: str | None = None

    def __post_init__(self) -> None:
        request_id = _validate_mqtt_request_id(self.request_id)
        export_type = _require_non_empty_string(self.export_type, "export_type")
        device_id = _validate_mqtt_device_id(self.device_id)
        items = _freeze_json_objects(self.items, "items")
        if len(items) > MAX_EXPORT_PAGE_ITEMS:
            raise ValueError(
                f"items must not contain more than {MAX_EXPORT_PAGE_ITEMS} entries"
            )
        next_page_token = _validate_page_token(self.next_page_token, "next_page_token")
        complete = _require_bool(self.complete, "complete")
        error = self.error
        if error is not None:
            error = _require_non_empty_string(error, "error")
            if items:
                raise ValueError("error responses must contain no items")
            if not complete:
                raise ValueError("error responses must set complete to true")
            if next_page_token:
                raise ValueError("error responses must not contain a next_page_token")
        else:
            _validate_export_type(export_type)
            if complete and next_page_token:
                raise ValueError(
                    "complete responses must not contain a next_page_token"
                )
            if not complete and not next_page_token:
                raise ValueError("incomplete responses must contain a next_page_token")
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "export_type", export_type)
        object.__setattr__(self, "device_id", device_id)
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "next_page_token", next_page_token)
        object.__setattr__(self, "complete", complete)
        object.__setattr__(self, "error", error)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RuntimeExportResponse:
        _reject_unknown_fields(
            payload,
            frozenset(
                {
                    "request_id",
                    "export_type",
                    "device_id",
                    "items",
                    "next_page_token",
                    "complete",
                    "error",
                }
            ),
            "export response",
        )
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("items must be an array")
        error_value = payload.get("error")
        error = None if error_value is None else _require_string(error_value, "error")
        return cls(
            request_id=_require_string(payload.get("request_id"), "request_id"),
            export_type=_require_string(payload.get("export_type"), "export_type"),
            device_id=_require_string(payload.get("device_id"), "device_id"),
            items=_freeze_json_objects(items, "items"),
            next_page_token=_require_string(
                payload.get("next_page_token"), "next_page_token"
            ),
            complete=_require_bool(payload.get("complete"), "complete"),
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "export_type": self.export_type,
            "device_id": self.device_id,
            "items": [_thaw_json_object(item, "items[]") for item in self.items],
            "next_page_token": self.next_page_token,
            "complete": self.complete,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class TierCEnrichmentHistorySample:
    """One bounded sensor-history sample used for Tier C explanation."""

    sensor_id: str
    sensor_type: str
    unit: str
    timestamp_ms: int
    value: float
    quality: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "sensor_id", _require_string(self.sensor_id, "sensor_id")
        )
        object.__setattr__(
            self, "sensor_type", _require_string(self.sensor_type, "sensor_type")
        )
        object.__setattr__(self, "unit", _require_string(self.unit, "unit"))
        object.__setattr__(
            self, "timestamp_ms", _require_int(self.timestamp_ms, "timestamp_ms")
        )
        object.__setattr__(self, "value", _require_number(self.value, "value"))
        object.__setattr__(self, "quality", _require_number(self.quality, "quality"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> TierCEnrichmentHistorySample:
        _reject_unknown_fields(
            payload,
            frozenset(
                {
                    "sensor_id",
                    "sensor_type",
                    "unit",
                    "timestamp_ms",
                    "value",
                    "quality",
                }
            ),
            "history_window[]",
        )
        return cls(
            sensor_id=_require_string(payload.get("sensor_id"), "sensor_id"),
            sensor_type=_require_string(payload.get("sensor_type"), "sensor_type"),
            unit=_require_string(payload.get("unit"), "unit"),
            timestamp_ms=_require_int(payload.get("timestamp_ms"), "timestamp_ms"),
            value=_require_number(payload.get("value"), "value"),
            quality=_require_number(payload.get("quality"), "quality"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "unit": self.unit,
            "timestamp_ms": self.timestamp_ms,
            "value": self.value,
            "quality": self.quality,
        }


@dataclass(frozen=True, slots=True)
class TierCEnrichmentRequest:
    """Advisory request for operator-facing Tier C context."""

    request_id: str
    proposal_id: str
    device_id: str
    skill_name: str
    trigger_name: str
    sensor_id: str
    sensor_type: str
    reading_value: float
    unit: str
    history_window: tuple[TierCEnrichmentHistorySample, ...]
    proposed_action: str
    safe_default_action: str
    operator_message: str
    timeout_ms: int

    def __post_init__(self) -> None:
        request_id = _validate_mqtt_request_id(self.request_id)
        proposal_id = _validate_mqtt_request_id(self.proposal_id, "proposal_id")
        device_id = _validate_mqtt_device_id(self.device_id)
        required_text = {
            "skill_name": self.skill_name,
            "trigger_name": self.trigger_name,
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "proposed_action": self.proposed_action,
            "safe_default_action": self.safe_default_action,
            "operator_message": self.operator_message,
        }
        for field_name, value in required_text.items():
            object.__setattr__(
                self, field_name, _require_non_empty_string(value, field_name)
            )
        reading_value = _require_number(self.reading_value, "reading_value")
        unit = _require_string(self.unit, "unit")
        if not isinstance(self.history_window, (list, tuple)):
            raise ValueError("history_window must be an array")
        history_window: list[TierCEnrichmentHistorySample] = []
        for sample in self.history_window:
            if not isinstance(sample, TierCEnrichmentHistorySample):
                raise ValueError(
                    "history_window entries must be TierCEnrichmentHistorySample"
                )
            history_window.append(sample)
        timeout_ms = _require_int(self.timeout_ms, "timeout_ms")
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "proposal_id", proposal_id)
        object.__setattr__(self, "device_id", device_id)
        object.__setattr__(self, "reading_value", reading_value)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "history_window", tuple(history_window))
        object.__setattr__(self, "timeout_ms", timeout_ms)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> TierCEnrichmentRequest:
        _reject_unknown_fields(
            payload,
            frozenset(
                {
                    "request_id",
                    "proposal_id",
                    "device_id",
                    "skill_name",
                    "trigger_name",
                    "sensor_id",
                    "sensor_type",
                    "reading_value",
                    "unit",
                    "history_window",
                    "proposed_action",
                    "safe_default_action",
                    "operator_message",
                    "timeout_ms",
                }
            ),
            "tier c enrichment request",
        )
        history = payload.get("history_window")
        if not isinstance(history, list):
            raise ValueError("history_window must be an array")
        return cls(
            request_id=_require_string(payload.get("request_id"), "request_id"),
            proposal_id=_require_string(payload.get("proposal_id"), "proposal_id"),
            device_id=_require_string(payload.get("device_id"), "device_id"),
            skill_name=_require_string(payload.get("skill_name"), "skill_name"),
            trigger_name=_require_string(payload.get("trigger_name"), "trigger_name"),
            sensor_id=_require_string(payload.get("sensor_id"), "sensor_id"),
            sensor_type=_require_string(payload.get("sensor_type"), "sensor_type"),
            reading_value=_require_number(
                payload.get("reading_value"), "reading_value"
            ),
            unit=_require_string(payload.get("unit"), "unit"),
            history_window=tuple(
                TierCEnrichmentHistorySample.from_dict(
                    _require_mapping(sample, "history_window[]")
                )
                for sample in history
            ),
            proposed_action=_require_string(
                payload.get("proposed_action"), "proposed_action"
            ),
            safe_default_action=_require_string(
                payload.get("safe_default_action"), "safe_default_action"
            ),
            operator_message=_require_string(
                payload.get("operator_message"), "operator_message"
            ),
            timeout_ms=_require_int(payload.get("timeout_ms"), "timeout_ms"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "proposal_id": self.proposal_id,
            "device_id": self.device_id,
            "skill_name": self.skill_name,
            "trigger_name": self.trigger_name,
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "reading_value": self.reading_value,
            "unit": self.unit,
            "history_window": [sample.to_dict() for sample in self.history_window],
            "proposed_action": self.proposed_action,
            "safe_default_action": self.safe_default_action,
            "operator_message": self.operator_message,
            "timeout_ms": self.timeout_ms,
        }


@dataclass(frozen=True, slots=True)
class TierCEnrichmentResponse:
    """Advisory-only Tier C enrichment response."""

    request_id: str
    proposal_id: str
    explanation: str = ""
    estimated_impact: str = ""
    recommended_operator_context: str = ""
    provider: str = ""
    model: str = ""
    tokens_used: int = 0
    latency_ms: int = 0
    error: str | None = None

    def __post_init__(self) -> None:
        request_id = _validate_mqtt_request_id(self.request_id)
        proposal_id = _validate_mqtt_request_id(self.proposal_id, "proposal_id")
        optional_text = {
            "explanation": self.explanation,
            "estimated_impact": self.estimated_impact,
            "recommended_operator_context": self.recommended_operator_context,
            "provider": self.provider,
            "model": self.model,
        }
        for field_name, value in optional_text.items():
            object.__setattr__(self, field_name, _require_string(value, field_name))
        tokens_used = _require_int(self.tokens_used, "tokens_used")
        latency_ms = _require_int(self.latency_ms, "latency_ms")
        error = self.error
        if error is not None:
            error = _require_non_empty_string(error, "error")
        elif not self.explanation:
            raise ValueError("explanation must not be empty on a successful response")
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "proposal_id", proposal_id)
        object.__setattr__(self, "tokens_used", tokens_used)
        object.__setattr__(self, "latency_ms", latency_ms)
        object.__setattr__(self, "error", error)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> TierCEnrichmentResponse:
        _reject_unknown_fields(
            payload,
            frozenset(
                {
                    "request_id",
                    "proposal_id",
                    "explanation",
                    "estimated_impact",
                    "recommended_operator_context",
                    "provider",
                    "model",
                    "tokens_used",
                    "latency_ms",
                    "error",
                }
            ),
            "tier c enrichment response",
        )
        error_value = payload.get("error")
        error = None if error_value is None else _require_string(error_value, "error")
        return cls(
            request_id=_require_string(payload.get("request_id"), "request_id"),
            proposal_id=_require_string(payload.get("proposal_id"), "proposal_id"),
            explanation=_require_string(payload.get("explanation", ""), "explanation"),
            estimated_impact=_require_string(
                payload.get("estimated_impact", ""), "estimated_impact"
            ),
            recommended_operator_context=_require_string(
                payload.get("recommended_operator_context", ""),
                "recommended_operator_context",
            ),
            provider=_require_string(payload.get("provider", ""), "provider"),
            model=_require_string(payload.get("model", ""), "model"),
            tokens_used=_require_int(payload.get("tokens_used", 0), "tokens_used"),
            latency_ms=_require_int(payload.get("latency_ms", 0), "latency_ms"),
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "request_id": self.request_id,
            "proposal_id": self.proposal_id,
        }
        optional_text = {
            "explanation": self.explanation,
            "estimated_impact": self.estimated_impact,
            "recommended_operator_context": self.recommended_operator_context,
            "provider": self.provider,
            "model": self.model,
        }
        for field_name, value in optional_text.items():
            if value:
                result[field_name] = value
        if self.tokens_used:
            result["tokens_used"] = self.tokens_used
        if self.latency_ms:
            result["latency_ms"] = self.latency_ms
        if self.error is not None:
            result["error"] = self.error
        return result
