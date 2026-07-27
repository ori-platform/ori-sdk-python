# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from threading import Barrier
from typing import cast

import pytest

import ori_sdk
from ori_sdk.errors import (
    ORI_SDK_EXPORT_TYPE_MISMATCH,
    ORI_SDK_GATEWAY_SESSION_DUPLICATE,
    ORI_SDK_GATEWAY_SESSION_EXHAUSTED,
    ORI_SDK_GATEWAY_SESSION_INVALID,
    ORI_SDK_GATEWAY_SESSION_NOT_FOUND,
    ORI_SDK_GATEWAY_SESSION_TIMEOUT,
    GatewayContractError,
    GatewaySessionError,
)
from ori_sdk.firmware_telemetry import FirmwareHeartbeatEnvelope
from ori_sdk.gateway import GatewayRetryPolicy, validate_export_response
from ori_sdk.gateway_models import (
    ExportType,
    RuntimeExportRequest,
    RuntimeExportResponse,
    RuntimeNodeHeartbeat,
    TierCEnrichmentRequest,
    TierCEnrichmentResponse,
)
from ori_sdk.gateway_session import (
    ActiveSessionRegistry,
    GatewaySession,
    GatewaySessionFamily,
    GatewaySessionRequest,
    GatewaySessionResponse,
)
from ori_sdk.models import (
    GatewayReasoningContext,
    GatewayReasoningRequest,
    GatewayReasoningResponse,
)


def _reasoning_request(
    request_id: str = "reasoning-1",
    *,
    device_id: str = "site-a",
    timeout_ms: int = 1_000,
) -> GatewayReasoningRequest:
    return GatewayReasoningRequest(
        request_id=request_id,
        device_id=device_id,
        sensor_type="current_clamp",
        trigger_name="overcurrent",
        prompt="Explain the current reading.",
        context=GatewayReasoningContext(
            value=14.2,
            unit="A",
            timestamp=1_720_000_000_000,
            history=[],
        ),
        action_tier_hint="A",
        timeout_ms=timeout_ms,
    )


def _reasoning_response(
    request_id: str = "reasoning-1",
) -> GatewayReasoningResponse:
    return GatewayReasoningResponse(
        request_id=request_id,
        text="The current is above its normal range.",
        model="local-model",
        tokens_used=12,
        latency_ms=20,
        confidence=0.8,
        action_tier="A",
        proposed_action=None,
    )


def _export_request(
    request_id: str = "export-1",
    *,
    device_id: str = "site-a",
    export_type: ExportType = "health",
) -> RuntimeExportRequest:
    return RuntimeExportRequest(
        request_id=request_id,
        export_type=export_type,
        device_id=device_id,
    )


def _export_response(
    request_id: str = "export-1",
    *,
    device_id: str = "site-a",
    export_type: str = "health",
) -> RuntimeExportResponse:
    return RuntimeExportResponse(
        request_id=request_id,
        export_type=export_type,
        device_id=device_id,
        items=(),
        next_page_token="",
        complete=True,
    )


def _tier_c_request(
    request_id: str = "enrichment-1",
    *,
    proposal_id: str = "proposal-1",
    device_id: str = "site-a",
    timeout_ms: int = 1_500,
) -> TierCEnrichmentRequest:
    return TierCEnrichmentRequest(
        request_id=request_id,
        proposal_id=proposal_id,
        device_id=device_id,
        skill_name="cold-room",
        trigger_name="compressor-risk",
        sensor_id="current-main",
        sensor_type="current_clamp",
        reading_value=14.2,
        unit="A",
        history_window=(),
        proposed_action="isolate_compressor",
        safe_default_action="alert_operator",
        operator_message="Compressor isolation needs approval.",
        timeout_ms=timeout_ms,
    )


def _tier_c_response(
    request_id: str = "enrichment-1",
    *,
    proposal_id: str = "proposal-1",
) -> TierCEnrichmentResponse:
    return TierCEnrichmentResponse(
        request_id=request_id,
        proposal_id=proposal_id,
        explanation="The current pattern supports operator review.",
    )


def test_gateway_session_api_is_public() -> None:
    expected = {
        "ActiveSessionRegistry",
        "GatewaySession",
        "GatewaySessionError",
        "GatewaySessionFamily",
        "GatewaySessionRequest",
        "GatewaySessionResponse",
    }
    assert expected <= set(ori_sdk.__all__)
    assert all(hasattr(ori_sdk, name) for name in expected)


