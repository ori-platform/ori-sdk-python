# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import cast, overload

import pytest

from ori_sdk import (
    ActionTier,
    Agent,
    EscalationTier,
    SensorRequirement,
    SkillPackage,
    SkillYamlNormaliser,
    action,
    when,
)
from ori_sdk.errors import ORI_SDK_SKILL_VALIDATION, SkillMetadataValidationError


class _ExplodingSensors(Sequence[SensorRequirement]):
    def __len__(self) -> int:
        return 1

    @overload
    def __getitem__(self, index: int) -> SensorRequirement: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[SensorRequirement]: ...

    def __getitem__(
        self, index: int | slice
    ) -> SensorRequirement | Sequence[SensorRequirement]:
        raise RuntimeError(f"sensor iteration exploded at {index!r}")


class _ExplodingActions(Sequence[str]):
    def __len__(self) -> int:
        return 1

    @overload
    def __getitem__(self, index: int) -> str: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[str]: ...

    def __getitem__(self, index: int | slice) -> str | Sequence[str]:
        raise RuntimeError(f"action iteration exploded at {index!r}")


class _ExplodingCallableName:
    def __call__(self) -> None:
        pass

    @property
    def __name__(self) -> str:
        raise RuntimeError("name lookup exploded")


class _FlakyDeepCopy:
    def __init__(self) -> None:
        self.calls = 0

    def __deepcopy__(self, memo: dict[int, object]) -> _FlakyDeepCopy:
        del memo
        self.calls += 1
        if self.calls == 1:
            return self
        raise RuntimeError("second deepcopy exploded")


def _agent(
    *,
    name: str = "decorated-energy-guard",
    config: dict[str, object] | None = None,
) -> Agent:
    return Agent(
        name=name,
        version="1.0.0",
        author="ori",
        signature="bundled",
        sensors_required=(SensorRequirement(type="current_clamp", protocol="modbus"),),
        config={} if config is None else config,
    )


def _declare_alert(agent: Agent, name: str = "alert_operator") -> None:
    @agent.action(name=name, tier="A")
    def alert_operator() -> None:
        raise AssertionError("decorated action bodies must never execute")


def test_agent_compile_to_skill_package() -> None:
    agent = _agent(config={"threshold": 20})
    executed: list[str] = []

    @agent.action(tier="A")
    def alert_operator() -> None:
        executed.append("action")

    @agent.when(
        "value > 20",
        tier="A",
        actions=("alert_operator",),
        cooldown_seconds=60,
        prompt="Current draw is {value}{unit}.",
    )
    def high_usage() -> None:
        executed.append("trigger")

    package = agent.compile()

    assert isinstance(package, SkillPackage)
    assert package.name == "decorated-energy-guard"
    assert package.version == "1.0.0"
    assert package.author == "ori"
    assert package.signature == "bundled"
    assert package.sensors_required == (
        SensorRequirement(type="current_clamp", protocol="modbus"),
    )
    assert package.triggers[0].name == "high_usage"
    assert package.triggers[0].condition == "value > 20"
    assert package.actions.available[0].name == "alert_operator"
    assert package.actions.defaults["high_usage"] == ("alert_operator",)
    assert package.prompts["high_usage"] == "Current draw is {value}{unit}."
    assert package.config["threshold"] == 20
    assert executed == []
    assert SkillYamlNormaliser.normalise(package.to_dict()).to_dict() == (
        package.to_dict()
    )


def test_when_requires_tier() -> None:
    agent = _agent()
    untyped_when = cast(Callable[..., object], agent.when)

    with pytest.raises(TypeError, match="tier"):
        untyped_when("value > 20", actions=("alert_operator",))


def test_tier_b_requires_policy() -> None:
    agent = _agent()

    @agent.action(tier="B")
    def shed_load() -> None:
        pass

    @agent.when("value > 30", tier="B", actions=("shed_load",))
    def shed_noncritical() -> None:
        pass

    with pytest.raises(SkillMetadataValidationError, match="physical Tier B") as exc:
        agent.compile()

    assert exc.value.code == ORI_SDK_SKILL_VALIDATION


