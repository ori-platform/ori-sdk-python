# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Gateway API v1 topic and envelope helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from ori_sdk.errors import ORI_SDK_REQUEST_ID_MISMATCH, GatewayContractError
from ori_sdk.models import GatewayReasoningRequest, GatewayReasoningResponse

GATEWAY_HEALTH_TOPIC = "ori/gateway/health"


def gateway_request_topic(device_id: str) -> str:
    device = device_id.strip()
    if not device:
        raise ValueError("device_id must not be empty")
    return f"ori/{device}/reasoning/request"


def gateway_response_topic(device_id: str) -> str:
    device = device_id.strip()
    if not device:
        raise ValueError("device_id must not be empty")
    return f"ori/{device}/reasoning/response"


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
    request_payload: dict[str, object] = {
        "request_id": request_id or new_request_id(),
        "device_id": device_id,
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
    return GatewayReasoningResponse.from_dict(payload)


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


@dataclass(frozen=True)
class GatewayRetryPolicy:
    timeout_ms: int = 10_000
    max_retries: int = 1

    def total_attempts(self) -> int:
        return self.max_retries + 1
