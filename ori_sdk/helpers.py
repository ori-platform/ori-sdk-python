# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Health payload helper utilities for interpreting runtime health snapshots.

These are read-only functions that consume typed HealthStatus objects and
produce diagnostic summaries — they make no network calls.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, TypedDict

from ori_sdk.errors import HealthClientError
from ori_sdk.models import CapabilityPosture, HealthStatus


class SensorFreshness(TypedDict):
    """Freshness diagnostics for one runtime-reported sensor."""

    sensor_id: str
    delta_ms: int | None
    timestamp_status: Literal["observed", "missing", "future"]
    runtime_stale: bool
    degraded_reasons: list[str]


class SensorFreshnessSummary(TypedDict):
    """Freshness diagnostics for all sensors in a health snapshot."""

    sensors: list[SensorFreshness]
    any_degraded: bool


class AlertChannelSummary(TypedDict):
    """Runtime alert-channel and global outbox posture."""

    sms_runtime_available: bool
    whatsapp_runtime_available: bool
    internet_available: bool
    outbox_backlog_count: int
    outbox_oldest_age_ms: int | None
    degraded: bool
    degraded_reasons: list[str]


class TierExecutionState(TypedDict):
    """Authority invariant and execution readiness for one action tier."""

    authority_model: Literal[
        "advisory",
        "runtime_policy",
        "operator_approval",
        "deterministic_safety",
    ]
    execution_ready: bool | None
    degraded_reasons: list[str]


class TierCapabilitySummary(TypedDict):
    """Execution diagnostics for all four action tiers."""

    tier_a: TierExecutionState
    tier_b: TierExecutionState
    tier_c: TierExecutionState
    tier_d: TierExecutionState


class EvidenceSummary(TypedDict):
    """Public evidence posture without private implementation details."""

    enabled: bool
    available: bool
    public_key_hex: str
    artifact_version: str
    protocol_version: str
    action_event_type: str
    chain_head_hash: str | None
    pending_export_count: int | None
    last_attested_action_id: int | None
    attestation_gap_count: int
    degraded: bool
    degraded_reasons: list[str]


class RemoteCommandLockoutAggregate(TypedDict):
    """Identity-free aggregate of remote-command sender risk."""

    enforcement_enabled: bool
    total_sender_count: int
    elevated_count: int
    critical_count: int
    locked_out_count: int
    stale_count: int
    degraded: bool


class RuntimePostureSummary(TypedDict):
    """Broad runtime posture with sender identities removed."""

    gateway_broker_degraded: bool
    state_store_encryption_degraded: bool
    alert_outbox_degraded: bool
    evidence_degraded: bool
    remote_command_lockout: RemoteCommandLockoutAggregate
    degraded: bool
    degraded_reasons: list[str]


@dataclass(frozen=True)
class StalenessReport:
    """Staleness analysis of every sensor in a health snapshot.

    ``stale_sensors`` maps sensor_id → milliseconds since last reading.
    A value of ``-1`` means the sensor is flagged stale but ``last_seen_ms``
    was not available in the snapshot.
    """

    stale_sensors: dict[str, int]
    fresh_sensors: list[str]

    @property
    def any_stale(self) -> bool:
        return bool(self.stale_sensors)


@dataclass(frozen=True)
class PostureReport:
    """Human-readable capability summary derived from a CapabilityPosture."""

    available: bool
    gateway_reachable: bool
    local_slm_loaded: bool
    sms_available: bool
    whatsapp_available: bool
    relay_connected: bool
    internet_available: bool
    available_tiers: list[str]
    summary: str


def sensor_freshness_delta(
    status: HealthStatus,
    *,
    now_ms: int | None = None,
) -> SensorFreshnessSummary:
    """Return signed timestamp deltas while preserving runtime stale verdicts."""
    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    sensors: list[SensorFreshness] = []
    any_degraded = False

    for sensor in status.sensors:
        reasons: list[str] = []
        if not sensor.connected:
            reasons.append("sensor_disconnected")

        if sensor.last_seen_ms is None:
            delta_ms = None
            timestamp_status: Literal["observed", "missing", "future"] = "missing"
            reasons.append("timestamp_missing")
        else:
            delta_ms = current_ms - sensor.last_seen_ms
            if delta_ms < 0:
                timestamp_status = "future"
                reasons.append("timestamp_in_future")
            else:
                timestamp_status = "observed"

        if sensor.stale:
            reasons.append("runtime_stale")

        any_degraded = any_degraded or bool(reasons)
        sensors.append(
            {
                "sensor_id": sensor.id,
                "delta_ms": delta_ms,
                "timestamp_status": timestamp_status,
                "runtime_stale": sensor.stale,
                "degraded_reasons": reasons,
            }
        )

    return {"sensors": sensors, "any_degraded": any_degraded}


