# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import ori_sdk
from ori_sdk.gateway_models import (
    JsonValue,
    RuntimeExportRequest,
    RuntimeExportResponse,
    RuntimeNodeHeartbeat,
    RuntimeNodeHeartbeatEvidence,
    TierCEnrichmentHistorySample,
    TierCEnrichmentRequest,
    TierCEnrichmentResponse,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict[str, object]:
    payload: object = json.loads((FIXTURES / name).read_text())
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def _tier_c_request() -> TierCEnrichmentRequest:
    return TierCEnrichmentRequest.from_dict(_fixture("tier_c_enrichment_request.json"))


def _compact_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def test_gateway_models_are_public_exports() -> None:
    assert ori_sdk.RuntimeNodeHeartbeat is RuntimeNodeHeartbeat
    assert ori_sdk.RuntimeNodeHeartbeatEvidence is RuntimeNodeHeartbeatEvidence
    assert ori_sdk.RuntimeExportRequest is RuntimeExportRequest
    assert ori_sdk.RuntimeExportResponse is RuntimeExportResponse
    assert ori_sdk.TierCEnrichmentHistorySample is TierCEnrichmentHistorySample
    assert ori_sdk.TierCEnrichmentRequest is TierCEnrichmentRequest
    assert ori_sdk.TierCEnrichmentResponse is TierCEnrichmentResponse
    assert {
        "ExportType",
        "JsonObject",
        "JsonScalar",
        "JsonValue",
        "RuntimeNodeHeartbeat",
        "RuntimeNodeHeartbeatEvidence",
        "RuntimeNodeStatus",
        "RuntimeExportRequest",
        "RuntimeExportResponse",
        "TierCEnrichmentHistorySample",
        "TierCEnrichmentRequest",
        "TierCEnrichmentResponse",
    } <= set(ori_sdk.__all__)


def test_runtime_node_heartbeat_evidence_round_trip() -> None:
    payload = _fixture("runtime_node_heartbeat_evidence.json")
    heartbeat = RuntimeNodeHeartbeat.from_dict(payload)

    assert heartbeat.evidence is not None
    assert heartbeat.evidence.attestation_gap_count == 2
    assert heartbeat.evidence.action_event_type == "SAFETY_ACTION_EXECUTED"
    assert heartbeat.to_dict() == payload
    assert (
        _compact_json(heartbeat.to_dict())
        == (FIXTURES / "runtime_node_heartbeat_evidence.json").read_text().strip()
    )


def test_runtime_node_heartbeat_without_evidence_round_trip() -> None:
    payload: dict[str, object] = {
        "device_id": "dev-01",
        "status": "degraded",
        "last_seen_ms": 1234567890000,
        "gateway_seen_ms": 0,
        "active_triggers": ["high_current"],
    }

    assert RuntimeNodeHeartbeat.from_dict(payload).to_dict() == payload


def test_evidence_accepts_future_bounded_event_vocabulary() -> None:
    evidence = RuntimeNodeHeartbeatEvidence(
        chain_head_hash="",
        attestation_gap_count=0,
        available=True,
        action_event_type="FUTURE_VOCABULARY_TYPE",
    )

    assert evidence.action_event_type == "FUTURE_VOCABULARY_TYPE"


def test_export_request_round_trip() -> None:
    payload = _fixture("runtime_export_request.json")
    request = RuntimeExportRequest.from_dict(payload)

    assert request.request_id == "uuid4-string"
    assert request.params["sensor_id"] == "current-main"
    assert request.to_dict() == payload


def test_export_response_round_trip() -> None:
    payload = _fixture("runtime_export_response.json")
    assert RuntimeExportResponse.from_dict(payload).to_dict() == payload


def test_export_response_error_round_trip() -> None:
    payload = _fixture("runtime_export_error_response.json")
    assert RuntimeExportResponse.from_dict(payload).to_dict() == payload


def test_export_error_response_preserves_unknown_export_type_sentinel() -> None:
    payload: dict[str, object] = {
        "request_id": "invalid",
        "export_type": "unknown",
        "device_id": "site-a-edge-01",
        "items": [],
        "next_page_token": "",
        "complete": True,
        "error": "request payload must be JSON",
    }

    assert RuntimeExportResponse.from_dict(payload).to_dict() == payload


def test_export_response_preserves_pagination_and_items() -> None:
    payload = _fixture("runtime_export_response.json")
    payload["items"] = [{"sensor_id": "current-main", "value": 4.2}]
    payload["next_page_token"] = "500"
    payload["complete"] = False

    response = RuntimeExportResponse.from_dict(payload)

    assert response.next_page_token == "500"
    assert response.complete is False
    assert response.to_dict() == payload


def test_tier_c_enrichment_round_trip() -> None:
    request_payload = _fixture("tier_c_enrichment_request.json")
    response_payload = _fixture("tier_c_enrichment_response.json")
    request = TierCEnrichmentRequest.from_dict(request_payload)
    response = TierCEnrichmentResponse.from_dict(response_payload)

    assert request.timeout_ms == 10_000
    assert request.history_window[0].quality == 0.98
    assert request.to_dict() == request_payload
    assert response.to_dict() == response_payload
    assert (
        _compact_json(request.to_dict())
        == (FIXTURES / "tier_c_enrichment_request.json").read_text().strip()
    )
    assert (
        _compact_json(response.to_dict())
        == (FIXTURES / "tier_c_enrichment_response.json").read_text().strip()
    )


def test_tier_c_enrichment_error_response_round_trip() -> None:
    payload = _fixture("tier_c_enrichment_error_response.json")
    response = TierCEnrichmentResponse.from_dict(payload)
    assert response.to_dict() == payload
    assert (
        _compact_json(response.to_dict())
        == (FIXTURES / "tier_c_enrichment_error_response.json").read_text().strip()
    )


def test_public_model_constructors_enforce_identifier_contract() -> None:
    heartbeat = RuntimeNodeHeartbeat.from_dict(
        _fixture("runtime_node_heartbeat_evidence.json")
    )
    export_request = RuntimeExportRequest.from_dict(
        _fixture("runtime_export_request.json")
    )
    export_response = RuntimeExportResponse.from_dict(
        _fixture("runtime_export_response.json")
    )
    tier_c_request = _tier_c_request()
    tier_c_response = TierCEnrichmentResponse.from_dict(
        _fixture("tier_c_enrichment_response.json")
    )

    with pytest.raises(ValueError, match="auth delimiters"):
        replace(heartbeat, device_id="site|a")
    with pytest.raises(ValueError, match="ASCII"):
        replace(export_request, request_id="request.with.dot")
    with pytest.raises(ValueError, match="ASCII"):
        replace(export_response, request_id="request.with.dot")
    with pytest.raises(ValueError, match="ASCII"):
        replace(tier_c_request, proposal_id="proposal.with.dot")
    with pytest.raises(ValueError, match="ASCII"):
        replace(tier_c_response, request_id="request.with.dot")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"chain_head_hash": "A" * 64}, "lowercase hexadecimal"),
        ({"chain_head_hash": "a" * 63}, "64 lowercase"),
        ({"attestation_gap_count": -1}, "must be >= 0"),
        ({"available": 1}, "must be a boolean"),
        ({"action_event_type": "SafetyAction"}, "SCREAMING_SNAKE_CASE"),
        ({"action_event_type": "A" * 65}, "must not exceed 64 bytes"),
    ],
)
def test_evidence_constructor_rejects_invalid_values(
    overrides: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "chain_head_hash": "a" * 64,
        "attestation_gap_count": 0,
        "available": True,
        "action_event_type": "SAFETY_ACTION_EXECUTED",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        RuntimeNodeHeartbeatEvidence(
            chain_head_hash=cast(str, values["chain_head_hash"]),
            attestation_gap_count=cast(int, values["attestation_gap_count"]),
            available=cast(bool, values["available"]),
            action_event_type=cast(str, values["action_event_type"]),
        )


def test_runtime_heartbeat_constructor_rejects_unimplemented_starting_status() -> None:
    with pytest.raises(ValueError, match="healthy or degraded"):
        RuntimeNodeHeartbeat(
            device_id="site-a",
            status=cast(ori_sdk.RuntimeNodeStatus, "starting"),
            last_seen_ms=int(time.time() * 1_000),
            gateway_seen_ms=0,
        )


def test_runtime_heartbeat_rejects_future_timestamp() -> None:
    with pytest.raises(ValueError, match="too far in the future"):
        RuntimeNodeHeartbeat(
            device_id="site-a",
            status="healthy",
            last_seen_ms=int(time.time() * 1_000) + 600_000,
            gateway_seen_ms=0,
        )


@pytest.mark.parametrize(
    "active_triggers",
    [("",), (" trigger",), ("trigger ",), ("x" * 129,), tuple("x" for _ in range(65))],
)
def test_runtime_heartbeat_rejects_invalid_active_triggers(
    active_triggers: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="active_trigger"):
        RuntimeNodeHeartbeat(
            device_id="site-a",
            status="healthy",
            last_seen_ms=int(time.time() * 1_000),
            gateway_seen_ms=0,
            active_triggers=active_triggers,
        )


def test_logical_heartbeat_rejects_raw_auth_envelope() -> None:
    payload = _fixture("runtime_node_heartbeat_evidence.json")
    payload["auth"] = {
        "scheme": "hmac-sha256",
        "signed_at_ms": 1234567890000,
        "signature": "hmac-sha256:not-modeled-here",
    }

    with pytest.raises(ValueError, match="unknown fields: 'auth'"):
        RuntimeNodeHeartbeat.from_dict(payload)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("request_id", "request.with.dot", "ASCII"),
        ("device_id", "site|a", "auth delimiters"),
        ("export_type", "firmware", "export_type must be one of"),
        ("limit", 0, "limit must be >= 1"),
        ("page_token", "next-page", "non-negative integer"),
        ("until_ms", 1, "until_ms must be >= since_ms"),
    ],
)
def test_export_request_parser_rejects_invalid_envelope_fields(
    field_name: str, value: object, message: str
) -> None:
    payload = _fixture("runtime_export_request.json")
    payload[field_name] = value

    with pytest.raises(ValueError, match=message):
        RuntimeExportRequest.from_dict(payload)


