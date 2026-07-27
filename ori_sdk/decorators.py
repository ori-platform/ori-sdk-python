# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Decorator-based authoring for validated Ori skill packages.

Decorated callables are metadata declarations only. The SDK never executes,
serializes, or inspects their bodies.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence, TypeVar, cast

from ori_sdk.errors import ORI_SDK_SKILL_VALIDATION, SkillMetadataValidationError
from ori_sdk.skill_package import (
    ActionRef,
    ActionTier,
    EscalationTier,
    ReasoningPolicy,
    SensorRequirement,
    SkillPackage,
    SkillYamlNormaliser,
    Trigger,
)

_DecoratedT = TypeVar("_DecoratedT")


def _authoring_error(details: str) -> SkillMetadataValidationError:
    return SkillMetadataValidationError(details, code=ORI_SDK_SKILL_VALIDATION)


def _callable_name(target: object, explicit_name: str | None) -> str:
    target_is_callable = callable(target)
    if not target_is_callable:
        raise _authoring_error("decorator target must be callable")
    try:
        inferred_name: object = getattr(target, "__name__", None)
    except Exception as exc:
        raise _authoring_error(
            f"decorated callable name could not be read safely: {exc}"
        ) from exc
    name: object = explicit_name if explicit_name is not None else inferred_name
    if not isinstance(name, str) or not name.strip():
        raise _authoring_error(
            "decorated callable must have a function name or an explicit name"
        )
    return name


def _action_names(actions: object, trigger_name: str) -> tuple[str, ...]:
    if isinstance(actions, (str, bytes)) or not isinstance(actions, Sequence):
        raise _authoring_error(
            f"trigger {trigger_name!r} actions must be a non-empty sequence"
        )
    try:
        names = tuple(actions)
    except Exception as exc:
        raise _authoring_error(
            f"trigger {trigger_name!r} actions could not be read safely: {exc}"
        ) from exc
    if not names:
        raise _authoring_error(
            f"trigger {trigger_name!r} actions must be a non-empty sequence"
        )
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise _authoring_error(
                f"trigger {trigger_name!r} action names must be non-empty strings"
            )
    return cast(tuple[str, ...], names)


def _copy_config(config: Mapping[str, object]) -> dict[str, object]:
    try:
        return deepcopy(dict(config))
    except Exception as exc:
        raise _authoring_error(f"config could not be copied safely: {exc}") from exc


@dataclass(frozen=True, slots=True)
class _TriggerDeclaration:
    trigger: Trigger
    action_names: tuple[str, ...]
    prompt: str | None


class Agent:
    """An isolated metadata builder for one Ori skill package.

    Registration happens when an ``@action`` or ``@when`` decorator is applied.
    ``compile()`` snapshots those declarations and delegates final validation
    to ``SkillYamlNormaliser``.
    """

    __slots__ = (
        "_actions",
        "_author",
        "_config",
        "_name",
        "_sensors_required",
        "_signature",
        "_triggers",
        "_version",
    )

    def __init__(
        self,
        name: str,
        version: str,
        author: str,
        *,
        signature: str | None = None,
        sensors_required: Sequence[SensorRequirement] = (),
        config: Mapping[str, object] | None = None,
    ) -> None:
        if isinstance(sensors_required, (str, bytes)) or not isinstance(
            sensors_required, Sequence
        ):
            raise _authoring_error(
                "sensors_required must be a sequence of SensorRequirement values"
            )
        try:
            sensors = tuple(sensors_required)
        except Exception as exc:
            raise _authoring_error(
                f"sensors_required could not be read safely: {exc}"
            ) from exc
        for index, sensor in enumerate(sensors):
            if not isinstance(sensor, SensorRequirement):
                raise _authoring_error(
                    f"sensors_required[{index}] must be a SensorRequirement"
                )
        if config is not None and not isinstance(config, Mapping):
            raise _authoring_error("config must be a mapping")
        config_source: Mapping[str, object] = {} if config is None else config
        config_snapshot = _copy_config(config_source)

        self._name = name
        self._version = version
        self._author = author
        self._signature = signature
        self._sensors_required = sensors
        self._config = config_snapshot
        self._actions: dict[str, ActionRef] = {}
        self._triggers: dict[str, _TriggerDeclaration] = {}

    @property
    def name(self) -> str:
        """Return the declared skill name."""

        return self._name

    @property
    def version(self) -> str:
        """Return the declared skill version."""

        return self._version

    @property
    def author(self) -> str:
        """Return the declared skill author."""

        return self._author

    def action(
        self,
        *,
        tier: ActionTier,
        name: str | None = None,
    ) -> Callable[[_DecoratedT], _DecoratedT]:
        """Return an agent-bound action metadata decorator."""

        return action(self, tier=tier, name=name)

    def when(
        self,
        condition: str,
        *,
        tier: ActionTier,
        actions: Sequence[str],
        name: str | None = None,
        cooldown_seconds: int = 0,
        escalate_to: EscalationTier | None = None,
        prompt: str | None = None,
        reasoning_policy: ReasoningPolicy | None = None,
        requires_approval: bool = False,
        approval_timeout_seconds: int = 300,
        safe_default_action: str | None = None,
    ) -> Callable[[_DecoratedT], _DecoratedT]:
        """Return an agent-bound trigger metadata decorator."""

        return when(
            self,
            condition,
            tier=tier,
            actions=actions,
            name=name,
            cooldown_seconds=cooldown_seconds,
            escalate_to=escalate_to,
            prompt=prompt,
            reasoning_policy=reasoning_policy,
            requires_approval=requires_approval,
            approval_timeout_seconds=approval_timeout_seconds,
            safe_default_action=safe_default_action,
        )

    def _register_action(self, declaration: ActionRef) -> None:
        if declaration.name in self._actions:
            raise _authoring_error(
                f"duplicate decorated action name {declaration.name!r}"
            )
        self._actions[declaration.name] = declaration

    def _register_trigger(self, declaration: _TriggerDeclaration) -> None:
        trigger_name = declaration.trigger.name
        if trigger_name in self._triggers:
            raise _authoring_error(f"duplicate decorated trigger name {trigger_name!r}")
        self._triggers[trigger_name] = declaration

    def compile(self) -> SkillPackage:
        """Compile declarations through the YAML-equivalent validation path."""

        triggers = list(self._triggers.values())
        document: dict[str, object] = {
            "name": self._name,
            "version": self._version,
            "author": self._author,
            "sensors_required": [sensor.to_dict() for sensor in self._sensors_required],
            "triggers": [declaration.trigger.to_dict() for declaration in triggers],
            "prompts": {
                declaration.trigger.name: declaration.prompt
                for declaration in triggers
                if declaration.prompt is not None
            },
            "actions": {
                "available": [
                    declaration.to_dict() for declaration in self._actions.values()
                ],
                "defaults": {
                    declaration.trigger.name: list(declaration.action_names)
                    for declaration in triggers
                },
            },
            "config": _copy_config(self._config),
        }
        if self._signature is not None:
            document["signature"] = self._signature
        return SkillYamlNormaliser.normalise(document)