def test_tier_b_accepts_approval_policy() -> None:
    agent = _agent()

    @agent.action(tier="B")
    def shed_load() -> None:
        pass

    @agent.when(
        "value > 30",
        tier="B",
        actions=("shed_load",),
        requires_approval=True,
    )
    def shed_noncritical() -> None:
        pass

    trigger = agent.compile().triggers[0]

    assert trigger.requires_approval is True
    assert trigger.reasoning_policy is None


def test_tier_b_post_action_requires_tier_a_notification() -> None:
    agent = _agent()

    @agent.action(tier="B")
    def shed_load() -> None:
        pass

    @agent.when(
        "value > 30",
        tier="B",
        actions=("shed_load",),
        reasoning_policy="post_action",
    )
    def shed_noncritical() -> None:
        pass

    with pytest.raises(SkillMetadataValidationError, match="Tier A default action"):
        agent.compile()


def test_tier_b_accepts_post_action_with_tier_a_notification() -> None:
    agent = _agent()
    _declare_alert(agent)

    @agent.action(tier="B")
    def shed_load() -> None:
        pass

    @agent.when(
        "value > 30",
        tier="B",
        actions=("shed_load", "alert_operator"),
        reasoning_policy="post_action",
        prompt="Explain the completed load shed.",
    )
    def shed_noncritical() -> None:
        pass

    package = agent.compile()

    assert package.triggers[0].reasoning_policy == "post_action"
    assert package.actions.defaults["shed_noncritical"] == (
        "shed_load",
        "alert_operator",
    )


def test_tier_c_requires_safe_default() -> None:
    agent = _agent()

    with pytest.raises(
        SkillMetadataValidationError, match="explicit safe_default_action"
    ) as exc:
        agent.when(
            "value > 40",
            tier="C",
            actions=("isolate_circuit",),
        )

    assert exc.value.code == ORI_SDK_SKILL_VALIDATION


def test_tier_c_compiles_explicit_safe_default() -> None:
    agent = _agent()

    @agent.action(tier="C")
    def isolate_circuit() -> None:
        pass

    @agent.when(
        "value > 40",
        tier="C",
        actions=("isolate_circuit",),
        escalate_to="gateway",
        safe_default_action="log_to_dashboard",
    )
    def isolate_fault() -> None:
        pass

    trigger = agent.compile().triggers[0]

    assert trigger.action_tier == "C"
    assert trigger.escalate_to == "gateway"
    assert trigger.safe_default_action == "log_to_dashboard"


def test_decorator_gateway_not_cloud() -> None:
    agent = _agent()
    _declare_alert(agent)

    @agent.when(
        "value > 20",
        tier="A",
        actions=("alert_operator",),
        escalate_to="gateway",
    )
    def needs_gateway_reasoning() -> None:
        pass

    assert agent.compile().triggers[0].escalate_to == "gateway"

    invalid = _agent(name="invalid-cloud")
    _declare_alert(invalid)
    with pytest.raises(SkillMetadataValidationError, match="escalate_to"):

        @invalid.when(
            "value > 20",
            tier="A",
            actions=("alert_operator",),
            escalate_to=cast(EscalationTier, "cloud"),
        )
        def legacy_cloud_reasoning() -> None:
            pass


def test_tier_d_is_rule_only_and_has_no_prompt() -> None:
    agent = _agent()

    @agent.action(tier="D")
    def emergency_trip() -> None:
        pass

    @agent.when("value > 50", tier="D", actions=("emergency_trip",))
    def dangerous_overcurrent() -> None:
        pass

    package = agent.compile()
    trigger = package.triggers[0]

    assert trigger.action_tier == "D"
    assert trigger.escalate_to == "rule"
    assert trigger.bypass_llm is True
    assert "dangerous_overcurrent" not in package.prompts


