# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Health payload helper utilities for interpreting runtime health snapshots.

These are read-only functions that consume typed HealthStatus objects and
produce diagnostic summaries — they make no network calls.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ori_sdk.errors import HealthClientError
from ori_sdk.models import CapabilityPosture, HealthStatus


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