def test_export_request_rejects_unparseable_large_page_token() -> None:
    payload = _fixture("runtime_export_request.json")
    payload["page_token"] = "1" * 5_000

    with pytest.raises(ValueError, match="non-negative integer"):
        RuntimeExportRequest.from_dict(payload)


def test_export_request_preserves_limit_for_runtime_side_bounding() -> None:
    payload = _fixture("runtime_export_request.json")
    payload["limit"] = 1_001

    request = RuntimeExportRequest.from_dict(payload)

    assert request.limit == 1_001
    assert request.to_dict()["limit"] == 1_001


def test_export_request_constructor_enforces_sensor_history_requirements() -> None:
    with pytest.raises(ValueError, match="since_ms and until_ms"):
        RuntimeExportRequest(
            request_id="request-1",
            export_type="sensor_history",
            device_id="site-a",
            params={"sensor_id": "current-main"},
        )
    with pytest.raises(ValueError, match="params.sensor_id"):
        RuntimeExportRequest(
            request_id="request-1",
            export_type="sensor_history",
            device_id="site-a",
            since_ms=1,
            until_ms=2,
            params={},
        )
    with pytest.raises(ValueError, match="params.bucket_ms"):
        RuntimeExportRequest(
            request_id="request-1",
            export_type="sensor_history",
            device_id="site-a",
            since_ms=1,
            until_ms=2,
            params={"sensor_id": "current-main", "bucket_ms": -1},
        )