def action(
    agent: Agent,
    *,
    tier: ActionTier,
    name: str | None = None,
) -> Callable[[_DecoratedT], _DecoratedT]:
    """Declare an action without executing or retaining the decorated callable."""

    if not isinstance(agent, Agent):
        raise _authoring_error("action decorator requires an Agent")

    def decorator(target: _DecoratedT) -> _DecoratedT:
        declaration = ActionRef(name=_callable_name(target, name), tier=tier)
        agent._register_action(declaration)
        return target

    return decorator


def when(
    agent: Agent,
    condition: str,
    *,
    tier: ActionTier,
    actions: Sequence[str],
    name: str | None = None,
    cooldown_seconds: int = 0,
    escalate_to: EscalationTier | None = None,
    prompt: str | None = None,
    reasoning_policy: ReasoningPolicy | None = None,
    requires_approval: bool = False,
    approval_timeout_seconds: int = 300,
    safe_default_action: str | None = None,
) -> Callable[[_DecoratedT], _DecoratedT]:
    """Declare a trigger whose condition and defaults are explicit metadata."""

    if not isinstance(agent, Agent):
        raise _authoring_error("when decorator requires an Agent")
    if tier == "C" and safe_default_action is None:
        raise _authoring_error(
            "Tier C decorated triggers require an explicit safe_default_action"
        )
    if tier == "D" and prompt is not None:
        raise _authoring_error("Tier D decorated triggers cannot declare a prompt")
    action_subject = (
        name if isinstance(name, str) and name.strip() else "decorated trigger"
    )
    action_names = _action_names(actions, action_subject)

    escalation: EscalationTier
    if escalate_to is None:
        escalation = "rule" if tier == "D" else "local_slm"
    else:
        escalation = escalate_to
    safe_default = (
        "log_to_dashboard" if safe_default_action is None else safe_default_action
    )

    def decorator(target: _DecoratedT) -> _DecoratedT:
        trigger = Trigger(
            name=_callable_name(target, name),
            condition=condition,
            action_tier=tier,
            cooldown_seconds=cooldown_seconds,
            escalate_to=escalation,
            bypass_llm=tier == "D",
            reasoning_policy=reasoning_policy,
            requires_approval=requires_approval,
            approval_timeout_seconds=approval_timeout_seconds,
            safe_default_action=safe_default,
        )
        declaration = _TriggerDeclaration(
            trigger=trigger,
            action_names=action_names,
            prompt=prompt,
        )
        agent._register_trigger(declaration)
        return target

    return decorator


__all__ = ["Agent", "action", "when"]
