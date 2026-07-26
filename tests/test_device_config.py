# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from ori_sdk import (
    DeploymentConstraints,
    DeploymentType,
    DeviceConfig,
    deployment_constraints,
)
from ori_sdk.errors import (
    ORI_SDK_DEPLOYMENT_DATA_UNAVAILABLE,
    ORI_SDK_UNKNOWN_DEPLOYMENT_TYPE,
    DeviceConfigError,
)
from ori_sdk.models import HealthResponse

FIXTURES = Path(__file__).parent / "fixtures"


def test_device_config_api_is_publicly_exported() -> None:
    assert DeploymentType.PHONE.value == "phone"
    assert DeviceConfig is not None
    assert deployment_constraints is not None


def test_deployment_type_from_value_accepts_pi() -> None:
    assert DeploymentType.from_value("pi") is DeploymentType.PI


def test_deployment_type_from_value_accepts_phone() -> None:
    assert DeploymentType.from_value("phone") is DeploymentType.PHONE


def test_deployment_type_from_value_accepts_edge_node() -> None:
    assert DeploymentType.from_value("edge_node") is DeploymentType.EDGE_NODE


def test_deployment_type_from_value_accepts_server() -> None:
    assert DeploymentType.from_value("server") is DeploymentType.SERVER


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "PHONE",
        "Phone",
        "phone ",
        " phone",
        "pi ",
        "edge-node",
        "edge node",
        "laptop",
    ],
)
def test_deployment_type_from_value_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(DeviceConfigError) as exc:
        DeploymentType.from_value(raw)

    assert exc.value.code == ORI_SDK_UNKNOWN_DEPLOYMENT_TYPE
    assert raw in exc.value.details


def test_every_deployment_type_has_constraints() -> None:
    for deployment_type in DeploymentType:
        constraints = deployment_constraints(deployment_type)

        assert isinstance(constraints, DeploymentConstraints)
        assert constraints.deployment_type is deployment_type


def test_deployment_constraints_return_canonical_object() -> None:
    first = deployment_constraints(DeploymentType.PI)
    second = deployment_constraints(DeploymentType.PI)

    assert first is second


def test_phone_constraints_match_contract() -> None:
    constraints = deployment_constraints(DeploymentType.PHONE)

    assert constraints.deployment_type is DeploymentType.PHONE
    assert constraints.supports_physical_actuation is False
    assert constraints.max_action_tier == "B"
    assert constraints.description


def test_server_constraints_match_contract() -> None:
    constraints = deployment_constraints(DeploymentType.SERVER)

    assert constraints.deployment_type is DeploymentType.SERVER
    assert constraints.supports_physical_actuation is False
    assert constraints.max_action_tier == "B"
    assert constraints.description


def test_pi_constraints_match_contract() -> None:
    constraints = deployment_constraints(DeploymentType.PI)

    assert constraints.deployment_type is DeploymentType.PI
    assert constraints.supports_physical_actuation is True
    assert constraints.max_action_tier == "D"
    assert constraints.description


def test_edge_node_constraints_match_contract() -> None:
    constraints = deployment_constraints(DeploymentType.EDGE_NODE)

    assert constraints.deployment_type is DeploymentType.EDGE_NODE
    assert constraints.supports_physical_actuation is True
    assert constraints.max_action_tier == "D"
    assert constraints.description


def test_deployment_constraints_are_immutable() -> None:
    constraints = deployment_constraints(DeploymentType.PI)

    with pytest.raises(FrozenInstanceError):
        constraints.max_action_tier = "B"


def test_device_config_accepts_valid_deployment_type() -> None:
    config = DeviceConfig(
        DeploymentType.PI,
        device_id="site-a-edge-01",
    )

    assert config.deployment_type is DeploymentType.PI
    assert config.device_id == "site-a-edge-01"


def test_device_config_exposes_constraints() -> None:
    config = DeviceConfig(DeploymentType.PHONE)

    assert config.constraints is deployment_constraints(DeploymentType.PHONE)


def test_device_config_is_immutable() -> None:
    config = DeviceConfig(DeploymentType.PI)

    with pytest.raises(FrozenInstanceError):
        config.device_id = "different-device"


@pytest.mark.parametrize(
    "invalid_value",
    [
        "pi",
        None,
        1,
        {},
        [],
        object(),
    ],
)
def test_device_config_rejects_non_deployment_type_values(
    invalid_value: object,
) -> None:
    with pytest.raises(DeviceConfigError) as exc:
        DeviceConfig(cast(DeploymentType, invalid_value))

    assert exc.value.code == ORI_SDK_UNKNOWN_DEPLOYMENT_TYPE
    assert "must be a DeploymentType" in exc.value.details


def test_health_status_without_deployment_type_fails() -> None:
    payload = json.loads((FIXTURES / "runtime_health_success.json").read_text())
    response = HealthResponse.from_dict(payload)

    assert response.health is not None

    with pytest.raises(DeviceConfigError) as exc:
        DeviceConfig.from_health_status(response.health)

    assert exc.value.code == ORI_SDK_DEPLOYMENT_DATA_UNAVAILABLE
    assert response.health.device_id in exc.value.details
