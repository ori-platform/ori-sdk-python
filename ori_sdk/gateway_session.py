# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Deterministic request lifecycle helpers for gateway MQTT exchanges.

This module owns retry, timeout, and in-process correlation state only. It does
not parse payloads, open MQTT connections, or enforce the full gateway response
contract.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock
from typing import TypeAlias

from ori_sdk.errors import (
    ORI_SDK_GATEWAY_SESSION_DUPLICATE,
    ORI_SDK_GATEWAY_SESSION_EXHAUSTED,
    ORI_SDK_GATEWAY_SESSION_INVALID,
    ORI_SDK_GATEWAY_SESSION_NOT_FOUND,
    ORI_SDK_GATEWAY_SESSION_TIMEOUT,
    GatewaySessionError,
)
from ori_sdk.gateway import (
    GatewayRetryPolicy,
    export_request_topic,
    export_response_topic,
    gateway_request_topic,
    gateway_response_topic,
    tier_c_enrichment_request_topic,
    tier_c_enrichment_response_topic,
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

GatewaySessionRequest: TypeAlias = (
    GatewayReasoningRequest | RuntimeExportRequest | TierCEnrichmentRequest
)
GatewaySessionResponse: TypeAlias = (
    GatewayReasoningResponse | RuntimeExportResponse | TierCEnrichmentResponse
)


class GatewaySessionFamily(StrEnum):
    """Closed set of gateway request/response exchanges with session semantics."""

    REASONING = "reasoning"
    RUNTIME_EXPORT = "runtime_export"
    TIER_C_ENRICHMENT = "tier_c_enrichment"


def _invalid_session(details: str) -> GatewaySessionError:
    return GatewaySessionError(details, code=ORI_SDK_GATEWAY_SESSION_INVALID)


def _monotonic_timestamp(now: float | None) -> float:
    value: object = time.monotonic() if now is None else now
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid_session("monotonic time must be a number")
    timestamp = float(value)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise _invalid_session("monotonic time must be finite and non-negative")
    return timestamp


def _positive_timeout_ms(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid_session(f"{field_name} must be an integer")
    if value <= 0:
        raise _invalid_session(f"{field_name} must be positive")
    return value


def _validated_request_id(request_id: object) -> str:
    try:
        return _validate_mqtt_request_id(request_id)
    except ValueError as exc:
        raise _invalid_session(str(exc)) from exc


def _validated_device_id(device_id: object) -> str:
    try:
        return _validate_mqtt_device_id(device_id)
    except ValueError as exc:
        raise _invalid_session(str(exc)) from exc


@dataclass(frozen=True, slots=True, init=False, eq=False)
class GatewaySession:
    """One immutable gateway request lifecycle.

    ``is_correlated()`` is deliberately a non-raising routing predicate over
    already-validated response models. Full response enforcement remains the
    job of ``validate_response()``, ``validate_export_response()``, or
    ``validate_tier_c_enrichment_response()`` after correlation.

    Reasoning and Tier C responses do not carry ``device_id``. Their device
    binding therefore remains an MQTT response-topic responsibility; this
    transport-free session checks only identifiers present in each response.
    ``attempt_started_at``, ``attempt_deadline``, and explicit ``now`` values
    use monotonic-clock seconds and must never be interpreted as wall time.
    """

    request: GatewaySessionRequest = field(repr=False)
    retry_policy: GatewayRetryPolicy
    family: GatewaySessionFamily
    request_id: str
    device_id: str
    proposal_id: str | None
    timeout_ms: int
    attempt: int
    attempt_started_at: float

    def __init__(
        self,
        request: GatewaySessionRequest,
        retry_policy: GatewayRetryPolicy | None = None,
        *,
        now: float | None = None,
    ) -> None:
        self._initialize(request, retry_policy, now=now, attempt=1)

    def _initialize(
        self,
        request: GatewaySessionRequest,
        retry_policy: GatewayRetryPolicy | None,
        *,
        now: float | None,
        attempt: int,
    ) -> None:
        policy = GatewayRetryPolicy() if retry_policy is None else retry_policy
        if not isinstance(policy, GatewayRetryPolicy):
            raise _invalid_session("retry_policy must be GatewayRetryPolicy")
        if isinstance(attempt, bool) or not isinstance(attempt, int):
            raise _invalid_session("attempt must be an integer")
        if attempt < 1 or attempt > policy.total_attempts():
            raise _invalid_session(
                f"attempt must be between 1 and {policy.total_attempts()}"
            )

        family: GatewaySessionFamily
        proposal_id: str | None = None
        if isinstance(request, GatewayReasoningRequest):
            family = GatewaySessionFamily.REASONING
            timeout_ms = _positive_timeout_ms(request.timeout_ms, "request.timeout_ms")
        elif isinstance(request, RuntimeExportRequest):
            family = GatewaySessionFamily.RUNTIME_EXPORT
            timeout_ms = _positive_timeout_ms(
                policy.timeout_ms, "retry_policy.timeout_ms"
            )
        elif isinstance(request, TierCEnrichmentRequest):
            family = GatewaySessionFamily.TIER_C_ENRICHMENT
            timeout_ms = _positive_timeout_ms(request.timeout_ms, "request.timeout_ms")
            proposal_id = _validated_request_id(request.proposal_id)
        else:
            raise _invalid_session(
                "request must be a reasoning, runtime export, or "
                "Tier C enrichment request"
            )

        object.__setattr__(self, "request", request)
        object.__setattr__(self, "retry_policy", policy)
        object.__setattr__(self, "family", family)
        object.__setattr__(
            self, "request_id", _validated_request_id(request.request_id)
        )
        object.__setattr__(self, "device_id", _validated_device_id(request.device_id))
        object.__setattr__(self, "proposal_id", proposal_id)
        object.__setattr__(self, "timeout_ms", timeout_ms)
        object.__setattr__(self, "attempt", attempt)
        object.__setattr__(self, "attempt_started_at", _monotonic_timestamp(now))

    @classmethod
    def _from_attempt(
        cls,
        request: GatewaySessionRequest,
        retry_policy: GatewayRetryPolicy,
        *,
        now: float,
        attempt: int,
    ) -> GatewaySession:
        session: GatewaySession = object.__new__(cls)
        session._initialize(request, retry_policy, now=now, attempt=attempt)
        return session

    @property
    def total_attempts(self) -> int:
        return self.retry_policy.total_attempts()

    @property
    def attempt_deadline(self) -> float:
        return self.attempt_started_at + (self.timeout_ms / 1_000)

    @property
    def request_topic(self) -> str:
        if self.family is GatewaySessionFamily.REASONING:
            return gateway_request_topic(self.device_id)
        if self.family is GatewaySessionFamily.RUNTIME_EXPORT:
            return export_request_topic(self.device_id)
        return tier_c_enrichment_request_topic(self.device_id)

    @property
    def response_topic(self) -> str:
        if self.family is GatewaySessionFamily.REASONING:
            return gateway_response_topic(self.device_id)
        if self.family is GatewaySessionFamily.RUNTIME_EXPORT:
            return export_response_topic(self.device_id, self.request_id)
        return tier_c_enrichment_response_topic(self.device_id)

    def is_timed_out(self, *, now: float | None = None) -> bool:
        """Return whether the current attempt has reached its deadline."""

        return _monotonic_timestamp(now) >= self.attempt_deadline

    def ensure_active(self, *, now: float | None = None) -> None:
        """Raise a typed timeout error if the current attempt has expired."""

        if self.is_timed_out(now=now):
            raise GatewaySessionError(
                f"gateway session {self.request_id!r} attempt {self.attempt} timed out",
                code=ORI_SDK_GATEWAY_SESSION_TIMEOUT,
            )

    def next_attempt(self, *, now: float | None = None) -> GatewaySession:
        """Return the next immutable attempt with a fresh per-attempt deadline."""

        if self.attempt >= self.total_attempts:
            raise GatewaySessionError(
                f"gateway session {self.request_id!r} exhausted "
                f"{self.total_attempts} attempts",
                code=ORI_SDK_GATEWAY_SESSION_EXHAUSTED,
            )
        timestamp = _monotonic_timestamp(now)
        return self._from_attempt(
            self.request,
            self.retry_policy,
            now=timestamp,
            attempt=self.attempt + 1,
        )

    def is_correlated(self, response: GatewaySessionResponse) -> bool:
        """Return whether a typed response belongs to this session.

        This method never parses mappings and never raises for an identifier or
        response-family mismatch.
        """

        if self.family is GatewaySessionFamily.REASONING:
            return (
                isinstance(response, GatewayReasoningResponse)
                and response.request_id == self.request_id
            )
        if self.family is GatewaySessionFamily.RUNTIME_EXPORT:
            return (
                isinstance(response, RuntimeExportResponse)
                and response.request_id == self.request_id
                and response.device_id == self.device_id
            )
        return (
            isinstance(response, TierCEnrichmentResponse)
            and response.request_id == self.request_id
            and response.proposal_id == self.proposal_id
        )


class ActiveSessionRegistry:
    """Thread-safe registry for synchronous gateway session lifecycle calls."""

    __slots__ = ("_lock", "_sessions")

    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, GatewaySession] = {}

    @staticmethod
    def _request_id(request_id: object) -> str:
        return _validated_request_id(request_id)

    def _require_locked(self, request_id: str) -> GatewaySession:
        session = self._sessions.get(request_id)
        if session is None:
            raise GatewaySessionError(
                f"gateway session {request_id!r} is not active",
                code=ORI_SDK_GATEWAY_SESSION_NOT_FOUND,
            )
        return session

    def register(self, session: GatewaySession) -> None:
        """Register a session without replacing an in-flight request."""

        if not isinstance(session, GatewaySession):
            raise _invalid_session("session must be GatewaySession")
        with self._lock:
            if session.request_id in self._sessions:
                raise GatewaySessionError(
                    f"gateway session {session.request_id!r} is already active",
                    code=ORI_SDK_GATEWAY_SESSION_DUPLICATE,
                )
            self._sessions[session.request_id] = session

    def get(self, request_id: str) -> GatewaySession | None:
        """Return an active session, or ``None`` when the ID is not registered."""

        validated_id = self._request_id(request_id)
        with self._lock:
            return self._sessions.get(validated_id)

    def require(self, request_id: str) -> GatewaySession:
        """Return an active session or raise a typed not-found error."""

        validated_id = self._request_id(request_id)
        with self._lock:
            return self._require_locked(validated_id)

    def retry(self, request_id: str, *, now: float | None = None) -> GatewaySession:
        """Atomically advance and store the next attempt for a session."""

        validated_id = self._request_id(request_id)
        timestamp = _monotonic_timestamp(now)
        with self._lock:
            current = self._require_locked(validated_id)
            next_session = current.next_attempt(now=timestamp)
            self._sessions[validated_id] = next_session
            return next_session

    def complete(self, request_id: str) -> GatewaySession:
        """Atomically remove and return a completed session."""

        validated_id = self._request_id(request_id)
        with self._lock:
            session = self._require_locked(validated_id)
            del self._sessions[validated_id]
            return session

    def evict_timed_out(
        self, *, now: float | None = None
    ) -> tuple[GatewaySession, ...]:
        """Remove expired attempts and return them in request-ID order."""

        timestamp = _monotonic_timestamp(now)
        with self._lock:
            expired_ids = sorted(
                request_id
                for request_id, session in self._sessions.items()
                if session.is_timed_out(now=timestamp)
            )
            return tuple(self._sessions.pop(request_id) for request_id in expired_ids)

    def snapshot(self) -> tuple[GatewaySession, ...]:
        """Return an immutable request-ID-ordered view of active sessions."""

        with self._lock:
            return tuple(
                self._sessions[request_id] for request_id in sorted(self._sessions)
            )

    def __contains__(self, request_id: object) -> bool:
        if not isinstance(request_id, str):
            return False
        try:
            validated_id = self._request_id(request_id)
        except GatewaySessionError:
            return False
        with self._lock:
            return validated_id in self._sessions

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)