@pytest.mark.parametrize(
    "mutation_field",
    ["command", "set_policy", "relay", "actuator", "delete_after_export"],
)
def test_export_request_rejects_mutation_fields(mutation_field: str) -> None:
    payload = _fixture("runtime_export_request.json")
    payload[mutation_field] = True

    with pytest.raises(ValueError, match="unknown fields"):
        RuntimeExportRequest.from_dict(payload)


def test_export_request_defensively_freezes_params() -> None:
    params: dict[str, JsonValue] = {
        "sensor_id": "current-main",
        "nested": {"samples": [1, 2]},
    }
    request = RuntimeExportRequest(
        request_id="request-1",
        export_type="sensor_history",
        device_id="site-a",
        since_ms=1,
        until_ms=2,
        params=params,
    )
    params["sensor_id"] = "changed"

    assert request.params["sensor_id"] == "current-main"
    assert request.to_dict()["params"] == {
        "sensor_id": "current-main",
        "nested": {"samples": [1, 2]},
    }


def test_export_response_error_constructor_enforces_error_envelope() -> None:
    with pytest.raises(ValueError, match="must contain no items"):
        RuntimeExportResponse(
            request_id="request-1",
            export_type="sensor_history",
            device_id="site-a",
            items=({"value": 1.0},),
            error="invalid request",
        )
    with pytest.raises(ValueError, match="complete to true"):
        RuntimeExportResponse(
            request_id="request-1",
            export_type="sensor_history",
            device_id="site-a",
            complete=False,
            error="invalid request",
        )