def alert_channel_summary(status: HealthStatus) -> AlertChannelSummary:
    """Summarize runtime availability without claiming provider delivery."""
    posture = status.capability_posture
    outbox = status.alert_outbox
    reasons: list[str] = []

    if not posture.available:
        reasons.append("capability_posture_unavailable")
    else:
        if not posture.sms_available:
            reasons.append("sms_runtime_unavailable")
        if not posture.whatsapp_available:
            reasons.append("whatsapp_runtime_unavailable")
        if not posture.internet_available:
            reasons.append("internet_unavailable")

    if outbox.backlog_count > 0:
        reasons.append("alert_outbox_backlog")

    return {
        "sms_runtime_available": posture.sms_available,
        "whatsapp_runtime_available": posture.whatsapp_available,
        "internet_available": posture.internet_available,
        "outbox_backlog_count": outbox.backlog_count,
        "outbox_oldest_age_ms": outbox.oldest_queued_age_ms,
        "degraded": bool(reasons),
        "degraded_reasons": reasons,
    }


def tier_capability_summary(status: HealthStatus) -> TierCapabilitySummary:
    """Separate invariant tier authority from observed execution readiness."""
    alert_summary = alert_channel_summary(status)
    posture = status.capability_posture

    if not posture.available:
        tier_a_ready: bool | None = None
    else:
        tier_a_ready = bool(
            posture.sms_available
            or (posture.whatsapp_available and posture.internet_available)
        )

    return {
        "tier_a": {
            "authority_model": "advisory",
            "execution_ready": tier_a_ready,
            "degraded_reasons": list(alert_summary["degraded_reasons"]),
        },
        "tier_b": _physical_tier_state(
            status,
            authority_model="runtime_policy",
            policy_field="relay_b_enabled",
        ),
        "tier_c": _physical_tier_state(
            status,
            authority_model="operator_approval",
            policy_field="relay_c_enabled",
        ),
        "tier_d": _physical_tier_state(
            status,
            authority_model="deterministic_safety",
            policy_field=None,
        ),
    }


def evidence_summary(status: HealthStatus) -> EvidenceSummary:
    """Summarize public evidence metadata without validating artifact identity."""
    evidence = status.evidence
    reasons: list[str] = []
    if evidence.enabled and not evidence.available:
        reasons.append("evidence_unavailable")
    if evidence.attestation_gap_count > 0:
        reasons.append("attestation_gaps_present")

    return {
        "enabled": evidence.enabled,
        "available": evidence.available,
        "public_key_hex": evidence.public_key_hex,
        "artifact_version": evidence.artifact_version,
        "protocol_version": evidence.protocol_version,
        "action_event_type": evidence.action_event_type,
        "chain_head_hash": evidence.chain_head_hash,
        "pending_export_count": evidence.pending_export_count,
        "last_attested_action_id": evidence.last_attested_action_id,
        "attestation_gap_count": evidence.attestation_gap_count,
        "degraded": bool(reasons),
        "degraded_reasons": reasons,
    }


def runtime_posture_summary(status: HealthStatus) -> RuntimePostureSummary:
    """Return broad posture diagnostics with no sender-level information."""
    gateway = status.gateway_broker_posture
    encryption = status.state_store_encryption
    outbox = status.alert_outbox
    evidence = evidence_summary(status)
    lockout = _remote_command_lockout_aggregate(status)

    gateway_degraded = not gateway.available or (
        gateway.gateway_enabled and gateway.requires_acl_hardening
    )
    encryption_degraded = not encryption.available or (
        encryption.mode == "filesystem_required" and not encryption.satisfied
    )
    outbox_degraded = outbox.backlog_count > 0
    evidence_degraded = evidence["degraded"]

    reasons: list[str] = []
    if gateway_degraded:
        reasons.append("gateway_broker_posture_degraded")
    if encryption_degraded:
        reasons.append("state_store_encryption_degraded")
    if outbox_degraded:
        reasons.append("alert_outbox_degraded")
    if evidence_degraded:
        reasons.append("evidence_degraded")
    if lockout["degraded"]:
        reasons.append("remote_command_lockout_degraded")

    return {
        "gateway_broker_degraded": gateway_degraded,
        "state_store_encryption_degraded": encryption_degraded,
        "alert_outbox_degraded": outbox_degraded,
        "evidence_degraded": evidence_degraded,
        "remote_command_lockout": lockout,
        "degraded": bool(reasons),
        "degraded_reasons": reasons,
    }


def staleness_summary(
    status: HealthStatus,
    *,
    now_ms: int | None = None,
) -> StalenessReport:
    """Return which sensors are stale and by how long (in milliseconds).

    If *now_ms* is not provided the current wall-clock time is used.
    """
    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    stale: dict[str, int] = {}
    fresh: list[str] = []
    for sensor in status.sensors:
        if sensor.stale:
            if sensor.last_seen_ms is not None:
                age_ms = max(0, current_ms - sensor.last_seen_ms)
                stale[sensor.id] = age_ms
            else:
                stale[sensor.id] = -1
        else:
            fresh.append(sensor.id)
    return StalenessReport(stale_sensors=stale, fresh_sensors=fresh)


