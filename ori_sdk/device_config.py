# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Typed deployment context for CLI and Gateway consumers.

This module defines the physical capabilities and hardware constraints of the four
supported deployment types (phone, Raspberry Pi, dedicated edge node, and server).
It does not load configuration or enforce runtime policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from ori_sdk.errors import (
    ORI_SDK_DEPLOYMENT_DATA_UNAVAILABLE,
    ORI_SDK_UNKNOWN_DEPLOYMENT_TYPE,
    DeviceConfigError,
)
from ori_sdk.models import HealthStatus
from ori_sdk.skill_package import ActionTier


class DeploymentType(Enum):
    """Runtime deployment classes."""

    PI = "pi"
    PHONE = "phone"
    EDGE_NODE = "edge_node"
    SERVER = "server"

    @classmethod
    def from_value(cls, raw: str) -> DeploymentType:
        """Parse a runtime ``device.deployment_type`` string, case-sensitive."""
        for member in cls:
            if member.value == raw:
                return member
        raise DeviceConfigError(
            f"unknown deployment_type {raw!r}",
            code=ORI_SDK_UNKNOWN_DEPLOYMENT_TYPE,
        )


@dataclass(frozen=True, slots=True)
class DeploymentConstraints:
    """Static deployment characteristics defined by the runtime contract."""

    deployment_type: DeploymentType
    physical_actuation_support: Literal["unsupported", "conditional"]
    potential_max_action_tier: ActionTier | None
    description: str


_CONSTRAINTS: dict[DeploymentType, DeploymentConstraints] = {
    DeploymentType.PHONE: DeploymentConstraints(
        deployment_type=DeploymentType.PHONE,
        physical_actuation_support="unsupported",
        potential_max_action_tier="B",
        description=(
            "Android runtime-mobile deployment. No GPIO or relay hardware path; "
            "it must not advertise Tier C or Tier D physical actuation."
        ),
    ),
    DeploymentType.PI: DeploymentConstraints(
        deployment_type=DeploymentType.PI,
        physical_actuation_support="conditional",
        potential_max_action_tier="D",
        description=(
            "Raspberry Pi deployment. GPIO and relay support depend on runtime "
            "configuration and health/capability posture."
        ),
    ),
    DeploymentType.EDGE_NODE: DeploymentConstraints(
        deployment_type=DeploymentType.EDGE_NODE,
        physical_actuation_support="conditional",
        potential_max_action_tier="D",
        description=(
            "Dedicated Ori edge-node deployment. Physical actuation support "
            "depends on runtime configuration and health posture."
        ),
    ),
    DeploymentType.SERVER: DeploymentConstraints(
        deployment_type=DeploymentType.SERVER,
        physical_actuation_support="unsupported",
        potential_max_action_tier=None,
        description=(
            "Server deployment. No implied GPIO or relay hardware path. "
            "The contract does not define an overall action-tier ceiling for "
            "this deployment class."
        ),
    ),
}


def deployment_constraints(deployment_type: DeploymentType) -> DeploymentConstraints:
    """Return the static characteristics for a deployment class."""
    return _CONSTRAINTS[deployment_type]


@dataclass(frozen=True, slots=True)
class DeviceConfig:
    """Typed deployment context for a single device."""

    deployment_type: DeploymentType
    device_id: str | None = None

    def __post_init__(self) -> None:
        """Reject a non-DeploymentType value."""
        if not isinstance(self.deployment_type, DeploymentType):
            raise DeviceConfigError(
                f"deployment_type must be a DeploymentType, got {self.deployment_type!r}",
                code=ORI_SDK_UNKNOWN_DEPLOYMENT_TYPE,
            )

    @property
    def constraints(self) -> DeploymentConstraints:
        return deployment_constraints(self.deployment_type)

    @classmethod
    def from_health_status(cls, status: HealthStatus) -> DeviceConfig:
        """Always fail: HealthStatus carries no deployment_type."""
        raise DeviceConfigError(
            f"HealthStatus for device_id={status.device_id!r} has no deployment_type",
            code=ORI_SDK_DEPLOYMENT_DATA_UNAVAILABLE,
        )


__all__ = [
    "DeploymentConstraints",
    "DeploymentType",
    "DeviceConfig",
    "deployment_constraints",
]
