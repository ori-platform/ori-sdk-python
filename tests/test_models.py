# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ori_sdk.models import (
    AlertTimestamps,
    DevicePolicyState,
    GatewayReasoningRequest,
    GatewayReasoningResponse,
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
    assert parsed.to_dict() == payload


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
    assert parsed.to_dict() == payload