def posture_interpretation(status: HealthStatus) -> PostureReport:
    """Interpret a CapabilityPosture snapshot into available tiers and a summary.

    Deprecated:
        Use :func:`tier_capability_summary` for current runtime v2 semantics.
        This function preserves its original return type and lossy tier mapping
        for backward compatibility.

    Tier availability is based on which capabilities are signalled by the
    runtime posture — this mirrors the IntelligenceElevator selection logic.

    Tier A  — always available (informational alerts, logging).
    Tier B  — requires at least one alert channel (SMS or WhatsApp).
    Tier C  — requires a reasoning engine (gateway or local SLM).
    Tier D  — always available (safety-critical, bypass-LLM path).
    """
    posture: CapabilityPosture = status.capability_posture
    tiers: list[str] = []

    if posture.available:
        tiers.append("A")
        if posture.sms_available or posture.whatsapp_available:
            tiers.append("B")
        if posture.gateway_reachable or posture.local_slm_loaded:
            tiers.append("C")
        tiers.append("D")

    summary = _build_posture_summary(posture, tiers)
    return PostureReport(
        available=posture.available,
        gateway_reachable=posture.gateway_reachable,
        local_slm_loaded=posture.local_slm_loaded,
        sms_available=posture.sms_available,
        whatsapp_available=posture.whatsapp_available,
        relay_connected=posture.relay_connected,
        internet_available=posture.internet_available,
        available_tiers=tiers,
        summary=summary,
    )


def error_code_from_health_failure(error: HealthClientError) -> str:
    """Return the ORI-SDK-* code from a HealthClientError.

    Convenience wrapper — callers can also access ``error.code`` directly.
    """
    return error.code


# ── Private helpers ───────────────────────────────────────────────────────────


def _physical_tier_state(
    status: HealthStatus,
    *,
    authority_model: Literal[
        "runtime_policy", "operator_approval", "deterministic_safety"
    ],
    policy_field: Literal["relay_b_enabled", "relay_c_enabled"] | None,
) -> TierExecutionState:
    posture = status.capability_posture
    reasons: list[str] = []
    execution_blocked = False

    if not posture.available:
        reasons.append("capability_posture_unavailable")
    elif not posture.relay_connected:
        reasons.append("relay_disconnected")
        execution_blocked = True

    if policy_field is not None:
        policy = status.device_policy
        if policy.enabled and not policy.available:
            reasons.append("device_policy_unavailable")
        elif policy.enabled:
            if policy.is_expired is True:
                reasons.append("device_policy_expired")
                execution_blocked = True
            elif policy.is_expired is None:
                reasons.append("device_policy_state_incomplete")
            policy_value = (
                policy.relay_b_enabled
                if policy_field == "relay_b_enabled"
                else policy.relay_c_enabled
            )
            if policy_value is False:
                disabled_reason = (
                    "device_policy_relay_b_disabled"
                    if policy_field == "relay_b_enabled"
                    else "device_policy_relay_c_disabled"
                )
                reasons.append(disabled_reason)
                execution_blocked = True
            elif (
                policy_value is None and "device_policy_state_incomplete" not in reasons
            ):
                reasons.append("device_policy_state_incomplete")

    if execution_blocked:
        return {
            "authority_model": authority_model,
            "execution_ready": False,
            "degraded_reasons": reasons,
        }

    reasons.append("deployment_context_unavailable")
    return {
        "authority_model": authority_model,
        "execution_ready": None,
        "degraded_reasons": reasons,
    }


def _remote_command_lockout_aggregate(
    status: HealthStatus,
) -> RemoteCommandLockoutAggregate:
    lockout = status.remote_command_lockout
    elevated_count = 0
    critical_count = 0
    locked_out_count = 0
    stale_count = 0

    for sender in lockout.senders:
        if sender.risk_level == "elevated":
            elevated_count += 1
        elif sender.risk_level == "critical":
            critical_count += 1
        if sender.locked_out:
            locked_out_count += 1
        if sender.stale:
            stale_count += 1

    degraded = bool(elevated_count or critical_count or locked_out_count or stale_count)
    return {
        "enforcement_enabled": lockout.enforcement_enabled,
        "total_sender_count": len(lockout.senders),
        "elevated_count": elevated_count,
        "critical_count": critical_count,
        "locked_out_count": locked_out_count,
        "stale_count": stale_count,
        "degraded": degraded,
    }


def _build_posture_summary(posture: CapabilityPosture, tiers: list[str]) -> str:
    if not posture.available:
        return "Capability posture unavailable — all tiers degraded to Tier D only."
    parts: list[str] = [f"Tiers available: {', '.join(tiers) if tiers else 'none'}."]
    if not posture.internet_available:
        parts.append("No internet.")
    if not posture.gateway_reachable:
        parts.append("Gateway unreachable.")
    if not posture.local_slm_loaded:
        parts.append("Local SLM not loaded.")
    if not posture.relay_connected:
        parts.append("Relay disconnected.")
    return " ".join(parts)
