# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ori_sdk.errors import GatewayContractError
from ori_sdk.gateway import (
    GATEWAY_HEALTH_TOPIC,
    GatewayRetryPolicy,
    build_gateway_reasoning_request,
    gateway_request_topic,
    gateway_response_topic,
    new_request_id,
    parse_gateway_reasoning_response,
    response_matches_request,
    validate_response,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_gateway_topics_include_device_id() -> None:
    assert gateway_request_topic("site-a") == "ori/gateway/site-a/reason/request"
    assert gateway_response_topic("site-a") == "ori/gateway/site-a/reason/response"
    assert GATEWAY_HEALTH_TOPIC == "ori/gateway/health"


def test_gateway_request_builder_preserves_request_id() -> None:
    expected_id = "7d4bd5ee-7f7e-4f11-bdab-a4b3fb3ca7a3"
    request = build_gateway_reasoning_request(
        request_id=expected_id,
        device_id="site-a",
        sensor_type="current_clamp",
        trigger_name="dangerous_overcurrent",
        prompt="Is this dangerous?",
        context_value=14.2,
        context_unit="A",
        context_timestamp=123,
        context_history=[{"value": 8.1, "timestamp": 111}],
        action_tier_hint="D",
        timeout_ms=10000,
    )
    assert request.request_id == expected_id


def test_gateway_response_correlation() -> None:
    req_payload = json.loads((FIXTURES / "gateway_reasoning_request.json").read_text())
    resp_payload = json.loads(
        (FIXTURES / "gateway_reasoning_response.json").read_text()
    )

    request = build_gateway_reasoning_request(
        request_id=str(req_payload["request_id"]),
        device_id=str(req_payload["device_id"]),
        sensor_type=str(req_payload["sensor_type"]),
        trigger_name=str(req_payload["trigger_name"]),
        prompt=str(req_payload["prompt"]),
        context_value=float(req_payload["context"]["value"]),
        context_unit=str(req_payload["context"]["unit"]),
        context_timestamp=int(req_payload["context"]["timestamp"]),
        context_history=list(req_payload["context"]["history"]),
        action_tier_hint=str(req_payload["action_tier_hint"]),
        timeout_ms=int(req_payload["timeout_ms"]),
    )
    response = parse_gateway_reasoning_response(resp_payload)
    assert response_matches_request(request, response) is True


def test_gateway_retry_policy_defaults() -> None:
    policy = GatewayRetryPolicy()
    assert policy.timeout_ms == 10_000
    assert policy.max_retries == 1
    assert policy.total_attempts() == 2


def test_new_request_id_is_non_empty_uuid_string() -> None:
    request_id = new_request_id()
    assert isinstance(request_id, str)
    assert len(request_id) > 10


def test_validate_response_passes_on_matching_request_id() -> None:
    req = build_gateway_reasoning_request(
        request_id="abc-123",
        device_id="site-a",
        sensor_type="current_clamp",
        trigger_name="test",
        prompt="p",
        context_value=1.0,
        context_unit="A",
        context_timestamp=0,
        context_history=[],
        action_tier_hint="A",
    )
    resp_payload = json.loads(
        (FIXTURES / "gateway_reasoning_response.json").read_text()
    )
    resp_payload["request_id"] = "abc-123"
    resp = parse_gateway_reasoning_response(resp_payload)
    validate_response(req, resp)  # must not raise


def test_validate_response_raises_on_mismatched_request_id() -> None:
    req = build_gateway_reasoning_request(
        request_id="abc-123",
        device_id="site-a",
        sensor_type="current_clamp",
        trigger_name="test",
        prompt="p",
        context_value=1.0,
        context_unit="A",
        context_timestamp=0,
        context_history=[],
        action_tier_hint="A",
    )
    resp_payload = json.loads(
        (FIXTURES / "gateway_reasoning_response.json").read_text()
    )
    resp_payload["request_id"] = "different-id"
    resp = parse_gateway_reasoning_response(resp_payload)
    with pytest.raises(GatewayContractError, match="does not match"):
        validate_response(req, resp)