def test_tier_d_rejects_prompt_and_non_rule_escalation() -> None:
    prompt_agent = _agent(name="tier-d-prompt")
    with pytest.raises(SkillMetadataValidationError, match="cannot declare a prompt"):
        prompt_agent.when(
            "value > 50",
            tier="D",
            actions=("emergency_trip",),
            prompt="Ask an LLM what to do.",
        )

    escalation_agent = _agent(name="tier-d-escalation")
    with pytest.raises(SkillMetadataValidationError, match="must use escalate_to"):

        @escalation_agent.when(
            "value > 50",
            tier="D",
            actions=("emergency_trip",),
            escalate_to="gateway",
        )
        def dangerous_overcurrent() -> None:
            pass


def test_callable_condition_is_rejected_explicitly() -> None:
    agent = _agent()

    with pytest.raises(SkillMetadataValidationError, match="condition.*string"):

        @agent.when(
            cast(str, lambda value: value > 20),
            tier="A",
            actions=("alert_operator",),
        )
        def unsafe_condition() -> None:
            pass


def test_multiple_triggers_and_actions_compile_in_declaration_order() -> None:
    agent = _agent()
    _declare_alert(agent)

    @agent.action(tier="B")
    def shed_load() -> None:
        pass

    @agent.when("value > 20", tier="A", actions=("alert_operator",))
    def high_usage() -> None:
        pass

    @agent.when(
        "value > 30",
        tier="B",
        actions=("shed_load", "alert_operator"),
        reasoning_policy="post_action",
    )
    def shed_noncritical() -> None:
        pass

    package = agent.compile()

    assert [action_ref.name for action_ref in package.actions.available] == [
        "alert_operator",
        "shed_load",
    ]
    assert [trigger.name for trigger in package.triggers] == [
        "high_usage",
        "shed_noncritical",
    ]


def test_compile_rejects_undeclared_default_action() -> None:
    agent = _agent()
    _declare_alert(agent)

    @agent.when(
        "value > 20",
        tier="A",
        actions=("missing_action",),
    )
    def high_usage() -> None:
        pass

    with pytest.raises(SkillMetadataValidationError, match="undeclared action"):
        agent.compile()


def test_decorators_reject_empty_action_lists_and_names() -> None:
    empty_list_agent = _agent(name="empty-list")
    with pytest.raises(SkillMetadataValidationError, match="non-empty sequence"):

        @empty_list_agent.when("value > 20", tier="A", actions=())
        def high_usage() -> None:
            pass

    empty_name_agent = _agent(name="empty-name")
    with pytest.raises(SkillMetadataValidationError, match="non-empty strings"):

        @empty_name_agent.when("value > 20", tier="A", actions=(" ",))
        def high_usage_again() -> None:
            pass


def test_duplicate_decorated_names_are_rejected_without_replacement() -> None:
    agent = _agent()

    @agent.action(name="notify", tier="A")
    def first_action() -> None:
        pass

    with pytest.raises(
        SkillMetadataValidationError, match="duplicate decorated action"
    ):

        @agent.action(name="notify", tier="A")
        def second_action() -> None:
            pass

    @agent.when(
        "value > 20",
        name="high_usage",
        tier="A",
        actions=("notify",),
    )
    def first_trigger() -> None:
        pass

    with pytest.raises(
        SkillMetadataValidationError, match="duplicate decorated trigger"
    ):

        @agent.when(
            "value > 30",
            name="high_usage",
            tier="A",
            actions=("notify",),
        )
        def second_trigger() -> None:
            pass

    package = agent.compile()

    assert package.actions.available[0].tier == "A"
    assert package.triggers[0].condition == "value > 20"


def test_module_level_decorators_are_agent_scoped() -> None:
    first = _agent(name="first")
    second = _agent(name="second")

    @action(first, tier="A")
    def first_alert() -> None:
        pass

    @when(first, "value > 20", tier="A", actions=("first_alert",))
    def first_trigger() -> None:
        pass

    @action(second, tier="A")
    def second_alert() -> None:
        pass

    @when(second, "value > 30", tier="A", actions=("second_alert",))
    def second_trigger() -> None:
        pass

    first_package = first.compile()
    second_package = second.compile()

    assert first_package.actions.available[0].name == "first_alert"
    assert first_package.triggers[0].name == "first_trigger"
    assert second_package.actions.available[0].name == "second_alert"
    assert second_package.triggers[0].name == "second_trigger"


