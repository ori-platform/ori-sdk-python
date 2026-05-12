# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from ori_sdk.errors import (
    ORI_SDK_CONNECTION_REFUSED,
    ORI_SDK_REQUEST_ID_MISMATCH,
    ORI_SDK_SKILL_VALIDATION,
    ORI_SDK_SOCKET_NOT_FOUND,
    GatewayContractError,
    HealthClientError,
    OriSDKError,
    SkillMetadataValidationError,
)


def test_ori_sdk_error_carries_code_and_details() -> None:
    exc = OriSDKError("something went wrong", code="ORI-SDK-999")
    assert exc.code == "ORI-SDK-999"
    assert exc.details == "something went wrong"
    assert "ORI-SDK-999" in str(exc)
    assert "something went wrong" in str(exc)


def test_health_client_error_is_ori_sdk_error() -> None:
    exc = HealthClientError("socket not found", code=ORI_SDK_SOCKET_NOT_FOUND)
    assert isinstance(exc, OriSDKError)
    assert exc.code == ORI_SDK_SOCKET_NOT_FOUND
    assert exc.details == "socket not found"


def test_health_client_error_connection_refused_code() -> None:
    exc = HealthClientError("connection refused", code=ORI_SDK_CONNECTION_REFUSED)
    assert exc.code == ORI_SDK_CONNECTION_REFUSED


def test_skill_metadata_validation_error_is_ori_sdk_error() -> None:
    exc = SkillMetadataValidationError("name is required", code=ORI_SDK_SKILL_VALIDATION)
    assert isinstance(exc, OriSDKError)
    assert exc.code == ORI_SDK_SKILL_VALIDATION


def test_gateway_contract_error_is_ori_sdk_error() -> None:
    exc = GatewayContractError("request_id mismatch", code=ORI_SDK_REQUEST_ID_MISMATCH)
    assert isinstance(exc, OriSDKError)
    assert exc.code == ORI_SDK_REQUEST_ID_MISMATCH


def test_errors_are_catchable_as_exception() -> None:
    with pytest.raises(Exception):
        raise HealthClientError("test", code=ORI_SDK_SOCKET_NOT_FOUND)


def test_errors_are_catchable_as_ori_sdk_error() -> None:
    with pytest.raises(OriSDKError):
        raise SkillMetadataValidationError("bad skill", code=ORI_SDK_SKILL_VALIDATION)
