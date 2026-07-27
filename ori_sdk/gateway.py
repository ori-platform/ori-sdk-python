# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Gateway API v1 topic and envelope helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from ori_sdk.errors import (
    ORI_SDK_DEVICE_ID_MISMATCH,
    ORI_SDK_EXPORT_TYPE_MISMATCH,
    ORI_SDK_PROPOSAL_ID_MISMATCH,
    ORI_SDK_REQUEST_ID_MISMATCH,
    GatewayContractError,
)
from ori_sdk.gateway_models import (
    RuntimeExportRequest,
    RuntimeExportResponse,
    TierCEnrichmentRequest,
    TierCEnrichmentResponse,
    _validate_mqtt_device_id,
    _validate_mqtt_request_id,
)
from ori_sdk.models import GatewayReasoningRequest, GatewayReasoningResponse

GATEWAY_HEALTH_TOPIC = "ori/gateway/health"
GATEWAY_REASONING_REQUEST_TOPIC_FILTER = "ori/+/reasoning/request"
RUNTIME_NODE_HEARTBEAT_TOPIC_FILTER = "ori/+/runtime/heartbeat"
TIER_C_ENRICHMENT_REQUEST_TOPIC_FILTER = "ori/+/tier_c/enrichment/request"


def gateway_request_topic(device_id: str) -> str:
    device = _validate_mqtt_device_id(device_id)
    return f"ori/{device}/reasoning/request"


def gateway_response_topic(device_id: str) -> str:
    device = _validate_mqtt_device_id(device_id)
    return f"ori/{device}/reasoning/response"


def runtime_node_heartbeat_topic(device_id: str) -> str:
    device = _validate_mqtt_device_id(device_id)
    return f"ori/{device}/runtime/heartbeat"


def export_request_topic(device_id: str) -> str:
    device = _validate_mqtt_device_id(device_id)
    return f"ori/{device}/export/request"


def export_response_topic(device_id: str, request_id: str) -> str:
    device = _validate_mqtt_device_id(device_id)
    request = _validate_mqtt_request_id(request_id)
    return f"ori/{device}/export/response/{request}"


def export_response_topic_filter(device_id: str) -> str:
    device = _validate_mqtt_device_id(device_id)
    return f"ori/{device}/export/response/+"


def tier_c_enrichment_request_topic(device_id: str) -> str:
    device = _validate_mqtt_device_id(device_id)
    return f"ori/{device}/tier_c/enrichment/request"


def tier_c_enrichment_response_topic(device_id: str) -> str:
    device = _validate_mqtt_device_id(device_id)
    return f"ori/{device}/tier_c/enrichment/response"


def new_request_id() -> str:
    return str(uuid.uuid4())


def build_gateway_reasoning_request(
    *,
    device_id: str,
    sensor_type: str,
    trigger_name: str,
    prompt: str,
    context_value: float,
    context_unit: str,
    context_timestamp: int,
    context_history: list[dict[str, float | int]],
    action_tier_hint: str,
    timeout_ms: int = 10_000,
    request_id: str | None = None,
) -> GatewayReasoningRequest:
    validated_device_id = _validate_mqtt_device_id(device_id)
    candidate_request_id = new_request_id() if request_id is None else request_id
    validated_request_id = _validate_mqtt_request_id(candidate_request_id)
    request_payload: dict[str, object] = {
        "request_id": validated_request_id,
        "device_id": validated_device_id,
        "sensor_type": sensor_type,
        "trigger_name": trigger_name,
        "prompt": prompt,
        "context": {
            "value": context_value,
            "unit": context_unit,
            "timestamp": context_timestamp,
            "history": context_history,
        },
        "action_tier_hint": action_tier_hint,
        "timeout_ms": timeout_ms,
    }
    return GatewayReasoningRequest.from_dict(request_payload)


def parse_gateway_reasoning_response(
    payload: dict[str, object],
) -> GatewayReasoningResponse:
    response = GatewayReasoningResponse.from_dict(payload)
    _validate_mqtt_request_id(response.request_id)
    return response


def response_matches_request(
    request: GatewayReasoningRequest,
    response: GatewayReasoningResponse,
) -> bool:
    return request.request_id == response.request_id


def validate_response(
    request: GatewayReasoningRequest,
    response: GatewayReasoningResponse,
) -> None:
    """Assert that *response* echoes the *request* request_id.

    Raises GatewayContractError (SDK-6) if the IDs do not match — a contract
    violation that must never be silently swallowed.
    """
    if request.request_id != response.request_id:
        raise GatewayContractError(
            f"response request_id {response.request_id!r} does not match "
            f"request request_id {request.request_id!r}",
            code=ORI_SDK_REQUEST_ID_MISMATCH,
        )


def validate_export_response(
    request: RuntimeExportRequest,
    response: RuntimeExportResponse,
) -> None:
    """Validate export response correlation without changing either envelope."""
    if request.request_id != response.request_id:
        raise GatewayContractError(
            f"response request_id {response.request_id!r} does not match "
            f"request request_id {request.request_id!r}",
            code=ORI_SDK_REQUEST_ID_MISMATCH,
        )
    if request.device_id != response.device_id:
        raise GatewayContractError(
            f"response device_id {response.device_id!r} does not match "
            f"request device_id {request.device_id!r}",
            code=ORI_SDK_DEVICE_ID_MISMATCH,
        )
    if request.export_type != response.export_type:
        raise GatewayContractError(
            f"response export_type {response.export_type!r} does not match "
            f"request export_type {request.export_type!r}",
            code=ORI_SDK_EXPORT_TYPE_MISMATCH,
        )


def validate_tier_c_enrichment_response(
    request: TierCEnrichmentRequest,
    response: TierCEnrichmentResponse,
) -> None:
    """Validate both identifiers that bind a Tier C enrichment exchange."""
    if request.request_id != response.request_id:
        raise GatewayContractError(
            f"response request_id {response.request_id!r} does not match "
            f"request request_id {request.request_id!r}",
            code=ORI_SDK_REQUEST_ID_MISMATCH,
        )
    if request.proposal_id != response.proposal_id:
        raise GatewayContractError(
            f"response proposal_id {response.proposal_id!r} does not match "
            f"request proposal_id {request.proposal_id!r}",
            code=ORI_SDK_PROPOSAL_ID_MISMATCH,
        )


@dataclass(frozen=True)
class GatewayRetryPolicy:
    timeout_ms: int = 10_000
    max_retries: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int):
            raise ValueError("timeout_ms must be an integer")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int):
            raise ValueError("max_retries must be an integer")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")

    def total_attempts(self) -> int:
        return self.max_retries + 1
