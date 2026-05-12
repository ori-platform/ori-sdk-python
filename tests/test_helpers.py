# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ori_sdk.errors import ORI_SDK_CONNECTION_REFUSED, HealthClientError
from ori_sdk.helpers import (
    error_code_from_health_failure,
    posture_interpretation,
    staleness_summary,
)
from ori_sdk.models import HealthResponse

FIXTURES = Path(__file__).parent / "fixtures"


def _load_health_status():  # type: ignore[return]
    payload = json.loads((FIXTURES / "runtime_health_success.json").read_text())
    resp = HealthResponse.from_dict(payload)
    assert resp.health is not None
    return resp.health


def test_staleness_summary_no_stale_sensors() -> None:
    status = _load_health_status()
    report = staleness_summary(status, now_ms=200)
    assert not report.any_stale
    assert "mains-current" in report.fresh_sensors
    assert report.stale_sensors == {}


def test_staleness_summary_with_stale_sensor() -> None:
    status = _load_health_status()
    # Patch: create a status with a stale sensor using model fields.
    from dataclasses import replace

    stale_sensor = replace(status.sensors[0], stale=True, last_seen_ms=100)
    stale_status = replace(status, sensors=[stale_sensor])

    report = staleness_summary(stale_status, now_ms=5100)
    assert report.any_stale
    assert "mains-current" in report.stale_sensors
    assert report.stale_sensors["mains-current"] == 5000


def test_staleness_summary_stale_no_last_seen() -> None:
    status = _load_health_status()
    from dataclasses import replace

    stale_sensor = replace(status.sensors[0], stale=True, last_seen_ms=None)
    stale_status = replace(status, sensors=[stale_sensor])

    report = staleness_summary(stale_status, now_ms=9999)
    assert report.stale_sensors["mains-current"] == -1


def test_posture_interpretation_all_available() -> None:
    status = _load_health_status()
    report = posture_interpretation(status)
    assert report.available is True
    assert "A" in report.available_tiers
    assert "D" in report.available_tiers
    # Fixture has sms_available=True → Tier B available
    assert "B" in report.available_tiers
    # Fixture has local_slm_loaded=True → Tier C available
    assert "C" in report.available_tiers
    assert "Tiers available:" in report.summary


def test_posture_interpretation_unavailable_posture() -> None:
    status = _load_health_status()
    from dataclasses import replace

    posture = replace(status.capability_posture, available=False)
    status2 = replace(status, capability_posture=posture)
    report = posture_interpretation(status2)
    assert report.available is False
    assert report.available_tiers == []
    assert "unavailable" in report.summary.lower()


def test_error_code_from_health_failure() -> None:
    exc = HealthClientError("refused", code=ORI_SDK_CONNECTION_REFUSED)
    assert error_code_from_health_failure(exc) == ORI_SDK_CONNECTION_REFUSED