def test_session_family_metadata() -> None:
    reasoning = GatewaySession(_reasoning_request(), now=10.0)
    runtime_export = GatewaySession(
        _export_request(),
        GatewayRetryPolicy(timeout_ms=2_000),
        now=20.0,
    )
    tier_c = GatewaySession(_tier_c_request(), now=30.0)

    assert reasoning.family is GatewaySessionFamily.REASONING
    assert reasoning.request_id == "reasoning-1"
    assert reasoning.device_id == "site-a"
    assert reasoning.proposal_id is None
    assert reasoning.request_topic == "ori/site-a/reasoning/request"
    assert reasoning.response_topic == "ori/site-a/reasoning/response"
    assert reasoning.timeout_ms == 1_000

    assert runtime_export.family is GatewaySessionFamily.RUNTIME_EXPORT
    assert runtime_export.request_id == "export-1"
    assert runtime_export.proposal_id is None
    assert runtime_export.request_topic == "ori/site-a/export/request"
    assert runtime_export.response_topic == "ori/site-a/export/response/export-1"
    assert runtime_export.timeout_ms == 2_000

    assert tier_c.family is GatewaySessionFamily.TIER_C_ENRICHMENT
    assert tier_c.request_id == "enrichment-1"
    assert tier_c.proposal_id == "proposal-1"
    assert tier_c.request_topic == "ori/site-a/tier_c/enrichment/request"
    assert tier_c.response_topic == "ori/site-a/tier_c/enrichment/response"
    assert tier_c.timeout_ms == 1_500


def test_heartbeat_is_not_session_family() -> None:
    assert set(GatewaySessionFamily) == {
        GatewaySessionFamily.REASONING,
        GatewaySessionFamily.RUNTIME_EXPORT,
        GatewaySessionFamily.TIER_C_ENRICHMENT,
    }
    runtime_heartbeat = RuntimeNodeHeartbeat(
        device_id="site-a",
        status="healthy",
        last_seen_ms=1,
        gateway_seen_ms=2,
    )
    firmware_heartbeat = FirmwareHeartbeatEnvelope(
        v=1,
        alg="ed25519",
        device_id="firmware-a",
        boot_id=1,
        seq=1,
        capability_hash=f"sha256:{'a' * 64}",
        posture="development",
        device_uptime_ms=100,
        emitted_at_ms=None,
    )

    for heartbeat in (runtime_heartbeat, firmware_heartbeat):
        with pytest.raises(GatewaySessionError) as error_info:
            GatewaySession(cast(GatewaySessionRequest, heartbeat))
        assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_INVALID


def test_session_correlates_response() -> None:
    reasoning = GatewaySession(_reasoning_request(), now=0.0)
    runtime_export = GatewaySession(_export_request(), now=0.0)
    tier_c = GatewaySession(_tier_c_request(), now=0.0)

    assert reasoning.is_correlated(_reasoning_response()) is True
    assert runtime_export.is_correlated(_export_response()) is True
    assert tier_c.is_correlated(_tier_c_response()) is True


def test_session_correlation_returns_false_for_wrong_family_or_identifiers() -> None:
    reasoning = GatewaySession(_reasoning_request(), now=0.0)
    runtime_export = GatewaySession(_export_request(), now=0.0)
    tier_c = GatewaySession(_tier_c_request(), now=0.0)

    assert reasoning.is_correlated(_reasoning_response("other")) is False
    assert reasoning.is_correlated(_export_response()) is False
    assert runtime_export.is_correlated(_export_response("other")) is False
    assert runtime_export.is_correlated(_export_response(device_id="site-b")) is False
    assert tier_c.is_correlated(_tier_c_response("other")) is False
    assert tier_c.is_correlated(_tier_c_response(proposal_id="proposal-2")) is False


def test_export_type_enforcement_remains_post_correlation() -> None:
    request = _export_request(export_type="health")
    response = _export_response(export_type="sensor_history")
    session = GatewaySession(request, now=0.0)

    assert session.is_correlated(response) is True
    with pytest.raises(GatewayContractError) as error_info:
        validate_export_response(request, response)
    assert error_info.value.code == ORI_SDK_EXPORT_TYPE_MISMATCH


def test_session_does_not_parse_raw_response_payloads() -> None:
    session = GatewaySession(_reasoning_request(), now=0.0)
    malformed = {"request_id": session.request_id}

    with pytest.raises(ValueError):
        GatewayReasoningResponse.from_dict(malformed)
    assert session.is_correlated(cast(GatewaySessionResponse, malformed)) is False


def test_next_attempt_preserves_request_id() -> None:
    request = _reasoning_request(timeout_ms=250)
    session = GatewaySession(
        request,
        GatewayRetryPolicy(timeout_ms=9_000, max_retries=2),
        now=10.0,
    )
    retried = session.next_attempt(now=20.0)

    assert retried is not session
    assert retried.request is request
    assert retried.request_id == session.request_id
    assert retried.family is session.family
    assert retried.device_id == session.device_id
    assert retried.attempt == 2
    assert retried.total_attempts == 3
    assert retried.attempt_started_at == 20.0
    assert retried.attempt_deadline == 20.25
    assert session.attempt == 1
    assert session.attempt_deadline == 10.25


