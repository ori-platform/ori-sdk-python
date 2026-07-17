# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Typed, immutable models for the Ori skill package v1 contract."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping, cast

import yaml

from ori_sdk.errors import ORI_SDK_SKILL_VALIDATION, SkillMetadataValidationError

ActionTier = Literal["A", "B", "C", "D"]
EscalationTier = Literal["rule", "local_slm", "gateway"]
ReasoningPolicy = Literal["post_action"]

TRIGGER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
VALID_TIERS = frozenset({"A", "B", "C", "D"})
VALID_ESCALATION_TIERS = frozenset({"rule", "local_slm", "gateway"})
HISTORY_PLACEHOLDER_RE = re.compile(r"\{history\.[^{}]+\}")
MAX_HISTORY_PLACEHOLDERS = 16


def _validation_error(details: str) -> SkillMetadataValidationError:
    return SkillMetadataValidationError(details, code=ORI_SDK_SKILL_VALIDATION)


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _validation_error(f"{field} must be a mapping")
    for key in value:
        if not isinstance(key, str):
            raise _validation_error(f"{field} keys must be strings")
    return cast(Mapping[str, object], value)


def _require_array(
    value: object, field: str, *, non_empty: bool = False
) -> list[object]:
    if not isinstance(value, list) or (non_empty and not value):
        qualifier = "a non-empty" if non_empty else "an"
        raise _validation_error(f"{field} must be {qualifier} array")
    return cast(list[object], value)


def _require_string(
    value: object,
    field: str,
    *,
    non_empty: bool = True,
    preserve: bool = False,
) -> str:
    if not isinstance(value, str):
        raise _validation_error(f"{field} must be a string")
    normalised = value.strip()
    if non_empty and not normalised:
        raise _validation_error(f"{field} must be a non-empty string")
    return value if preserve else normalised


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise _validation_error(f"{field} must be a boolean")
    return value


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _validation_error(f"{field} must be an integer")
    return value


def _normalise_trigger_name(
    value: object, field: str, *, preserve: bool = False
) -> str:
    name = _require_string(value, field, preserve=preserve)
    if not TRIGGER_NAME_RE.fullmatch(name):
        raise _validation_error(f"trigger {name!r} has invalid name format")
    return name


def _normalise_action_tier(
    value: object, field: str, subject: str, *, label: str = "tier"
) -> ActionTier:
    tier = _require_string(value, field)
    if tier not in VALID_TIERS:
        raise _validation_error(f"{subject} has invalid {label}={tier!r}")
    return cast(ActionTier, tier)


def _normalise_escalation_tier(value: object, trigger_name: str) -> EscalationTier:
    escalation = _require_string(value, f"triggers[{trigger_name}].escalate_to")
    if escalation not in VALID_ESCALATION_TIERS:
        raise _validation_error(
            f"trigger {trigger_name!r} has invalid escalate_to={escalation!r}; "
            "expected rule, local_slm, or gateway"
        )
    return cast(EscalationTier, escalation)


def _normalise_signature(value: object) -> str | None:
    if value is None:
        return None
    signature = _require_string(value, "signature")
    if signature != "bundled" and not signature.startswith("ed25519:"):
        raise _validation_error("signature must be 'bundled' or start with 'ed25519:'")
    return signature


def _freeze_value(
    value: object,
    field: str,
    active_container_ids: set[int] | None = None,
) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _validation_error(f"{field} must contain only finite numbers")
        return value
    if not isinstance(value, (Mapping, list, tuple)):
        raise _validation_error(f"{field} must contain only JSON-compatible values")

    active_ids = active_container_ids if active_container_ids is not None else set()
    container_id = id(value)
    if container_id in active_ids:
        raise _validation_error(f"{field} contains a cyclic reference")
    active_ids.add(container_id)
    try:
        if isinstance(value, Mapping):
            mapping = _require_mapping(value, field)
            return MappingProxyType(
                {
                    key: _freeze_value(item, f"{field}.{key}", active_ids)
                    for key, item in mapping.items()
                }
            )
        sequence = cast(list[object] | tuple[object, ...], value)
        return tuple(_freeze_value(item, f"{field}[]", active_ids) for item in sequence)
    finally:
        active_ids.remove(container_id)