def test_export_response_constructor_enforces_runtime_page_bound() -> None:
    with pytest.raises(ValueError, match="more than 1000 entries"):
        RuntimeExportResponse(
            request_id="request-1",
            export_type="sensor_history",
            device_id="site-a",
            items=tuple({"row": index} for index in range(1_001)),
        )


@pytest.mark.parametrize(
    ("complete", "next_page_token", "message"),
    [
        (True, "10", "complete responses"),
        (False, "", "incomplete responses"),
    ],
)
def test_export_response_constructor_enforces_pagination(
    complete: bool, next_page_token: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        RuntimeExportResponse(
            request_id="request-1",
            export_type="sensor_history",
            device_id="site-a",
            complete=complete,
            next_page_token=next_page_token,
        )


def test_logical_export_response_rejects_transport_security_fields() -> None:
    payload = _fixture("runtime_export_response.json")
    payload["encrypted"] = True
    payload["encryption"] = {"scheme": "aes-256-gcm"}
    payload["auth"] = {"scheme": "hmac-sha256"}

    with pytest.raises(ValueError, match="unknown fields"):
        RuntimeExportResponse.from_dict(payload)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("request_id", "request.with.dot", "ASCII"),
        ("proposal_id", "proposal.with.dot", "ASCII"),
        ("device_id", "site|a", "auth delimiters"),
        ("skill_name", "", "skill_name must not be empty"),
        ("trigger_name", "", "trigger_name must not be empty"),
        ("sensor_id", "", "sensor_id must not be empty"),
        ("sensor_type", "", "sensor_type must not be empty"),
        ("proposed_action", "", "proposed_action must not be empty"),
        ("safe_default_action", "", "safe_default_action must not be empty"),
        ("operator_message", "", "operator_message must not be empty"),
        ("timeout_ms", 0, "timeout_ms must be positive"),
    ],
)
def test_tier_c_request_parser_rejects_invalid_contract_fields(
    field_name: str, value: object, message: str
) -> None:
    payload = _fixture("tier_c_enrichment_request.json")
    payload[field_name] = value

    with pytest.raises(ValueError, match=message):
        TierCEnrichmentRequest.from_dict(payload)


def test_tier_c_history_constructor_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        TierCEnrichmentHistorySample(
            sensor_id="sensor-a",
            sensor_type="current_clamp",
            unit="A",
            timestamp_ms=1,
            value=float("nan"),
            quality=1.0,
        )


def test_tier_c_request_constructor_validates_timeout() -> None:
    request = _tier_c_request()
    with pytest.raises(ValueError, match="timeout_ms must be positive"):
        TierCEnrichmentRequest(
            request_id=request.request_id,
            proposal_id=request.proposal_id,
            device_id=request.device_id,
            skill_name=request.skill_name,
            trigger_name=request.trigger_name,
            sensor_id=request.sensor_id,
            sensor_type=request.sensor_type,
            reading_value=request.reading_value,
            unit=request.unit,
            history_window=request.history_window,
            proposed_action=request.proposed_action,
            safe_default_action=request.safe_default_action,
            operator_message=request.operator_message,
            timeout_ms=0,
        )


@pytest.mark.parametrize(
    "authority_field",
    [
        "action_tier",
        "action_name",
        "safe_default_action",
        "approval_required",
        "relay",
        "actuator",
        "dispatch",
        "execution_status",
    ],
)
def test_tier_c_response_rejects_authority_fields(authority_field: str) -> None:
    payload = _fixture("tier_c_enrichment_response.json")
    payload[authority_field] = "not-authoritative"

    with pytest.raises(ValueError, match="unknown fields"):
        TierCEnrichmentResponse.from_dict(payload)


def test_tier_c_response_rejects_all_unknown_fields() -> None:
    payload = _fixture("tier_c_enrichment_response.json")
    payload["future_advisory_field"] = "not silently discarded"

    with pytest.raises(ValueError, match="future_advisory_field"):
        TierCEnrichmentResponse.from_dict(payload)


def test_tier_c_response_constructor_enforces_success_and_error_shapes() -> None:
    with pytest.raises(ValueError, match="explanation must not be empty"):
        TierCEnrichmentResponse(
            request_id="request-1",
            proposal_id="proposal-1",
        )
    with pytest.raises(ValueError, match="error must not be empty"):
        TierCEnrichmentResponse(
            request_id="request-1",
            proposal_id="proposal-1",
            error="",
        )