def test_late_response_to_earlier_attempt_still_correlates() -> None:
    session = GatewaySession(_reasoning_request(), now=0.0)
    response = _reasoning_response(session.request_id)

    retried = session.next_attempt(now=2.0)

    assert retried.is_correlated(response) is True


def test_request_id_is_stable_across_every_attempt() -> None:
    initial = GatewaySession(
        _export_request(),
        GatewayRetryPolicy(timeout_ms=100, max_retries=3),
        now=0.0,
    )
    attempts = [initial]

    for attempt_number in range(2, initial.total_attempts + 1):
        attempts.append(attempts[-1].next_attempt(now=float(attempt_number)))

    assert [session.attempt for session in attempts] == [1, 2, 3, 4]
    assert {session.request_id for session in attempts} == {initial.request_id}
    assert {session.response_topic for session in attempts} == {initial.response_topic}


def test_timeout_boundary_and_error_are_deterministic() -> None:
    session = GatewaySession(_reasoning_request(timeout_ms=500), now=10.0)

    assert session.is_timed_out(now=10.499) is False
    session.ensure_active(now=10.499)
    assert session.is_timed_out(now=10.5) is True
    with pytest.raises(GatewaySessionError) as error_info:
        session.ensure_active(now=10.5)
    assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_TIMEOUT


def test_timeout_source_is_family_specific() -> None:
    policy = GatewayRetryPolicy(timeout_ms=7_000)
    reasoning = GatewaySession(_reasoning_request(timeout_ms=100), policy, now=1.0)
    runtime_export = GatewaySession(_export_request(), policy, now=1.0)
    tier_c = GatewaySession(_tier_c_request(timeout_ms=300), policy, now=1.0)

    assert reasoning.attempt_deadline == 1.1
    assert runtime_export.attempt_deadline == 8.0
    assert tier_c.attempt_deadline == 1.3


def test_next_attempt_raises_typed_exhaustion_error() -> None:
    session = GatewaySession(
        _reasoning_request(),
        GatewayRetryPolicy(max_retries=1),
        now=0.0,
    )
    final_attempt = session.next_attempt(now=1.0)

    with pytest.raises(GatewaySessionError) as error_info:
        final_attempt.next_attempt(now=2.0)
    assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_EXHAUSTED


@pytest.mark.parametrize("now", [-1.0, float("inf"), float("-inf"), float("nan")])
def test_session_rejects_invalid_monotonic_time(now: float) -> None:
    with pytest.raises(GatewaySessionError) as error_info:
        GatewaySession(_reasoning_request(), now=now)
    assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_INVALID


def test_session_rejects_boolean_monotonic_time() -> None:
    with pytest.raises(GatewaySessionError) as error_info:
        GatewaySession(_reasoning_request(), now=cast(float, True))
    assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_INVALID


@pytest.mark.parametrize("timeout_ms", [0, -1])
def test_retry_policy_rejects_non_positive_timeout(timeout_ms: int) -> None:
    with pytest.raises(ValueError, match="timeout_ms must be positive"):
        GatewayRetryPolicy(timeout_ms=timeout_ms)


def test_retry_policy_rejects_boolean_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_ms must be an integer"):
        GatewayRetryPolicy(timeout_ms=cast(int, True))


def test_retry_policy_rejects_negative_retry_count() -> None:
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        GatewayRetryPolicy(max_retries=-1)


def test_retry_policy_rejects_boolean_retry_count() -> None:
    with pytest.raises(ValueError, match="max_retries must be an integer"):
        GatewayRetryPolicy(max_retries=cast(int, False))


def test_session_rejects_invalid_direct_reasoning_request_metadata() -> None:
    invalid_id = _reasoning_request(request_id="")
    invalid_device = _reasoning_request(device_id="site/a")
    invalid_timeout = _reasoning_request(timeout_ms=0)

    for request in (invalid_id, invalid_device, invalid_timeout):
        with pytest.raises(GatewaySessionError) as error_info:
            GatewaySession(request)
        assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_INVALID


def test_public_constructor_cannot_forge_attempt_state() -> None:
    parameters = inspect.signature(GatewaySession).parameters
    assert "attempt" not in parameters
    assert "_attempt" not in parameters

    session = GatewaySession(_reasoning_request(), now=0.0)
    with pytest.raises(FrozenInstanceError):
        setattr(session, "attempt", 2)


