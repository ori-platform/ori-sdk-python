# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Typed models for Ori runtime/spec contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


def _as_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _as_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


def _as_int(value: object, field: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _as_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    return float(value)


def _as_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _as_optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _as_int(value, field)


def _as_optional_bool(value: object, field: str) -> bool | None:
    if value is None:
        return None
    return _as_bool(value, field)


def _as_optional_str(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, field)


def _as_int_dict(value: object, field: str) -> dict[str, int]:
    mapping = _as_mapping(value, field)
    result: dict[str, int] = {}
    for k, v in mapping.items():
        if not isinstance(k, str):
            raise ValueError(f"{field} keys must be strings")
        result[k] = _as_int(v, f"{field}.{k}")
    return result


def _as_action_tier(value: object, field: str) -> str:
    tier = _as_str(value, field)
    if tier not in {"A", "B", "C", "D"}:
        raise ValueError(f"{field} must be one of A, B, C, D")
    return tier


@dataclass(frozen=True)
class AlertTimestamps:
    """Alert delivery timestamps indexed by channel and trigger name.

    Mirrors the ``last_alert_timestamps`` field in the runtime health snapshot.
    Both dicts map names to millisecond Unix timestamps.
    """

    by_channel: dict[str, int]
    by_trigger: dict[str, int]

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AlertTimestamps:
        return cls(
            by_channel=_as_int_dict(
                payload.get("by_channel"), "last_alert_timestamps.by_channel"
            ),
            by_trigger=_as_int_dict(
                payload.get("by_trigger"), "last_alert_timestamps.by_trigger"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "by_channel": dict(self.by_channel),
            "by_trigger": dict(self.by_trigger),
        }


@dataclass(frozen=True)
class DevicePolicyState:
    """Device policy snapshot as reported by the action dispatcher.

    When ``available`` is ``False`` all optional fields are ``None``.
    The ``enabled`` flag reflects the runtime config regardless of availability.
    """

    available: bool
    enabled: bool
    policy_version: int | None
    tier: str | None
    relay_b_enabled: bool | None
    relay_c_enabled: bool | None
    cloud_llm_enabled: bool | None
    valid_until: int | None
    issued_at: int | None
    is_expired: bool | None

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> DevicePolicyState:
        return cls(
            available=_as_bool(payload.get("available"), "device_policy.available"),
            enabled=_as_bool(payload.get("enabled"), "device_policy.enabled"),
            policy_version=_as_optional_int(
                payload.get("policy_version"), "device_policy.policy_version"
            ),
            tier=_as_optional_str(payload.get("tier"), "device_policy.tier"),
            relay_b_enabled=_as_optional_bool(
                payload.get("relay_b_enabled"), "device_policy.relay_b_enabled"
            ),
            relay_c_enabled=_as_optional_bool(
                payload.get("relay_c_enabled"), "device_policy.relay_c_enabled"
            ),
            cloud_llm_enabled=_as_optional_bool(
                payload.get("cloud_llm_enabled"), "device_policy.cloud_llm_enabled"
            ),
            valid_until=_as_optional_int(
                payload.get("valid_until"), "device_policy.valid_until"
            ),
            issued_at=_as_optional_int(
                payload.get("issued_at"), "device_policy.issued_at"
            ),
            is_expired=_as_optional_bool(
                payload.get("is_expired"), "device_policy.is_expired"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "enabled": self.enabled,
            "policy_version": self.policy_version,
            "tier": self.tier,
            "relay_b_enabled": self.relay_b_enabled,
            "relay_c_enabled": self.relay_c_enabled,
            "cloud_llm_enabled": self.cloud_llm_enabled,
            "valid_until": self.valid_until,
            "issued_at": self.issued_at,
            "is_expired": self.is_expired,
        }


@dataclass(frozen=True)
class CapabilityPosture:
    available: bool
    sms_available: bool
    whatsapp_available: bool
    gateway_reachable: bool
    local_slm_loaded: bool
    relay_connected: bool
    internet_available: bool
    checked_at_ms: int
    expires_at_ms: int
    gateway_last_heartbeat_ms: int | None

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> CapabilityPosture:
        return cls(
            available=_as_bool(
                payload.get("available"), "capability_posture.available"
            ),
            sms_available=_as_bool(
                payload.get("sms_available"), "capability_posture.sms_available"
            ),
            whatsapp_available=_as_bool(
                payload.get("whatsapp_available"),
                "capability_posture.whatsapp_available",
            ),
            gateway_reachable=_as_bool(
                payload.get("gateway_reachable"),
                "capability_posture.gateway_reachable",
            ),
            local_slm_loaded=_as_bool(
                payload.get("local_slm_loaded"), "capability_posture.local_slm_loaded"
            ),
            relay_connected=_as_bool(
                payload.get("relay_connected"), "capability_posture.relay_connected"
            ),
            internet_available=_as_bool(
                payload.get("internet_available"),
                "capability_posture.internet_available",
            ),
            checked_at_ms=_as_int(
                payload.get("checked_at_ms"), "capability_posture.checked_at_ms"
            ),
            expires_at_ms=_as_int(
                payload.get("expires_at_ms"), "capability_posture.expires_at_ms"
            ),
            gateway_last_heartbeat_ms=_as_optional_int(
                payload.get("gateway_last_heartbeat_ms"),
                "capability_posture.gateway_last_heartbeat_ms",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "sms_available": self.sms_available,
            "whatsapp_available": self.whatsapp_available,
            "gateway_reachable": self.gateway_reachable,
            "local_slm_loaded": self.local_slm_loaded,
            "relay_connected": self.relay_connected,
            "internet_available": self.internet_available,
            "checked_at_ms": self.checked_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "gateway_last_heartbeat_ms": self.gateway_last_heartbeat_ms,
        }


@dataclass(frozen=True)
class SensorStatus:
    id: str
    type: str
    protocol: str
    poll_interval_ms: int
    connected: bool
    last_seen_ms: int | None
    stale: bool

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> SensorStatus:
        return cls(
            id=_as_str(payload.get("id"), "sensors[].id"),
            type=_as_str(payload.get("type"), "sensors[].type"),
            protocol=_as_str(payload.get("protocol"), "sensors[].protocol"),
            poll_interval_ms=_as_int(
                payload.get("poll_interval_ms"), "sensors[].poll_interval_ms"
            ),
            connected=_as_bool(payload.get("connected"), "sensors[].connected"),
            last_seen_ms=_as_optional_int(
                payload.get("last_seen_ms"), "sensors[].last_seen_ms"
            ),
            stale=_as_bool(payload.get("stale"), "sensors[].stale"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "protocol": self.protocol,
            "poll_interval_ms": self.poll_interval_ms,
            "connected": self.connected,
            "last_seen_ms": self.last_seen_ms,
            "stale": self.stale,
        }


@dataclass(frozen=True)
class HealthStatus:
    device_id: str
    uptime_s: float
    health_socket_path: str
    capability_posture: CapabilityPosture
    sensors: list[SensorStatus]
    last_alert_timestamps: AlertTimestamps
    device_policy: DevicePolicyState

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> HealthStatus:
        posture_raw = _as_mapping(
            payload.get("capability_posture"), "health.capability_posture"
        )
        sensors_raw = payload.get("sensors")
        if not isinstance(sensors_raw, list):
            raise ValueError("health.sensors must be an array")
        alert_raw = _as_mapping(
            payload.get("last_alert_timestamps"), "health.last_alert_timestamps"
        )
        policy_raw = _as_mapping(payload.get("device_policy"), "health.device_policy")
        return cls(
            device_id=_as_str(payload.get("device_id"), "health.device_id"),
            uptime_s=_as_float(payload.get("uptime_s"), "health.uptime_s"),
            health_socket_path=_as_str(
                payload.get("health_socket_path"), "health.health_socket_path"
            ),
            capability_posture=CapabilityPosture.from_dict(posture_raw),
            sensors=[
                SensorStatus.from_dict(_as_mapping(item, "health.sensors[]"))
                for item in sensors_raw
            ],
            last_alert_timestamps=AlertTimestamps.from_dict(alert_raw),
            device_policy=DevicePolicyState.from_dict(policy_raw),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "device_id": self.device_id,
            "uptime_s": self.uptime_s,
            "health_socket_path": self.health_socket_path,
            "capability_posture": self.capability_posture.to_dict(),
            "sensors": [sensor.to_dict() for sensor in self.sensors],
            "last_alert_timestamps": self.last_alert_timestamps.to_dict(),
            "device_policy": self.device_policy.to_dict(),
        }


@dataclass(frozen=True)
class HealthError:
    code: str
    detail: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> HealthError:
        return cls(
            code=_as_str(payload.get("code"), "error.code"),
            detail=_as_str(payload.get("detail"), "error.detail"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HealthResponse:
    schema_version: int
    ok: bool
    health: HealthStatus | None
    error: HealthError | None

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> HealthResponse:
        ok = _as_bool(payload.get("ok"), "ok")
        health: HealthStatus | None = None
        error: HealthError | None = None
        if ok:
            health = HealthStatus.from_dict(
                _as_mapping(payload.get("health"), "health")
            )
        else:
            error = HealthError.from_dict(_as_mapping(payload.get("error"), "error"))
        return cls(
            schema_version=_as_int(payload.get("schema_version"), "schema_version"),
            ok=ok,
            health=health,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        base: dict[str, object] = {
            "schema_version": self.schema_version,
            "ok": self.ok,
        }
        if self.ok:
            base["health"] = self.health.to_dict() if self.health is not None else None
        else:
            base["error"] = self.error.to_dict() if self.error is not None else None
        return base


@dataclass(frozen=True)
class GatewayContextHistoryPoint:
    value: float
    timestamp: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> GatewayContextHistoryPoint:
        return cls(
            value=_as_float(payload.get("value"), "context.history[].value"),
            timestamp=_as_int(payload.get("timestamp"), "context.history[].timestamp"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class GatewayReasoningContext:
    value: float
    unit: str
    timestamp: int
    history: list[GatewayContextHistoryPoint]

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> GatewayReasoningContext:
        history_raw = payload.get("history")
        if not isinstance(history_raw, list):
            raise ValueError("context.history must be an array")
        return cls(
            value=_as_float(payload.get("value"), "context.value"),
            unit=_as_str(payload.get("unit"), "context.unit"),
            timestamp=_as_int(payload.get("timestamp"), "context.timestamp"),
            history=[
                GatewayContextHistoryPoint.from_dict(
                    _as_mapping(item, "context.history[]")
                )
                for item in history_raw
            ],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "history": [item.to_dict() for item in self.history],
        }


@dataclass(frozen=True)
class GatewayReasoningRequest:
    request_id: str
    device_id: str
    sensor_type: str
    trigger_name: str
    prompt: str
    context: GatewayReasoningContext
    action_tier_hint: str
    timeout_ms: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> GatewayReasoningRequest:
        return cls(
            request_id=_as_str(payload.get("request_id"), "request_id"),
            device_id=_as_str(payload.get("device_id"), "device_id"),
            sensor_type=_as_str(payload.get("sensor_type"), "sensor_type"),
            trigger_name=_as_str(payload.get("trigger_name"), "trigger_name"),
            prompt=_as_str(payload.get("prompt"), "prompt"),
            context=GatewayReasoningContext.from_dict(
                _as_mapping(payload.get("context"), "context")
            ),
            action_tier_hint=_as_action_tier(
                payload.get("action_tier_hint"), "action_tier_hint"
            ),
            timeout_ms=_as_int(payload.get("timeout_ms"), "timeout_ms"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "trigger_name": self.trigger_name,
            "prompt": self.prompt,
            "context": self.context.to_dict(),
            "action_tier_hint": self.action_tier_hint,
            "timeout_ms": self.timeout_ms,
        }


@dataclass(frozen=True)
class GatewayReasoningResponse:
    request_id: str
    text: str
    model: str
    tokens_used: int
    latency_ms: int
    confidence: float
    action_tier: str
    proposed_action: str | None

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> GatewayReasoningResponse:
        proposed_raw = payload.get("proposed_action")
        if proposed_raw is not None and not isinstance(proposed_raw, str):
            raise ValueError("proposed_action must be string or null")
        return cls(
            request_id=_as_str(payload.get("request_id"), "request_id"),
            text=_as_str(payload.get("text"), "text"),
            model=_as_str(payload.get("model"), "model"),
            tokens_used=_as_int(payload.get("tokens_used"), "tokens_used"),
            latency_ms=_as_int(payload.get("latency_ms"), "latency_ms"),
            confidence=_as_float(payload.get("confidence"), "confidence"),
            action_tier=_as_action_tier(payload.get("action_tier"), "action_tier"),
            proposed_action=proposed_raw,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "text": self.text,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "confidence": self.confidence,
            "action_tier": self.action_tier,
            "proposed_action": self.proposed_action,
        }
