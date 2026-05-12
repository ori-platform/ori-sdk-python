# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Typed error hierarchy for ori-sdk-python.

All public exceptions inherit from OriSDKError and carry an ORI-SDK-* code
registered below.  Never raise bare exceptions across module boundaries.
"""

from __future__ import annotations

# ── Health client error codes (ORI-SDK-0xx) ───────────────────────────────────
ORI_SDK_SOCKET_NOT_FOUND = "ORI-SDK-001"
ORI_SDK_CONNECTION_REFUSED = "ORI-SDK-002"
ORI_SDK_TIMEOUT = "ORI-SDK-003"
ORI_SDK_RESPONSE_TOO_LARGE = "ORI-SDK-004"
ORI_SDK_INVALID_JSON = "ORI-SDK-005"
ORI_SDK_SCHEMA_MISMATCH = "ORI-SDK-006"
ORI_SDK_EMPTY_RESPONSE = "ORI-SDK-007"

# ── Skill validation error codes (ORI-SDK-01x) ────────────────────────────────
ORI_SDK_SKILL_VALIDATION = "ORI-SDK-010"

# ── Gateway contract error codes (ORI-SDK-02x) ────────────────────────────────
ORI_SDK_REQUEST_ID_MISMATCH = "ORI-SDK-020"


class OriSDKError(Exception):
    """Base class for all ori-sdk-python errors.

    Every subclass must pass a registered *code* so callers can branch on
    error type without string-matching the human-readable *details*.
    """

    def __init__(self, details: str, *, code: str) -> None:
        super().__init__(details)
        self.code = code
        self.details = details

    def __str__(self) -> str:
        return f"[{self.code}] {self.details}"


class HealthClientError(OriSDKError):
    """Raised by RuntimeHealthClient when the health socket call fails."""


class SkillMetadataValidationError(OriSDKError):
    """Raised when skill metadata fails pre-v1 runtime invariant checks."""


class GatewayContractError(OriSDKError):
    """Raised when a gateway response violates the request/response contract."""