def test_decorators_return_original_callable_without_execution() -> None:
    agent = _agent()
    calls = 0

    def notify() -> None:
        nonlocal calls
        calls += 1

    decorated_action = agent.action(tier="A")(notify)

    def high_usage() -> None:
        nonlocal calls
        calls += 1

    decorated_trigger = agent.when(
        "value > 20",
        tier="A",
        actions=("notify",),
    )(high_usage)

    assert decorated_action is notify
    assert decorated_trigger is high_usage
    assert calls == 0
    agent.compile()
    assert calls == 0


def test_compile_is_deterministic_and_does_not_share_mutable_config() -> None:
    thresholds = [20, 30]
    source_config: dict[str, object] = {"thresholds": thresholds}
    agent = _agent(config=source_config)
    _declare_alert(agent)

    @agent.when("value > 20", tier="A", actions=("alert_operator",))
    def high_usage() -> None:
        pass

    thresholds.append(40)
    source_config["site"] = "changed-after-construction"
    first = agent.compile()
    second = agent.compile()

    assert first.to_dict() == second.to_dict()
    assert first.config["thresholds"] == (20, 30)
    assert "site" not in first.config


def test_when_snapshots_actions_before_decorator_application() -> None:
    agent = _agent()
    _declare_alert(agent, name="first_action")
    _declare_alert(agent, name="second_action")
    action_names = ["first_action"]
    pending_decorator = agent.when(
        "value > 20",
        tier="A",
        actions=action_names,
    )
    action_names[0] = "second_action"

    @pending_decorator
    def high_usage() -> None:
        pass

    assert agent.compile().actions.defaults["high_usage"] == ("first_action",)


def test_compile_rejects_invalid_agent_metadata_through_normaliser() -> None:
    agent = _agent(name=" ")
    _declare_alert(agent)

    @agent.when("value > 20", tier="A", actions=("alert_operator",))
    def high_usage() -> None:
        pass

    with pytest.raises(SkillMetadataValidationError, match="name") as exc:
        agent.compile()

    assert exc.value.code == ORI_SDK_SKILL_VALIDATION


def test_compile_enforces_normaliser_prompt_limits() -> None:
    agent = _agent()
    _declare_alert(agent)
    prompt = " ".join("{history.last_value('mains')}" for _ in range(17))

    @agent.when(
        "value > 20",
        tier="A",
        actions=("alert_operator",),
        prompt=prompt,
    )
    def high_usage() -> None:
        pass

    with pytest.raises(
        SkillMetadataValidationError, match="maximum allowed is 16"
    ) as exc:
        agent.compile()

    assert exc.value.code == ORI_SDK_SKILL_VALIDATION


def test_compile_rejects_non_json_and_cyclic_config() -> None:
    invalid = _agent(config={"unsupported": {"set-value"}})
    _declare_alert(invalid)

    @invalid.when("value > 20", tier="A", actions=("alert_operator",))
    def invalid_config_trigger() -> None:
        pass

    with pytest.raises(SkillMetadataValidationError, match="JSON-compatible"):
        invalid.compile()

    cyclic_config: dict[str, object] = {}
    cyclic_config["self"] = cyclic_config
    cyclic = _agent(name="cyclic", config=cyclic_config)
    _declare_alert(cyclic)

    @cyclic.when("value > 20", tier="A", actions=("alert_operator",))
    def cyclic_config_trigger() -> None:
        pass

    with pytest.raises(SkillMetadataValidationError, match="cyclic reference"):
        cyclic.compile()