def _thaw_value(
    value: object,
    field: str,
    active_container_ids: set[int] | None = None,
) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _validation_error(f"{field} must contain only finite numbers")
        return value
    if not isinstance(value, (Mapping, list, tuple)):
        raise _validation_error(f"{field} must contain only JSON-compatible values")

    active_ids = active_container_ids if active_container_ids is not None else set()
    container_id = id(value)
    if container_id in active_ids:
        raise _validation_error(f"{field} contains a cyclic reference")
    active_ids.add(container_id)
    try:
        if isinstance(value, Mapping):
            mapping = _require_mapping(value, field)
            return {
                key: _thaw_value(item, f"{field}.{key}", active_ids)
                for key, item in mapping.items()
            }
        sequence = cast(list[object] | tuple[object, ...], value)
        return [_thaw_value(item, f"{field}[]", active_ids) for item in sequence]
    finally:
        active_ids.remove(container_id)


@dataclass(frozen=True, slots=True)
class SensorRequirement:
    """A sensor capability required by a skill package."""

    type: str
    protocol: str | None = None

    def __post_init__(self) -> None:
        """Validate and canonicalise a directly constructed requirement."""
        sensor_type = _require_string(self.type, "sensor.type")
        protocol = (
            None
            if self.protocol is None
            else _require_string(self.protocol, "sensor.protocol")
        )
        object.__setattr__(self, "type", sensor_type)
        object.__setattr__(self, "protocol", protocol)

    def to_dict(self) -> dict[str, object]:
        """Return the normalised transport representation."""
        result: dict[str, object] = {"type": self.type}
        if self.protocol is not None:
            result["protocol"] = self.protocol
        return result


