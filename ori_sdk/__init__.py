# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Public package surface for ori-sdk-python."""

from ori_sdk.errors import (
    GatewayContractError,
    HealthClientError,
    OriSDKError,
    SkillMetadataValidationError,
)
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
from ori_sdk.health import RuntimeHealthClient
from ori_sdk.helpers import (
    PostureReport,
    StalenessReport,
    error_code_from_health_failure,
    posture_interpretation,
    staleness_summary,
)
from ori_sdk.models import (
    AlertTimestamps,
    CapabilityPosture,
    DevicePolicyState,
    GatewayContextHistoryPoint,
    GatewayReasoningContext,
    GatewayReasoningRequest,
    GatewayReasoningResponse,
    HealthError,
    HealthResponse,
    HealthStatus,
    SensorStatus,
)
from ori_sdk.validation import validate_skill_metadata, validate_skill_metadata_file

__all__ = [
    # errors
    "GatewayContractError",
    "HealthClientError",
    "OriSDKError",
    "SkillMetadataValidationError",
    # gateway
    "GATEWAY_HEALTH_TOPIC",
    "GatewayRetryPolicy",
    "build_gateway_reasoning_request",
    "gateway_request_topic",
    "gateway_response_topic",
    "new_request_id",
    "parse_gateway_reasoning_response",
    "response_matches_request",
    "validate_response",
    # health client
    "RuntimeHealthClient",
    # helpers
    "PostureReport",
    "StalenessReport",
    "error_code_from_health_failure",
    "posture_interpretation",
    "staleness_summary",
    # models
    "AlertTimestamps",
    "CapabilityPosture",
    "DevicePolicyState",
    "GatewayContextHistoryPoint",
    "GatewayReasoningContext",
    "GatewayReasoningRequest",
    "GatewayReasoningResponse",
    "HealthError",
    "HealthResponse",
    "HealthStatus",
    "SensorStatus",
    # validation
    "validate_skill_metadata",
    "validate_skill_metadata_file",
]
