# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ori_sdk
from ori_sdk.errors import (
    ORI_SDK_DEVICE_ID_MISMATCH,
    ORI_SDK_EXPORT_TYPE_MISMATCH,
    ORI_SDK_PROPOSAL_ID_MISMATCH,
    ORI_SDK_REQUEST_ID_MISMATCH,
    GatewayContractError,
)
from ori_sdk.gateway import (
    GATEWAY_HEALTH_TOPIC,
    GATEWAY_REASONING_REQUEST_TOPIC_FILTER,
    RUNTIME_NODE_HEARTBEAT_TOPIC_FILTER,
    TIER_C_ENRICHMENT_REQUEST_TOPIC_FILTER,
    GatewayRetryPolicy,
    build_gateway_reasoning_request,
    export_request_topic,
    export_response_topic,
    export_response_topic_filter,
    gateway_request_topic,
    gateway_response_topic,
    new_request_id,
    parse_gateway_reasoning_response,
    response_matches_request,
    runtime_node_heartbeat_topic,
    tier_c_enrichment_request_topic,
    tier_c_enrichment_response_topic,
    validate_export_response,
    validate_response,
    validate_tier_c_enrichment_response,
)
from ori_sdk.gateway_models import (
    RuntimeExportRequest,
    RuntimeExportResponse,
    TierCEnrichmentRequest,
    TierCEnrichmentResponse,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_gateway_api_v1_helpers_are_public_exports() -> None:
    assert {
        "RUNTIME_NODE_HEARTBEAT_TOPIC_FILTER",
        "TIER_C_ENRICHMENT_REQUEST_TOPIC_FILTER",
        "runtime_node_heartbeat_topic",
        "export_request_topic",
        "export_response_topic",
        "export_response_topic_filter",
        "tier_c_enrichment_request_topic",
        "tier_c_enrichment_response_topic",
        "validate_export_response",
        "validate_tier_c_enrichment_response",
    } <= set(ori_sdk.__all__)


def test_gateway_topics_include_device_id() -> None:
    assert gateway_request_topic("site-a") == "ori/site-a/reasoning/request"
    assert gateway_response_topic("site-a") == "ori/site-a/reasoning/response"
    assert GATEWAY_HEALTH_TOPIC == "ori/gateway/health"
    assert GATEWAY_REASONING_REQUEST_TOPIC_FILTER == "ori/+/reasoning/request"


def test_runtime_heartbeat_topic_helper() -> None:
    assert runtime_node_heartbeat_topic("site-a") == "ori/site-a/runtime/heartbeat"
    assert RUNTIME_NODE_HEARTBEAT_TOPIC_FILTER == "ori/+/runtime/heartbeat"
    with pytest.raises(ValueError, match="MQTT topic"):
        runtime_node_heartbeat_topic("site/a")


def test_export_topic_helpers() -> None:
    assert export_request_topic("site-a") == "ori/site-a/export/request"
    assert (
        export_response_topic("site-a", "request_123")
        == "ori/site-a/export/response/request_123"
    )
    assert export_response_topic_filter("site-a") == "ori/site-a/export/response/+"
    with pytest.raises(ValueError, match="MQTT topic"):
        export_request_topic("site/a")
    with pytest.raises(ValueError, match="MQTT topic"):
        export_response_topic("site/a", "request-1")
    with pytest.raises(ValueError, match="MQTT topic"):
        export_response_topic_filter("site/a")


def test_tier_c_enrichment_topic_helpers() -> None:
    assert (
        tier_c_enrichment_request_topic("site-a")
        == "ori/site-a/tier_c/enrichment/request"
    )
    assert (
        tier_c_enrichment_response_topic("site-a")
        == "ori/site-a/tier_c/enrichment/response"
    )
    assert TIER_C_ENRICHMENT_REQUEST_TOPIC_FILTER == "ori/+/tier_c/enrichment/request"
    with pytest.raises(ValueError, match="MQTT topic"):
        tier_c_enrichment_request_topic("site/a")
    with pytest.raises(ValueError, match="MQTT topic"):
        tier_c_enrichment_response_topic("site/a")


@pytest.mark.parametrize(
    "device_id",
    ["", " site-a", "site-a ", "site/a", "site+a", "site#a", "site|a"],
)
def test_gateway_topics_reject_invalid_device_ids(device_id: str) -> None:
    with pytest.raises(ValueError):
        gateway_request_topic(device_id)
    with pytest.raises(ValueError):
        gateway_response_topic(device_id)


@pytest.mark.parametrize(
    "request_id",
    ["", " request", "request ", "request/id", "request.id", "réquest", "a" * 129],
)
def test_export_response_topic_rejects_invalid_request_ids(
    request_id: str,
) -> None:
    with pytest.raises(ValueError):
        export_response_topic("site-a", request_id)


def test_gateway_topics_do_not_use_legacy_gateway_namespace() -> None:
    request_topic = gateway_request_topic("site-a")
    response_topic = gateway_response_topic("site-a")
    legacy_fragments = [
        "ori/gateway/site-a/reason/request",
        "ori/gateway/site-a/reason/response",
        "/reason/request",
        "/reason/response",
    ]
    for fragment in legacy_fragments:
        assert fragment not in request_topic
        assert fragment not in response_topic


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


def test_gateway_request_builder_uses_strict_identifier_validation() -> None:
    with pytest.raises(ValueError, match="request_id must not be empty"):
        build_gateway_reasoning_request(
            request_id="",
            device_id="site-a",
            sensor_type="current_clamp",
            trigger_name="dangerous_overcurrent",
            prompt="Is this dangerous?",
            context_value=14.2,
            context_unit="A",
            context_timestamp=123,
            context_history=[],
            action_tier_hint="D",
        )
    with pytest.raises(ValueError, match="auth delimiters"):
        build_gateway_reasoning_request(
            request_id="request-1",
            device_id="site|a",
            sensor_type="current_clamp",
            trigger_name="dangerous_overcurrent",
            prompt="Is this dangerous?",
            context_value=14.2,
            context_unit="A",
            context_timestamp=123,
            context_history=[],
            action_tier_hint="D",
        )
    with pytest.raises(ValueError, match="ASCII"):
        build_gateway_reasoning_request(
            request_id="request.1",
            device_id="site-a",
            sensor_type="current_clamp",
            trigger_name="dangerous_overcurrent",
            prompt="Is this dangerous?",
            context_value=14.2,
            context_unit="A",
            context_timestamp=123,
            context_history=[],
            action_tier_hint="D",
        )


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


def test_gateway_response_parser_uses_strict_request_id_validation() -> None:
    payload = json.loads((FIXTURES / "gateway_reasoning_response.json").read_text())
    payload["request_id"] = "request.with.dot"

    with pytest.raises(ValueError, match="ASCII"):
        parse_gateway_reasoning_response(payload)


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


def test_gateway_error_response_correlation() -> None:
    req_payload = json.loads((FIXTURES / "gateway_reasoning_request.json").read_text())
    resp_payload = json.loads(
        (FIXTURES / "gateway_reasoning_error_response.json").read_text()
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
    assert response.error == "provider timeout"
    validate_response(request, response)


def test_validate_export_response_checks_all_correlation_fields() -> None:
    request_payload = json.loads((FIXTURES / "runtime_export_request.json").read_text())
    response_payload = json.loads(
        (FIXTURES / "runtime_export_response.json").read_text()
    )
    request = RuntimeExportRequest.from_dict(request_payload)
    response = RuntimeExportResponse.from_dict(response_payload)
    validate_export_response(request, response)

    expected_codes = {
        "request_id": ORI_SDK_REQUEST_ID_MISMATCH,
        "device_id": ORI_SDK_DEVICE_ID_MISMATCH,
        "export_type": ORI_SDK_EXPORT_TYPE_MISMATCH,
    }
    for field_name, expected_code in expected_codes.items():
        mismatched = dict(response_payload)
        mismatched[field_name] = (
            "health" if field_name == "export_type" else "different"
        )
        with pytest.raises(GatewayContractError, match=field_name) as error_info:
            validate_export_response(
                request, RuntimeExportResponse.from_dict(mismatched)
            )
        assert error_info.value.code == expected_code


def test_validate_tier_c_enrichment_response_checks_both_ids() -> None:
    request_payload = json.loads(
        (FIXTURES / "tier_c_enrichment_request.json").read_text()
    )
    response_payload = json.loads(
        (FIXTURES / "tier_c_enrichment_response.json").read_text()
    )
    request = TierCEnrichmentRequest.from_dict(request_payload)
    response = TierCEnrichmentResponse.from_dict(response_payload)
    validate_tier_c_enrichment_response(request, response)

    expected_codes = {
        "request_id": ORI_SDK_REQUEST_ID_MISMATCH,
        "proposal_id": ORI_SDK_PROPOSAL_ID_MISMATCH,
    }
    for field_name, expected_code in expected_codes.items():
        mismatched = dict(response_payload)
        mismatched[field_name] = "different"
        with pytest.raises(GatewayContractError, match=field_name) as error_info:
            validate_tier_c_enrichment_response(
                request, TierCEnrichmentResponse.from_dict(mismatched)
            )
        assert error_info.value.code == expected_code
