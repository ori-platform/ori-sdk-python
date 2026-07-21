# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Typed logical models for the observational ``runtime.telemetry.v1`` contract.

This module does not load credentials, build HTTP requests, or grant mutation
authority. It mirrors the specs-owned telemetry body and byte contract only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping, TypeAlias, cast

RUNTIME_TELEMETRY_SCHEMA_VERSION: Literal["runtime.telemetry.v1"] = (
    "runtime.telemetry.v1"
)
JSON_SAFE_INT_MAX = 9_007_199_254_740_991

RuntimeTelemetryEventType = Literal["sensor.reading"]
TelemetryJsonScalar: TypeAlias = str | int | float | bool | None
TelemetryJsonValue: TypeAlias = (
    TelemetryJsonScalar
    | list["TelemetryJsonValue"]
    | tuple["TelemetryJsonValue", ...]
    | Mapping[str, "TelemetryJsonValue"]
)
TelemetryJsonObject: TypeAlias = Mapping[str, TelemetryJsonValue]

_READING_FIELDS = frozenset(
    {"sensor_id", "sensor_type", "value", "unit", "timestamp", "quality", "metadata"}
)
_EVENT_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "device_id",
        "sensor_id",
        "timestamp",
        "source",
        "fingerprint",
        "context",
        "reading",
    }
)
_BATCH_FIELDS = frozenset(
    {"schema_version", "device_id", "sequence", "sent_at_ms", "events"}
)


class TelemetryCanonicalizationError(ValueError):
    """Raised when telemetry cannot be represented byte-identically."""


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field_name} must be valid UTF-8 text") from exc
    return value


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if abs(value) > JSON_SAFE_INT_MAX:
        raise ValueError(f"{field_name} must be within the JSON-safe integer range")
    return value


