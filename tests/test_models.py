# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from ori_sdk.models import (
    AlertOutboxState,
    AlertTimestamps,
    DevicePolicyState,
    EvidenceState,
    GatewayBrokerPosture,
    GatewayReasoningRequest,
    GatewayReasoningResponse,
    RemoteCommandLockoutState,
    StateStoreEncryptionPosture,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_gateway_reasoning_request_from_dict() -> None:
    payload = json.loads((FIXTURES / "gateway_reasoning_request.json").read_text())
    parsed = GatewayReasoningRequest.from_dict(payload)
    assert parsed.context.history[0].value == 8.1
    assert parsed.to_dict() == payload


def test_gateway_reasoning_response_from_dict() -> None:
    payload = json.loads((FIXTURES / "gateway_reasoning_response.json").read_text())
    parsed = GatewayReasoningResponse.from_dict(payload)
    assert parsed.action_tier == "D"
    assert parsed.error is None
    assert parsed.to_dict() == payload


def test_gateway_reasoning_error_response_from_dict() -> None:
    payload = json.loads(
        (FIXTURES / "gateway_reasoning_error_response.json").read_text()
    )
    parsed = GatewayReasoningResponse.from_dict(payload)
    assert parsed.error == "provider timeout"
    assert parsed.to_dict() == payload


def test_alert_timestamps_round_trip() -> None:
    payload = {"by_channel": {"sms": 100}, "by_trigger": {"overcurrent": 200}}
    parsed = AlertTimestamps.from_dict(payload)
    assert parsed.by_channel == {"sms": 100}
    assert parsed.by_trigger == {"overcurrent": 200}
    assert parsed.to_dict() == payload


def test_device_policy_state_available_round_trip() -> None:
    payload = {
        "available": True,
        "enabled": True,
        "policy_version": 3,
        "tier": "B",
        "relay_b_enabled": True,
        "relay_c_enabled": False,
        "cloud_llm_enabled": True,
        "valid_until": 9999,
        "issued_at": 1000,
        "is_expired": False,
    }
    parsed = DevicePolicyState.from_dict(payload)
    assert parsed.available is True
    assert parsed.tier == "B"
    assert parsed.to_dict() == {
        **payload,
        "alert_sms_monthly_cap": None,
        "alert_whatsapp_monthly_cap": None,
    }


def test_device_policy_state_unavailable_round_trip() -> None:
    payload = {
        "available": False,
        "enabled": False,
        "policy_version": None,
        "tier": None,
        "relay_b_enabled": None,
        "relay_c_enabled": None,
        "cloud_llm_enabled": None,
        "valid_until": None,
        "issued_at": None,
        "is_expired": None,
    }
    parsed = DevicePolicyState.from_dict(payload)
    assert parsed.available is False
    assert parsed.tier is None
    assert parsed.to_dict() == {
        **payload,
        "alert_sms_monthly_cap": None,
        "alert_whatsapp_monthly_cap": None,
    }


@pytest.mark.parametrize(
    ("sms_cap", "whatsapp_cap"),
    [(None, None), (-1, -1), (0, 0), (100, 250)],
)
def test_device_policy_alert_caps_round_trip(
    sms_cap: int | None, whatsapp_cap: int | None
) -> None:
    payload: dict[str, object] = {
        "available": True,
        "enabled": True,
        "policy_version": 3,
        "tier": "B",
        "relay_b_enabled": True,
        "relay_c_enabled": False,
        "cloud_llm_enabled": True,
        "valid_until": 9999,
        "issued_at": 1000,
        "is_expired": False,
        "alert_sms_monthly_cap": sms_cap,
        "alert_whatsapp_monthly_cap": whatsapp_cap,
    }

    assert DevicePolicyState.from_dict(payload).to_dict() == payload


@pytest.mark.parametrize("cap", [-2, -100, True, 1.5, "10"])
def test_device_policy_alert_caps_reject_invalid_values(cap: object) -> None:
    payload: dict[str, object] = {
        "available": True,
        "enabled": True,
        "policy_version": 3,
        "tier": "B",
        "relay_b_enabled": True,
        "relay_c_enabled": False,
        "cloud_llm_enabled": True,
        "valid_until": 9999,
        "issued_at": 1000,
        "is_expired": False,
        "alert_sms_monthly_cap": cap,
        "alert_whatsapp_monthly_cap": 0,
    }

    with pytest.raises(ValueError, match="alert_sms_monthly_cap"):
        DevicePolicyState.from_dict(payload)

    valid = DevicePolicyState.from_dict({**payload, "alert_sms_monthly_cap": 0})
    with pytest.raises(ValueError, match="alert_sms_monthly_cap"):
        replace(valid, alert_sms_monthly_cap=cast(int, cap))


def test_alert_outbox_state_round_trip() -> None:
    payload = {
        "backlog_count": 2,
        "oldest_queued_original_ts": 100,
        "oldest_queued_age_ms": 25,
        "retry_interval_minutes": 0.5,
        "max_non_tier_d_attempts": 10,
        "tier_d_critical_warning_threshold": 3,
        "batch_size": 50,
    }
    parsed = AlertOutboxState.from_dict(payload)
    assert parsed.backlog_count == 2
    assert parsed.to_dict() == payload


def test_remote_command_lockout_state_round_trip() -> None:
    payload = {
        "enforcement_enabled": True,
        "risk_window_ms": 3600000,
        "stale_after_ms": 3600000,
        "incident_sender_limit": 50,
        "senders": [
            {
                "channel": "sms",
                "from_number": "+2348012345678",
                "risk_level": "critical",
                "locked_out": True,
                "enforcement_enabled": True,
                "incident_count": 6,
                "rejection_count": 4,
                "window_ms": 3600000,
                "checked_at_ms": 123,
                "reason": "recent_security_incident",
                "stale": False,
            }
        ],
    }
    parsed = RemoteCommandLockoutState.from_dict(payload)
    assert parsed.senders[0].from_number == "+2348012345678"
    assert parsed.senders[0].locked_out is True
    assert parsed.to_dict() == payload


def test_gateway_broker_posture_round_trip() -> None:
    payload = {
        "available": True,
        "gateway_enabled": True,
        "deployment_check": "required",
        "anonymous_access": "disabled",
        "acl_policy": "per_device_required",
        "require_credentials": True,
        "credentials_configured": True,
        "requires_acl_hardening": False,
    }
    parsed = GatewayBrokerPosture.from_dict(payload)
    assert parsed.requires_acl_hardening is False
    assert parsed.to_dict() == payload


def test_state_store_encryption_posture_round_trip() -> None:
    payload = {
        "available": True,
        "mode": "filesystem_required",
        "satisfied": True,
        "marker_configured": False,
        "path_prefix_configured": True,
    }
    parsed = StateStoreEncryptionPosture.from_dict(payload)
    assert parsed.satisfied is True
    assert parsed.to_dict() == payload


def test_evidence_state_round_trip() -> None:
    payload = {
        "enabled": True,
        "available": True,
        "public_key_hex": "ab" * 32,
        "artifact_version": "0.2.0",
        "protocol_version": "evidence.v1",
        "action_event_type": "SAFETY_ACTION_EXECUTED",
        "chain_head_hash": "head-1",
        "pending_export_count": 0,
        "last_attested_action_id": 42,
        "attestation_gap_count": 0,
        "status_counts": {"signed": 3, "pending": 0},
    }
    parsed = EvidenceState.from_dict(payload)
    assert parsed.action_event_type == "SAFETY_ACTION_EXECUTED"
    assert parsed.to_dict() == payload
