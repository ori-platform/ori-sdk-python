# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Backward-compatible skill metadata validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ori_sdk.errors import SkillMetadataValidationError
from ori_sdk.skill_package import MAX_HISTORY_PLACEHOLDERS, SkillYamlNormaliser


def validate_skill_metadata_file(path: Path) -> Mapping[str, object]:
    """Load and validate skill YAML or JSON, preserving the legacy return type."""
    return SkillYamlNormaliser.load_mapping_and_validate(path)


def validate_skill_metadata(skill: object) -> Mapping[str, object]:
    """Validate skill metadata against the skill package v1 contract."""
    return SkillYamlNormaliser.validate_mapping(skill)


__all__ = [
    "MAX_HISTORY_PLACEHOLDERS",
    "SkillMetadataValidationError",
    "validate_skill_metadata",
    "validate_skill_metadata_file",
]