def test_agent_rejects_invalid_sensor_collection() -> None:
    invalid_sensors = cast(Sequence[SensorRequirement], ("temperature",))

    with pytest.raises(SkillMetadataValidationError, match=r"sensors_required\[0\]"):
        Agent(
            name="invalid-sensors",
            version="1.0.0",
            author="ori",
            sensors_required=invalid_sensors,
        )


def test_decorators_reject_invalid_agent_and_target() -> None:
    invalid_agent = cast(Agent, object())
    with pytest.raises(SkillMetadataValidationError, match="requires an Agent"):
        action(invalid_agent, tier="A")
    with pytest.raises(SkillMetadataValidationError, match="requires an Agent"):
        when(
            invalid_agent,
            "value > 20",
            tier="A",
            actions=("notify",),
        )

    agent = _agent()
    apply_action = cast(Callable[[object], object], agent.action(tier="A"))
    with pytest.raises(SkillMetadataValidationError, match="must be callable"):
        apply_action("not-callable")


def test_public_boundaries_wrap_caller_protocol_failures() -> None:
    with pytest.raises(
        SkillMetadataValidationError, match="sensors_required could not be read safely"
    ) as sensors_exc:
        Agent(
            name="bad-sensors",
            version="1.0.0",
            author="ori",
            sensors_required=_ExplodingSensors(),
        )

    actions_agent = _agent(name="bad-actions")
    with pytest.raises(
        SkillMetadataValidationError, match="actions could not be read safely"
    ) as actions_exc:
        actions_agent.when(
            "value > 20",
            tier="A",
            actions=_ExplodingActions(),
        )

    name_agent = _agent(name="bad-name")
    with pytest.raises(
        SkillMetadataValidationError,
        match="callable name could not be read safely",
    ) as name_exc:
        name_agent.action(tier="A")(_ExplodingCallableName())

    flaky = _FlakyDeepCopy()
    config_agent = _agent(name="bad-config", config={"flaky": flaky})
    _declare_alert(config_agent)

    @config_agent.when("value > 20", tier="A", actions=("alert_operator",))
    def high_usage() -> None:
        pass

    with pytest.raises(
        SkillMetadataValidationError, match="config could not be copied safely"
    ) as config_exc:
        config_agent.compile()

    assert {
        sensors_exc.value.code,
        actions_exc.value.code,
        name_exc.value.code,
        config_exc.value.code,
    } == {ORI_SDK_SKILL_VALIDATION}


def test_invalid_decorated_names_and_tiers_use_typed_errors() -> None:
    invalid_action = _agent(name="invalid-action")
    with pytest.raises(SkillMetadataValidationError, match="invalid tier") as exc:

        @invalid_action.action(tier=cast(ActionTier, "Z"))
        def unsupported_action() -> None:
            pass

    assert exc.value.code == ORI_SDK_SKILL_VALIDATION

    invalid_trigger = _agent(name="invalid-trigger")
    with pytest.raises(SkillMetadataValidationError, match="invalid name format"):

        @invalid_trigger.when(
            "value > 20",
            name="bad trigger",
            tier="A",
            actions=("notify",),
        )
        def unsupported_trigger() -> None:
            pass


def test_compile_requires_at_least_one_action_and_trigger() -> None:
    with pytest.raises(SkillMetadataValidationError, match="triggers"):
        _agent(name="empty-agent").compile()

    actions_only = _agent(name="actions-only")
    _declare_alert(actions_only)
    with pytest.raises(SkillMetadataValidationError, match="triggers"):
        actions_only.compile()

    triggers_only = _agent(name="triggers-only")

    @triggers_only.when("value > 20", tier="A", actions=("alert_operator",))
    def high_usage() -> None:
        pass

    with pytest.raises(SkillMetadataValidationError, match="actions.available"):
        triggers_only.compile()


def test_agent_properties_are_read_only_metadata_views() -> None:
    agent = _agent()

    assert agent.name == "decorated-energy-guard"
    assert agent.version == "1.0.0"
    assert agent.author == "ori"

    with pytest.raises(AttributeError):
        setattr(agent, "name", "changed")
