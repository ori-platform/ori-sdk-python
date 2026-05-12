# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Skill metadata validation helpers aligned with ori-runtime invariants."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

import yaml

from ori_sdk.errors import ORI_SDK_SKILL_VALIDATION, SkillMetadataValidationError

TRIGGER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
VALID_TIERS = {"A", "B", "C", "D"}
HISTORY_PLACEHOLDER_RE = re.compile(r"\{history\.[^{}]+\}")
MAX_HISTORY_PLACEHOLDERS = 16


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SkillMetadataValidationError(
            f"{field} must be a mapping", code=ORI_SDK_SKILL_VALIDATION
        )
    return value


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillMetadataValidationError(
            f"{field} must be a non-empty string", code=ORI_SDK_SKILL_VALIDATION
        )
    return value.strip()


def validate_skill_metadata_file(path: Path) -> Mapping[str, object]:
    """Load and validate a skill.yaml file."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillMetadataValidationError(
            f"failed to read {path}: {exc}", code=ORI_SDK_SKILL_VALIDATION
        ) from exc
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise SkillMetadataValidationError(
            f"invalid YAML in {path}: {exc}", code=ORI_SDK_SKILL_VALIDATION
        ) from exc
    validated = validate_skill_metadata(parsed)
    return validated


def validate_skill_metadata(skill: object) -> Mapping[str, object]:
    """Validate key pre-v1 runtime invariants for skill metadata."""
    root = _require_mapping(skill, "skill")
    _require_string(root.get("name"), "name")
    _require_string(root.get("version"), "version")
    _require_string(root.get("author"), "author")

    signature = root.get("signature")
    if signature is not None:
        signature_str = _require_string(signature, "signature")
        if signature_str != "bundled" and not signature_str.startswith("ed25519:"):
            raise SkillMetadataValidationError(
                "signature must be 'bundled' or start with 'ed25519:'",
                code=ORI_SDK_SKILL_VALIDATION,
            )

    raw_triggers = root.get("triggers")
    if not isinstance(raw_triggers, list) or not raw_triggers:
        raise SkillMetadataValidationError(
            "triggers must be a non-empty array", code=ORI_SDK_SKILL_VALIDATION
        )

    trigger_names: list[str] = []
    seen_names: set[str] = set()
    for item in raw_triggers:
        trigger = _require_mapping(item, "triggers[]")
        trigger_name = _require_string(trigger.get("name"), "triggers[].name")
        if not TRIGGER_NAME_RE.fullmatch(trigger_name):
            raise SkillMetadataValidationError(
                f"trigger {trigger_name!r} has invalid name format", code=ORI_SDK_SKILL_VALIDATION
            )
        if trigger_name in seen_names:
            raise SkillMetadataValidationError(
                f"duplicate trigger name {trigger_name!r}", code=ORI_SDK_SKILL_VALIDATION
            )
        seen_names.add(trigger_name)
        trigger_names.append(trigger_name)

        action_tier = _require_string(
            trigger.get("action_tier"), f"triggers[{trigger_name}].action_tier"
        )
        if action_tier not in VALID_TIERS:
            raise SkillMetadataValidationError(
                f"trigger {trigger_name!r} has invalid action_tier={action_tier!r}",
                code=ORI_SDK_SKILL_VALIDATION,
            )
        bypass_llm = bool(trigger.get("bypass_llm", False))
        if bypass_llm and action_tier != "D":
            raise SkillMetadataValidationError(
                f"trigger {trigger_name!r} sets bypass_llm=true for non-Tier-D action_tier",
                code=ORI_SDK_SKILL_VALIDATION,
            )
        if action_tier == "C":
            safe_default_action = str(
                trigger.get("safe_default_action", "log_to_dashboard")
            ).strip()
            if not safe_default_action:
                raise SkillMetadataValidationError(
                    f"trigger {trigger_name!r} is Tier C and requires safe_default_action",
                    code=ORI_SDK_SKILL_VALIDATION,
                )

    raw_actions = _require_mapping(root.get("actions"), "actions")
    defaults = _require_mapping(raw_actions.get("defaults"), "actions.defaults")
    available_list = raw_actions.get("available")
    if not isinstance(available_list, list) or not available_list:
        raise SkillMetadataValidationError(
            "actions.available must be a non-empty array", code=ORI_SDK_SKILL_VALIDATION
        )

    available_names: set[str] = set()
    for action in available_list:
        action_map = _require_mapping(action, "actions.available[]")
        action_name = _require_string(
            action_map.get("name"), "actions.available[].name"
        )
        available_names.add(action_name)

    default_keys = set(defaults.keys())
    missing = sorted(set(trigger_names) - default_keys)
    extra = sorted(default_keys - set(trigger_names))
    if missing:
        raise SkillMetadataValidationError(
            f"missing actions.defaults mapping for trigger(s): {', '.join(missing)}",
            code=ORI_SDK_SKILL_VALIDATION,
        )
    if extra:
        raise SkillMetadataValidationError(
            f"actions.defaults contains unknown trigger(s): {', '.join(extra)}",
            code=ORI_SDK_SKILL_VALIDATION,
        )

    for trigger_name in trigger_names:
        actions_for_trigger = defaults.get(trigger_name)
        if not isinstance(actions_for_trigger, list):
            raise SkillMetadataValidationError(
                f"actions.defaults.{trigger_name} must be an array", code=ORI_SDK_SKILL_VALIDATION
            )
        if not actions_for_trigger:
            raise SkillMetadataValidationError(
                f"actions.defaults.{trigger_name} must not be empty", code=ORI_SDK_SKILL_VALIDATION
            )
        for action_name in actions_for_trigger:
            if not isinstance(action_name, str) or not action_name.strip():
                raise SkillMetadataValidationError(
                    f"actions.defaults.{trigger_name} contains empty action name",
                    code=ORI_SDK_SKILL_VALIDATION,
                )
            if action_name not in available_names:
                raise SkillMetadataValidationError(
                    f"actions.defaults.{trigger_name} references undeclared action {action_name!r}",
                    code=ORI_SDK_SKILL_VALIDATION,
                )

    prompts_obj = root.get("prompts")
    if isinstance(prompts_obj, Mapping):
        trigger_names_set = set(trigger_names)
        for prompt_key, template in prompts_obj.items():
            if not isinstance(template, str):
                continue
            count = len(HISTORY_PLACEHOLDER_RE.findall(template))
            if count > MAX_HISTORY_PLACEHOLDERS:
                scope = "trigger" if prompt_key in trigger_names_set else "prompt key"
                raise SkillMetadataValidationError(
                    f"{scope} {prompt_key!r} contains {count} history placeholders; "
                    f"maximum allowed is {MAX_HISTORY_PLACEHOLDERS}",
                    code=ORI_SDK_SKILL_VALIDATION,
                )

    return root