def _require_number(value: object, field_name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    _validate_canonical_number(value, field_name)
    return value


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    for key in value:
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")
        _require_string(key, f"{field_name} key")
    return cast(Mapping[str, object], value)


def _require_array(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return cast(list[object], value)


def _validate_canonical_number(value: int | float, field_name: str) -> None:
    if isinstance(value, int):
        if abs(value) > JSON_SAFE_INT_MAX:
            raise ValueError(f"integer outside JSON-safe range at {field_name}")
        return
    if not math.isfinite(value):
        raise ValueError(f"non-finite number at {field_name}")
    magnitude = abs(value)
    if magnitude != 0.0 and not (1e-4 <= magnitude < 1e16):
        raise ValueError(f"float outside cross-language canonical zone at {field_name}")


def _freeze_json(
    value: object,
    field_name: str,
    active_container_ids: set[int] | None = None,
) -> TelemetryJsonValue:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _require_string(value, field_name)
    if isinstance(value, int):
        _validate_canonical_number(value, field_name)
        return value
    if isinstance(value, float):
        _validate_canonical_number(value, field_name)
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


def _freeze_json_object(value: object, field_name: str) -> TelemetryJsonObject:
    frozen = _freeze_json(value, field_name)
    if not isinstance(frozen, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return frozen


def _thaw_json(value: TelemetryJsonValue, field_name: str) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {
            key: _thaw_json(item, f"{field_name}.{key}") for key, item in value.items()
        }
    return [_thaw_json(item, f"{field_name}[]") for item in value]


def _thaw_json_object(value: TelemetryJsonObject, field_name: str) -> dict[str, object]:
    thawed = _thaw_json(value, field_name)
    if not isinstance(thawed, dict):
        raise ValueError(f"{field_name} must be an object")
    return cast(dict[str, object], thawed)


def _freeze_additional_fields(
    value: object,
    known_fields: frozenset[str],
    field_name: str,
    *,
    forbidden_fields: frozenset[str] = frozenset(),
) -> TelemetryJsonObject:
    mapping = _require_mapping(value, field_name)
    collisions = sorted(set(mapping) & known_fields)
    if collisions:
        rendered = ", ".join(repr(key) for key in collisions)
        raise ValueError(f"{field_name} duplicates known fields: {rendered}")
    forbidden = sorted(set(mapping) & forbidden_fields)
    if forbidden:
        rendered = ", ".join(repr(key) for key in forbidden)
        raise ValueError(f"{field_name} contains forbidden fields: {rendered}")
    return _freeze_json_object(mapping, field_name)


def _extract_additional_fields(
    payload: Mapping[str, object], known_fields: frozenset[str], field_name: str
) -> TelemetryJsonObject:
    _require_mapping(payload, field_name)
    return _freeze_json_object(
        {key: value for key, value in payload.items() if key not in known_fields},
        f"{field_name}.additional_fields",
    )


@dataclass(frozen=True, slots=True)
class RuntimeTelemetryReading:
    """One reading embedded in a direct observational telemetry event."""

    sensor_id: str
    sensor_type: str
    value: int | float
    unit: str
    timestamp: int
    quality: int | float
    metadata: TelemetryJsonObject
    additional_fields: TelemetryJsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "sensor_id", _require_string(self.sensor_id, "sensor_id")
        )
        object.__setattr__(
            self, "sensor_type", _require_string(self.sensor_type, "sensor_type")
        )
        object.__setattr__(self, "value", _require_number(self.value, "value"))
        object.__setattr__(self, "unit", _require_string(self.unit, "unit"))
        object.__setattr__(
            self, "timestamp", _require_int(self.timestamp, "reading.timestamp")
        )
        object.__setattr__(self, "quality", _require_number(self.quality, "quality"))
        object.__setattr__(
            self, "metadata", _freeze_json_object(self.metadata, "metadata")
        )
        object.__setattr__(
            self,
            "additional_fields",
            _freeze_additional_fields(
                self.additional_fields,
                _READING_FIELDS,
                "reading.additional_fields",
                forbidden_fields=frozenset({"raw"}),
            ),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RuntimeTelemetryReading:
        if "raw" in payload:
            raise ValueError("reading.raw is forbidden by runtime.telemetry.v1")
        return cls(
            sensor_id=_require_string(payload.get("sensor_id"), "sensor_id"),
            sensor_type=_require_string(payload.get("sensor_type"), "sensor_type"),
            value=_require_number(payload.get("value"), "value"),
            unit=_require_string(payload.get("unit"), "unit"),
            timestamp=_require_int(payload.get("timestamp"), "reading.timestamp"),
            quality=_require_number(payload.get("quality"), "quality"),
            metadata=_freeze_json_object(payload.get("metadata"), "metadata"),
            additional_fields=_extract_additional_fields(
                payload, _READING_FIELDS, "reading"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "quality": self.quality,
            "metadata": _thaw_json_object(self.metadata, "metadata"),
        }
        result.update(
            _thaw_json_object(self.additional_fields, "reading.additional_fields")
        )
        return result


@dataclass(frozen=True, slots=True)
class RuntimeTelemetryEvent:
    """One ``sensor.reading`` event in a direct telemetry batch."""

    event_id: str
    event_type: RuntimeTelemetryEventType
    device_id: str
    sensor_id: str
    timestamp: int
    source: str
    fingerprint: str
    context: TelemetryJsonObject
    reading: RuntimeTelemetryReading
    additional_fields: TelemetryJsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _require_string(self.event_id, "event_id"))
        event_type = _require_string(self.event_type, "event_type")
        if event_type != "sensor.reading":
            raise ValueError("event_type must be 'sensor.reading'")
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(
            self, "device_id", _require_string(self.device_id, "device_id")
        )
        object.__setattr__(
            self, "sensor_id", _require_string(self.sensor_id, "sensor_id")
        )
        object.__setattr__(
            self, "timestamp", _require_int(self.timestamp, "event.timestamp")
        )
        object.__setattr__(self, "source", _require_string(self.source, "source"))
        object.__setattr__(
            self, "fingerprint", _require_string(self.fingerprint, "fingerprint")
        )
        object.__setattr__(
            self, "context", _freeze_json_object(self.context, "context")
        )
        if not isinstance(self.reading, RuntimeTelemetryReading):
            raise ValueError("reading must be a RuntimeTelemetryReading")
        if self.sensor_id != self.reading.sensor_id:
            raise ValueError("event sensor_id must match reading sensor_id")
        object.__setattr__(
            self,
            "additional_fields",
            _freeze_additional_fields(
                self.additional_fields, _EVENT_FIELDS, "event.additional_fields"
            ),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RuntimeTelemetryEvent:
        reading = RuntimeTelemetryReading.from_dict(
            _require_mapping(payload.get("reading"), "reading")
        )
        event_type = _require_string(payload.get("event_type"), "event_type")
        return cls(
            event_id=_require_string(payload.get("event_id"), "event_id"),
            event_type=cast(RuntimeTelemetryEventType, event_type),
            device_id=_require_string(payload.get("device_id"), "device_id"),
            sensor_id=_require_string(payload.get("sensor_id"), "sensor_id"),
            timestamp=_require_int(payload.get("timestamp"), "event.timestamp"),
            source=_require_string(payload.get("source"), "source"),
            fingerprint=_require_string(payload.get("fingerprint"), "fingerprint"),
            context=_freeze_json_object(payload.get("context"), "context"),
            reading=reading,
            additional_fields=_extract_additional_fields(
                payload, _EVENT_FIELDS, "event"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "device_id": self.device_id,
            "sensor_id": self.sensor_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "fingerprint": self.fingerprint,
            "context": _thaw_json_object(self.context, "context"),
            "reading": self.reading.to_dict(),
        }
        result.update(
            _thaw_json_object(self.additional_fields, "event.additional_fields")
        )
        return result


@dataclass(frozen=True, slots=True)
class RuntimeTelemetryBatch:
    """One canonicalizable direct runtime telemetry batch."""

    schema_version: Literal["runtime.telemetry.v1"]
    device_id: str
    sequence: int
    sent_at_ms: int
    events: tuple[RuntimeTelemetryEvent, ...]
    additional_fields: TelemetryJsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        schema_version = _require_string(self.schema_version, "schema_version")
        if schema_version != RUNTIME_TELEMETRY_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {RUNTIME_TELEMETRY_SCHEMA_VERSION!r}"
            )
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(
            self, "device_id", _require_string(self.device_id, "device_id")
        )
        object.__setattr__(self, "sequence", _require_int(self.sequence, "sequence"))
        object.__setattr__(
            self, "sent_at_ms", _require_int(self.sent_at_ms, "sent_at_ms")
        )
        if not isinstance(self.events, (list, tuple)):
            raise ValueError("events must be an array")
        events = tuple(self.events)
        for event in events:
            if not isinstance(event, RuntimeTelemetryEvent):
                raise ValueError("events must contain RuntimeTelemetryEvent values")
            if event.device_id != self.device_id:
                raise ValueError("event device_id must match batch device_id")
        object.__setattr__(self, "events", events)
        object.__setattr__(
            self,
            "additional_fields",
            _freeze_additional_fields(
                self.additional_fields, _BATCH_FIELDS, "batch.additional_fields"
            ),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RuntimeTelemetryBatch:
        events_payload = _require_array(payload.get("events"), "events")
        schema_version = _require_string(
            payload.get("schema_version"), "schema_version"
        )
        return cls(
            schema_version=cast(Literal["runtime.telemetry.v1"], schema_version),
            device_id=_require_string(payload.get("device_id"), "device_id"),
            sequence=_require_int(payload.get("sequence"), "sequence"),
            sent_at_ms=_require_int(payload.get("sent_at_ms"), "sent_at_ms"),
            events=tuple(
                RuntimeTelemetryEvent.from_dict(_require_mapping(item, "events[]"))
                for item in events_payload
            ),
            additional_fields=_extract_additional_fields(
                payload, _BATCH_FIELDS, "batch"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": self.schema_version,
            "device_id": self.device_id,
            "sequence": self.sequence,
            "sent_at_ms": self.sent_at_ms,
            "events": [event.to_dict() for event in self.events],
        }
        result.update(
            _thaw_json_object(self.additional_fields, "batch.additional_fields")
        )
        return result


def canonical_telemetry_bytes(batch: RuntimeTelemetryBatch) -> bytes:
    """Return specs-owned canonical UTF-8 bytes for a validated batch."""

    if not isinstance(batch, RuntimeTelemetryBatch):
        raise TypeError("batch must be a RuntimeTelemetryBatch")
    try:
        return json.dumps(
            batch.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TelemetryCanonicalizationError(str(exc)) from exc


def telemetry_hmac_sha256(
    api_key: str | bytes, timestamp_ms: int | str | bytes, body: bytes
) -> str:
    """Return the lowercase HMAC hex for an already-canonical telemetry body."""

    if not isinstance(api_key, (str, bytes)):
        raise TypeError("api_key must be a string or bytes")
    if not isinstance(body, bytes):
        raise TypeError("body must be bytes")
    key = api_key.encode("utf-8") if isinstance(api_key, str) else api_key
    if isinstance(timestamp_ms, bool):
        raise TypeError("timestamp_ms must be an integer, string, or bytes")
    if isinstance(timestamp_ms, int):
        timestamp = str(timestamp_ms).encode("ascii")
    elif isinstance(timestamp_ms, str):
        try:
            timestamp = timestamp_ms.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("timestamp_ms must contain only ASCII characters") from exc
    elif isinstance(timestamp_ms, bytes):
        timestamp = timestamp_ms
    else:
        raise TypeError("timestamp_ms must be an integer, string, or bytes")
    return hmac.new(key, timestamp + b"." + body, hashlib.sha256).hexdigest()


__all__ = [
    "JSON_SAFE_INT_MAX",
    "RUNTIME_TELEMETRY_SCHEMA_VERSION",
    "RuntimeTelemetryBatch",
    "RuntimeTelemetryEvent",
    "RuntimeTelemetryEventType",
    "RuntimeTelemetryReading",
    "TelemetryCanonicalizationError",
    "TelemetryJsonObject",
    "TelemetryJsonScalar",
    "TelemetryJsonValue",
    "canonical_telemetry_bytes",
    "telemetry_hmac_sha256",
]