@dataclass(frozen=True, slots=True)
class Trigger:
    """A normalised skill trigger and its actuation policy."""

    name: str
    condition: str
    action_tier: ActionTier
    cooldown_seconds: int
    escalate_to: EscalationTier
    bypass_llm: bool
    reasoning_policy: ReasoningPolicy | None
    requires_approval: bool
    approval_timeout_seconds: int
    safe_default_action: str

    def __post_init__(self) -> None:
        """Enforce trigger policy for direct and normaliser construction."""
        name = _normalise_trigger_name(self.name, "trigger.name")
        action_tier = _normalise_action_tier(
            self.action_tier,
            f"triggers[{name}].action_tier",
            f"trigger {name!r}",
            label="action_tier",
        )
        condition = _require_string(
            self.condition,
            f"triggers[{name}].condition",
            non_empty=False,
            preserve=True,
        )
        cooldown_seconds = _require_int(
            self.cooldown_seconds, f"triggers[{name}].cooldown_seconds"
        )
        escalate_to = _normalise_escalation_tier(self.escalate_to, name)
        bypass_llm = _require_bool(self.bypass_llm, f"triggers[{name}].bypass_llm")
        if bypass_llm and action_tier != "D":
            raise _validation_error(
                f"trigger {name!r} sets bypass_llm=true for non-Tier-D action_tier"
            )
        if action_tier == "D":
            if escalate_to != "rule":
                raise _validation_error(
                    f"Tier D trigger {name!r} must use escalate_to='rule'"
                )
            bypass_llm = True

        reasoning_policy: ReasoningPolicy | None = None
        if self.reasoning_policy is not None:
            parsed_policy = _require_string(
                self.reasoning_policy, f"triggers[{name}].reasoning_policy"
            )
            if parsed_policy != "post_action":
                raise _validation_error(
                    f"trigger {name!r} has invalid reasoning_policy={parsed_policy!r}"
                )
            if action_tier != "B":
                raise _validation_error(
                    f"trigger {name!r} uses reasoning_policy=post_action outside Tier B"
                )
            reasoning_policy = "post_action"

        requires_approval = _require_bool(
            self.requires_approval, f"triggers[{name}].requires_approval"
        )
        approval_timeout_seconds = _require_int(
            self.approval_timeout_seconds,
            f"triggers[{name}].approval_timeout_seconds",
        )
        safe_default_action = _require_string(
            self.safe_default_action,
            f"triggers[{name}].safe_default_action",
            non_empty=False,
        )
        if action_tier == "C" and not safe_default_action:
            raise _validation_error(
                f"trigger {name!r} is Tier C and requires safe_default_action"
            )

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "condition", condition)
        object.__setattr__(self, "action_tier", action_tier)
        object.__setattr__(self, "cooldown_seconds", cooldown_seconds)
        object.__setattr__(self, "escalate_to", escalate_to)
        object.__setattr__(self, "bypass_llm", bypass_llm)
        object.__setattr__(self, "reasoning_policy", reasoning_policy)
        object.__setattr__(self, "requires_approval", requires_approval)
        object.__setattr__(self, "approval_timeout_seconds", approval_timeout_seconds)
        object.__setattr__(self, "safe_default_action", safe_default_action)

    def to_dict(self) -> dict[str, object]:
        """Return the normalised transport representation."""
        result: dict[str, object] = {
            "name": self.name,
            "condition": self.condition,
            "action_tier": self.action_tier,
            "cooldown_seconds": self.cooldown_seconds,
            "escalate_to": self.escalate_to,
            "bypass_llm": self.bypass_llm,
        }
        if self.reasoning_policy is not None:
            result["reasoning_policy"] = self.reasoning_policy
        result.update(
            {
                "requires_approval": self.requires_approval,
                "approval_timeout_seconds": self.approval_timeout_seconds,
                "safe_default_action": self.safe_default_action,
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class ActionRef:
    """A declared action and its maximum authority tier."""

    name: str
    tier: ActionTier

    def __post_init__(self) -> None:
        """Validate and canonicalise a directly constructed action reference."""
        name = _require_string(self.name, "action.name")
        tier = _normalise_action_tier(self.tier, "action.tier", f"action {name!r}")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "tier", tier)

    def to_dict(self) -> dict[str, object]:
        """Return the normalised transport representation."""
        return {"name": self.name, "tier": self.tier}


@dataclass(frozen=True, slots=True)
class ActionsSection:
    """Declared actions and trigger-to-action defaults."""

    available: tuple[ActionRef, ...]
    defaults: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        """Validate action declarations and defensively freeze collections."""
        if not isinstance(self.available, (list, tuple)) or not self.available:
            raise _validation_error("actions.available must be a non-empty array")

        available: list[ActionRef] = []
        available_names: set[str] = set()
        for index, action in enumerate(self.available):
            if not isinstance(action, ActionRef):
                raise _validation_error(
                    f"actions.available[{index}] must be an ActionRef"
                )
            if action.name in available_names:
                raise _validation_error(f"duplicate action name {action.name!r}")
            available_names.add(action.name)
            available.append(action)

        defaults = _require_mapping(self.defaults, "actions.defaults")
        frozen_defaults: dict[str, tuple[str, ...]] = {}
        for raw_trigger_name, raw_action_names in defaults.items():
            trigger_name = _normalise_trigger_name(
                raw_trigger_name, "actions.defaults key", preserve=True
            )
            if not isinstance(raw_action_names, (list, tuple)) or not raw_action_names:
                raise _validation_error(
                    f"actions.defaults.{trigger_name} must be a non-empty array"
                )
            action_names: list[str] = []
            for raw_action_name in raw_action_names:
                action_name = _require_string(
                    raw_action_name, f"actions.defaults.{trigger_name}[]"
                )
                if action_name not in available_names:
                    raise _validation_error(
                        f"actions.defaults.{trigger_name} references undeclared "
                        f"action {action_name!r}"
                    )
                action_names.append(action_name)
            frozen_defaults[trigger_name] = tuple(action_names)

        object.__setattr__(self, "available", tuple(available))
        object.__setattr__(self, "defaults", MappingProxyType(frozen_defaults))

    def to_dict(self) -> dict[str, object]:
        """Return the normalised transport representation."""
        return {
            "available": [action.to_dict() for action in self.available],
            "defaults": {
                trigger_name: list(action_names)
                for trigger_name, action_names in self.defaults.items()
            },
        }


def _validate_trigger_action_contract(
    triggers: tuple[Trigger, ...], actions: ActionsSection
) -> None:
    trigger_names = {trigger.name for trigger in triggers}
    default_keys = set(actions.defaults)
    missing = sorted(trigger_names - default_keys)
    extra = sorted(default_keys - trigger_names)
    if missing:
        raise _validation_error(
            f"missing actions.defaults mapping for trigger(s): {', '.join(missing)}"
        )
    if extra:
        raise _validation_error(
            f"actions.defaults contains unknown trigger(s): {', '.join(extra)}"
        )

    action_tiers = {action.name: action.tier for action in actions.available}
    for trigger in triggers:
        default_actions = actions.defaults[trigger.name]
        has_physical_action = any(
            action_tiers[action_name] == "B" for action_name in default_actions
        )
        if trigger.action_tier != "B" or not has_physical_action:
            continue
        if not trigger.requires_approval and trigger.reasoning_policy != "post_action":
            raise _validation_error(
                f"physical Tier B trigger {trigger.name!r} must declare "
                "requires_approval=true or reasoning_policy=post_action"
            )
        if trigger.reasoning_policy == "post_action" and not any(
            action_tiers[action_name] == "A" for action_name in default_actions
        ):
            raise _validation_error(
                f"physical Tier B post_action trigger {trigger.name!r} must "
                "include a Tier A default action for operator notification"
            )


@dataclass(frozen=True, slots=True)
class SkillPackage:
    """A validated Ori skill package independent of the runtime implementation."""

    name: str
    version: str
    author: str
    signature: str | None
    sensors_required: tuple[SensorRequirement, ...]
    triggers: tuple[Trigger, ...]
    prompts: Mapping[str, str]
    actions: ActionsSection
    config: Mapping[str, object]

    def __post_init__(self) -> None:
        """Validate the complete package and defensively freeze collections."""
        name = _require_string(self.name, "name")
        version = _require_string(self.version, "version")
        author = _require_string(self.author, "author")
        signature = _normalise_signature(self.signature)

        if not isinstance(self.sensors_required, (list, tuple)):
            raise _validation_error("sensors_required must be an array")
        sensors_required = tuple(self.sensors_required)
        for index, sensor in enumerate(sensors_required):
            if not isinstance(sensor, SensorRequirement):
                raise _validation_error(
                    f"sensors_required[{index}] must be a SensorRequirement"
                )

        if not isinstance(self.triggers, (list, tuple)) or not self.triggers:
            raise _validation_error("triggers must be a non-empty array")
        triggers = tuple(self.triggers)
        seen_trigger_names: set[str] = set()
        for index, trigger in enumerate(triggers):
            if not isinstance(trigger, Trigger):
                raise _validation_error(f"triggers[{index}] must be a Trigger")
            if trigger.name in seen_trigger_names:
                raise _validation_error(f"duplicate trigger name {trigger.name!r}")
            seen_trigger_names.add(trigger.name)

        prompts = _require_mapping(self.prompts, "prompts")
        frozen_prompts: dict[str, str] = {}
        for prompt_key, template in prompts.items():
            parsed_template = _require_string(
                template,
                f"prompts.{prompt_key}",
                non_empty=False,
                preserve=True,
            )
            count = len(HISTORY_PLACEHOLDER_RE.findall(parsed_template))
            if count > MAX_HISTORY_PLACEHOLDERS:
                scope = "trigger" if prompt_key in seen_trigger_names else "prompt key"
                raise _validation_error(
                    f"{scope} {prompt_key!r} contains {count} history placeholders; "
                    f"maximum allowed is {MAX_HISTORY_PLACEHOLDERS}"
                )
            frozen_prompts[prompt_key] = parsed_template

        if not isinstance(self.actions, ActionsSection):
            raise _validation_error("actions must be an ActionsSection")
        _validate_trigger_action_contract(triggers, self.actions)

        config = _require_mapping(self.config, "config")
        frozen_config = cast(Mapping[str, object], _freeze_value(config, "config"))

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "author", author)
        object.__setattr__(self, "signature", signature)
        object.__setattr__(self, "sensors_required", sensors_required)
        object.__setattr__(self, "triggers", triggers)
        object.__setattr__(self, "prompts", MappingProxyType(frozen_prompts))
        object.__setattr__(self, "config", frozen_config)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON/YAML-serialisable normalised representation."""
        result: dict[str, object] = {
            "name": self.name,
            "version": self.version,
            "author": self.author,
        }
        if self.signature is not None:
            result["signature"] = self.signature
        result.update(
            {
                "sensors_required": [
                    sensor.to_dict() for sensor in self.sensors_required
                ],
                "triggers": [trigger.to_dict() for trigger in self.triggers],
                "prompts": dict(self.prompts),
                "actions": self.actions.to_dict(),
                "config": _thaw_value(self.config, "config"),
            }
        )
        return result


class SkillYamlNormaliser:
    """Load skill YAML or JSON and enforce the current skill package v1 contract."""

    @classmethod
    def load_and_validate(cls, path: Path) -> SkillPackage:
        """Load *path* and return a validated, immutable skill package."""
        return cls.normalise(cls._load_document(path))

    @classmethod
    def load_mapping_and_validate(cls, path: Path) -> Mapping[str, object]:
        """Load *path* while preserving the legacy validated mapping result."""
        return cls.validate_mapping(cls._load_document(path))

    @staticmethod
    def _load_document(path: Path) -> object:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise _validation_error(f"failed to read {path}: {exc}") from exc
        try:
            parsed: object = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise _validation_error(f"invalid YAML in {path}: {exc}") from exc
        return parsed

    @classmethod
    def normalise(cls, skill: object) -> SkillPackage:
        """Validate an already-decoded mapping and return its typed package."""
        package, _ = cls._normalise_with_root(skill)
        return package

    @classmethod
    def validate_mapping(cls, skill: object) -> Mapping[str, object]:
        """Validate a mapping while preserving the legacy mapping return contract."""
        _, root = cls._normalise_with_root(skill)
        return root

    @classmethod
    def _normalise_with_root(
        cls, skill: object
    ) -> tuple[SkillPackage, Mapping[str, object]]:
        root = _require_mapping(skill, "skill")
        name = _require_string(root.get("name"), "name")
        version = _require_string(root.get("version"), "version")
        author = _require_string(root.get("author"), "author")
        signature = cls._parse_signature(root.get("signature"))
        sensors = cls._parse_sensors(root.get("sensors_required", []))
        triggers = cls._parse_triggers(root.get("triggers"))
        actions = cls._parse_actions(root.get("actions"), triggers)
        prompts = cls._parse_prompts(root.get("prompts", {}), triggers)
        config = _require_mapping(root.get("config", {}), "config")

        return (
            SkillPackage(
                name=name,
                version=version,
                author=author,
                signature=signature,
                sensors_required=sensors,
                triggers=triggers,
                prompts=prompts,
                actions=actions,
                config=config,
            ),
            root,
        )

    @staticmethod
    def _parse_signature(value: object) -> str | None:
        return _normalise_signature(value)

    @staticmethod
    def _parse_sensors(value: object) -> tuple[SensorRequirement, ...]:
        sensors: list[SensorRequirement] = []
        for index, item in enumerate(_require_array(value, "sensors_required")):
            field = f"sensors_required[{index}]"
            sensor = _require_mapping(item, field)
            sensor_type = _require_string(sensor.get("type"), f"{field}.type")
            protocol_value = sensor.get("protocol")
            protocol = (
                None
                if protocol_value is None
                else _require_string(protocol_value, f"{field}.protocol")
            )
            sensors.append(SensorRequirement(type=sensor_type, protocol=protocol))
        return tuple(sensors)

    @staticmethod
    def _parse_triggers(value: object) -> tuple[Trigger, ...]:
        raw_triggers = _require_array(value, "triggers", non_empty=True)
        triggers: list[Trigger] = []
        seen_names: set[str] = set()
        for index, item in enumerate(raw_triggers):
            field = f"triggers[{index}]"
            trigger = _require_mapping(item, field)
            trigger_name = _normalise_trigger_name(trigger.get("name"), f"{field}.name")
            if trigger_name in seen_names:
                raise _validation_error(f"duplicate trigger name {trigger_name!r}")
            seen_names.add(trigger_name)

            action_tier = _normalise_action_tier(
                trigger.get("action_tier"),
                f"triggers[{trigger_name}].action_tier",
                f"trigger {trigger_name!r}",
                label="action_tier",
            )

            bypass_llm = _require_bool(
                trigger.get("bypass_llm", False),
                f"triggers[{trigger_name}].bypass_llm",
            )
            if bypass_llm and action_tier != "D":
                raise _validation_error(
                    f"trigger {trigger_name!r} sets bypass_llm=true for "
                    "non-Tier-D action_tier"
                )
            if action_tier == "D":
                bypass_llm = True

            escalation_default = "rule" if action_tier == "D" else "local_slm"
            escalation_value = _normalise_escalation_tier(
                trigger.get("escalate_to", escalation_default), trigger_name
            )
            if action_tier == "D" and escalation_value != "rule":
                raise _validation_error(
                    f"Tier D trigger {trigger_name!r} must use escalate_to='rule'"
                )

            reasoning_value = trigger.get("reasoning_policy")
            reasoning_policy: ReasoningPolicy | None = None
            if reasoning_value is not None:
                parsed_policy = _require_string(
                    reasoning_value, f"triggers[{trigger_name}].reasoning_policy"
                )
                if parsed_policy != "post_action":
                    raise _validation_error(
                        f"trigger {trigger_name!r} has invalid "
                        f"reasoning_policy={parsed_policy!r}"
                    )
                if action_tier != "B":
                    raise _validation_error(
                        f"trigger {trigger_name!r} uses reasoning_policy=post_action "
                        "outside Tier B"
                    )
                reasoning_policy = "post_action"

            safe_default = _require_string(
                trigger.get("safe_default_action", "log_to_dashboard"),
                f"triggers[{trigger_name}].safe_default_action",
                non_empty=False,
            )
            if action_tier == "C" and not safe_default:
                raise _validation_error(
                    f"trigger {trigger_name!r} is Tier C and requires "
                    "safe_default_action"
                )

            triggers.append(
                Trigger(
                    name=trigger_name,
                    condition=_require_string(
                        trigger.get("condition", ""),
                        f"triggers[{trigger_name}].condition",
                        non_empty=False,
                        preserve=True,
                    ),
                    action_tier=action_tier,
                    cooldown_seconds=_require_int(
                        trigger.get("cooldown_seconds", 0),
                        f"triggers[{trigger_name}].cooldown_seconds",
                    ),
                    escalate_to=escalation_value,
                    bypass_llm=bypass_llm,
                    reasoning_policy=reasoning_policy,
                    requires_approval=_require_bool(
                        trigger.get("requires_approval", False),
                        f"triggers[{trigger_name}].requires_approval",
                    ),
                    approval_timeout_seconds=_require_int(
                        trigger.get("approval_timeout_seconds", 300),
                        f"triggers[{trigger_name}].approval_timeout_seconds",
                    ),
                    safe_default_action=safe_default,
                )
            )
        return tuple(triggers)

    @staticmethod
    def _parse_actions(value: object, triggers: tuple[Trigger, ...]) -> ActionsSection:
        raw_actions = _require_mapping(value, "actions")
        raw_available = _require_array(
            raw_actions.get("available"), "actions.available", non_empty=True
        )
        available: list[ActionRef] = []
        available_names: set[str] = set()
        for index, item in enumerate(raw_available):
            field = f"actions.available[{index}]"
            action = _require_mapping(item, field)
            action_name = _require_string(action.get("name"), f"{field}.name")
            if action_name in available_names:
                raise _validation_error(f"duplicate action name {action_name!r}")
            available_names.add(action_name)
            available.append(
                ActionRef(
                    name=action_name,
                    tier=_normalise_action_tier(
                        action.get("tier"), f"{field}.tier", f"action {action_name!r}"
                    ),
                )
            )

        raw_defaults = _require_mapping(raw_actions.get("defaults"), "actions.defaults")
        trigger_names = {trigger.name for trigger in triggers}
        default_keys = set(raw_defaults)
        missing = sorted(trigger_names - default_keys)
        extra = sorted(default_keys - trigger_names)
        if missing:
            raise _validation_error(
                f"missing actions.defaults mapping for trigger(s): {', '.join(missing)}"
            )
        if extra:
            raise _validation_error(
                f"actions.defaults contains unknown trigger(s): {', '.join(extra)}"
            )

        defaults: dict[str, tuple[str, ...]] = {}
        for trigger in triggers:
            field = f"actions.defaults.{trigger.name}"
            raw_default_actions = _require_array(
                raw_defaults.get(trigger.name), field, non_empty=True
            )
            action_names: list[str] = []
            for item in raw_default_actions:
                action_name = _require_string(item, f"{field}[]")
                if action_name not in available_names:
                    raise _validation_error(
                        f"{field} references undeclared action {action_name!r}"
                    )
                action_names.append(action_name)
            defaults[trigger.name] = tuple(action_names)

        return ActionsSection(
            available=tuple(available), defaults=MappingProxyType(defaults)
        )

    @staticmethod
    def _parse_prompts(value: object, triggers: tuple[Trigger, ...]) -> dict[str, str]:
        raw_prompts = _require_mapping(value, "prompts")
        prompts: dict[str, str] = {}
        trigger_names = {trigger.name for trigger in triggers}
        for prompt_key, template_value in raw_prompts.items():
            template = _require_string(
                template_value,
                f"prompts.{prompt_key}",
                non_empty=False,
                preserve=True,
            )
            count = len(HISTORY_PLACEHOLDER_RE.findall(template))
            if count > MAX_HISTORY_PLACEHOLDERS:
                scope = "trigger" if prompt_key in trigger_names else "prompt key"
                raise _validation_error(
                    f"{scope} {prompt_key!r} contains {count} history placeholders; "
                    f"maximum allowed is {MAX_HISTORY_PLACEHOLDERS}"
                )
            prompts[prompt_key] = template
        return prompts


__all__ = [
    "ActionRef",
    "ActionTier",
    "ActionsSection",
    "EscalationTier",
    "MAX_HISTORY_PLACEHOLDERS",
    "ReasoningPolicy",
    "SensorRequirement",
    "SkillPackage",
    "SkillYamlNormaliser",
    "Trigger",
]