def test_registry_rejects_duplicate_without_replacing_first_session() -> None:
    registry = ActiveSessionRegistry()
    first = GatewaySession(_reasoning_request(), now=0.0)
    duplicate = GatewaySession(_reasoning_request(), now=1.0)
    registry.register(first)

    with pytest.raises(GatewaySessionError) as error_info:
        registry.register(duplicate)

    assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_DUPLICATE
    assert registry.get(first.request_id) is first
    assert len(registry) == 1


def test_registry_lookup_snapshot_and_completion() -> None:
    registry = ActiveSessionRegistry()
    second = GatewaySession(_export_request("request-b"), now=0.0)
    first = GatewaySession(_reasoning_request("request-a"), now=0.0)
    registry.register(second)
    registry.register(first)

    assert "request-a" in registry
    assert object() not in registry
    assert registry.require("request-a") is first
    assert registry.snapshot() == (first, second)
    assert registry.complete("request-a") is first
    assert registry.get("request-a") is None
    assert "request-a" not in registry

    with pytest.raises(GatewaySessionError) as error_info:
        registry.complete("request-a")
    assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_NOT_FOUND


def test_registry_retry_updates_attempt_atomically() -> None:
    registry = ActiveSessionRegistry()
    initial = GatewaySession(
        _reasoning_request(),
        GatewayRetryPolicy(max_retries=1),
        now=0.0,
    )
    registry.register(initial)

    retried = registry.retry(initial.request_id, now=5.0)

    assert retried.attempt == 2
    assert retried.request_id == initial.request_id
    assert registry.require(initial.request_id) is retried

    with pytest.raises(GatewaySessionError) as error_info:
        registry.retry(initial.request_id, now=6.0)
    assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_EXHAUSTED
    assert registry.require(initial.request_id) is retried


def test_registry_evicts_timed_out() -> None:
    registry = ActiveSessionRegistry()
    later = GatewaySession(
        _export_request("request-b"),
        GatewayRetryPolicy(timeout_ms=200),
        now=0.0,
    )
    first = GatewaySession(
        _export_request("request-a"),
        GatewayRetryPolicy(timeout_ms=100),
        now=0.0,
    )
    active = GatewaySession(
        _export_request("request-c"),
        GatewayRetryPolicy(timeout_ms=300),
        now=0.0,
    )
    for session in (later, first, active):
        registry.register(session)

    evicted = registry.evict_timed_out(now=0.2)

    assert evicted == (first, later)
    assert registry.snapshot() == (active,)
    assert len(registry) == 1
    for session in evicted:
        with pytest.raises(GatewaySessionError) as error_info:
            session.ensure_active(now=0.2)
        assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_TIMEOUT


def test_registry_rejects_invalid_lookup_id() -> None:
    registry = ActiveSessionRegistry()

    with pytest.raises(GatewaySessionError) as error_info:
        registry.get("invalid/id")
    assert error_info.value.code == ORI_SDK_GATEWAY_SESSION_INVALID


def test_registry_duplicate_registration_is_thread_safe() -> None:
    worker_count = 16
    registry = ActiveSessionRegistry()
    session = GatewaySession(_reasoning_request(), now=0.0)
    barrier = Barrier(worker_count)

    def register_once() -> str:
        barrier.wait()
        try:
            registry.register(session)
        except GatewaySessionError as exc:
            return exc.code
        return "registered"

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(register_once) for _ in range(worker_count)]
        results = [future.result() for future in futures]

    assert results.count("registered") == 1
    assert results.count(ORI_SDK_GATEWAY_SESSION_DUPLICATE) == worker_count - 1
    assert registry.snapshot() == (session,)


def test_registry_completion_and_eviction_are_thread_safe() -> None:
    registry = ActiveSessionRegistry()
    session = GatewaySession(
        _export_request(),
        GatewayRetryPolicy(timeout_ms=100),
        now=0.0,
    )
    registry.register(session)
    barrier = Barrier(2)

    def complete_once() -> str:
        barrier.wait()
        try:
            registry.complete(session.request_id)
        except GatewaySessionError as exc:
            return exc.code
        return "completed"

    def evict_once() -> str:
        barrier.wait()
        return "evicted" if registry.evict_timed_out(now=1.0) == (session,) else "empty"

    with ThreadPoolExecutor(max_workers=2) as executor:
        complete_future = executor.submit(complete_once)
        evict_future = executor.submit(evict_once)
        results = {complete_future.result(), evict_future.result()}

    assert results in (
        {"completed", "empty"},
        {"evicted", ORI_SDK_GATEWAY_SESSION_NOT_FOUND},
    )
    assert len(registry) == 0
