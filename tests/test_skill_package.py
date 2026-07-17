# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import cast

import pytest

from ori_sdk import (
    ActionRef,
    ActionsSection,
    ActionTier,
    EscalationTier,
    ReasoningPolicy,
    SensorRequirement,
    SkillPackage,
    SkillYamlNormaliser,
    Trigger,
)
from ori_sdk.errors import ORI_SDK_SKILL_VALIDATION, SkillMetadataValidationError
from ori_sdk.validation import MAX_HISTORY_PLACEHOLDERS, validate_skill_metadata

FIXTURE = Path(__file__).parent / "fixtures" / "skill_package_v1.json"


def _fixture() -> dict[str, object]:
    return cast(dict[str, object], json.loads(FIXTURE.read_text(encoding="utf-8")))


def _triggers(skill: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], skill["triggers"])


def _actions(skill: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], skill["actions"])


def _defaults(skill: dict[str, object]) -> dict[str, list[str]]:
    return cast(dict[str, list[str]], _actions(skill)["defaults"])


def _direct_trigger(
    *,
    name: str = "notify",
    action_tier: ActionTier = "A",
    escalate_to: EscalationTier = "local_slm",
    bypass_llm: bool = False,
    reasoning_policy: ReasoningPolicy | None = None,
    requires_approval: bool = False,
    safe_default_action: str = "log_to_dashboard",
) -> Trigger:
    return Trigger(
        name=name,
        condition="value > 1",
        action_tier=action_tier,
        cooldown_seconds=0,
        escalate_to=escalate_to,
        bypass_llm=bypass_llm,
        reasoning_policy=reasoning_policy,
        requires_approval=requires_approval,
        approval_timeout_seconds=300,
        safe_default_action=safe_default_action,
    )


def _direct_package() -> SkillPackage:
    trigger = _direct_trigger()
    action = ActionRef(name="alert_operator", tier="A")
    return SkillPackage(
        name="direct-skill",
        version="1.0.0",
        author="ori",
        signature="bundled",
        sensors_required=(SensorRequirement(type="temperature"),),
        triggers=(trigger,),
        prompts={trigger.name: "Temperature is {value}{unit}."},
        actions=ActionsSection(
            available=(action,), defaults={trigger.name: (action.name,)}
        ),
        config={"threshold": 30},
    )


def test_skill_package_loads_fixture() -> None:
    expected = _fixture()

    package = SkillYamlNormaliser.load_and_validate(FIXTURE)

    assert isinstance(package, SkillPackage)
    assert package.name == "canonical-energy-guard"
    assert package.to_dict() == expected
    assert json.dumps(package.to_dict()) == json.dumps(expected)


def test_skill_package_defaults_are_explicit() -> None:
    skill = _fixture()
    trigger = _triggers(skill)[0]
    for field in (
        "condition",
        "cooldown_seconds",
        "escalate_to",
        "bypass_llm",
        "requires_approval",
        "approval_timeout_seconds",
        "safe_default_action",
    ):
        trigger.pop(field)

    normalised = SkillYamlNormaliser.normalise(skill).triggers[0]

    assert normalised.condition == ""
    assert normalised.cooldown_seconds == 0
    assert normalised.escalate_to == "local_slm"
    assert normalised.bypass_llm is False
    assert normalised.requires_approval is False
    assert normalised.approval_timeout_seconds == 300
    assert normalised.safe_default_action == "log_to_dashboard"


def test_models_and_nested_collections_are_immutable() -> None:
    package = SkillYamlNormaliser.load_and_validate(FIXTURE)

    with pytest.raises(FrozenInstanceError):
        package.name = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        package.actions.defaults["high_usage"] = ("trip_relay",)  # type: ignore[index]
    with pytest.raises(TypeError):
        package.config["site"] = "changed"  # type: ignore[index]
    assert package.config["thresholds"] == (20, 30, 40, 50)


def test_model_constructors_defensively_freeze_caller_owned_collections() -> None:
    source = SkillYamlNormaliser.load_and_validate(FIXTURE)
    prompts = {"high_usage": "original"}
    config: dict[str, object] = {"nested": [1, 2]}
    defaults = dict(source.actions.defaults)

    package = SkillPackage(
        name=source.name,
        version=source.version,
        author=source.author,
        signature=source.signature,
        sensors_required=source.sensors_required,
        triggers=source.triggers,
        prompts=prompts,
        actions=ActionsSection(
            available=source.actions.available,
            defaults=defaults,
        ),
        config=config,
    )
    prompts["high_usage"] = "changed"
    cast(list[int], config["nested"]).append(3)
    defaults["high_usage"] = ("trip_relay",)

    assert package.prompts["high_usage"] == "original"
    assert package.config["nested"] == (1, 2)
    assert package.actions.defaults["high_usage"] == ("alert_whatsapp",)


def test_direct_model_construction_round_trips_through_normaliser() -> None:
    sensor = SensorRequirement(type=" temperature ", protocol=" modbus ")
    trigger = _direct_trigger(name=" notify ")
    action = ActionRef(name=" alert_operator ", tier="A")
    package = SkillPackage(
        name=" direct-skill ",
        version=" 1.0.0 ",
        author=" ori ",
        signature=" bundled ",
        sensors_required=(sensor,),
        triggers=(trigger,),
        prompts={trigger.name: "Alert operator."},
        actions=ActionsSection(
            available=(action,), defaults={trigger.name: (action.name,)}
        ),
        config={},
    )

    assert package.name == "direct-skill"
    assert sensor.type == "temperature"
    assert sensor.protocol == "modbus"
    assert trigger.name == "notify"
    assert action.name == "alert_operator"
    assert SkillYamlNormaliser.normalise(package.to_dict()).to_dict() == (
        package.to_dict()
    )


def test_sensor_requirement_constructor_rejects_empty_fields() -> None:
    with pytest.raises(SkillMetadataValidationError, match="sensor.type"):
        SensorRequirement(type=" ")
    with pytest.raises(SkillMetadataValidationError, match="sensor.protocol"):
        SensorRequirement(type="temperature", protocol=" ")


def test_action_ref_constructor_rejects_invalid_values() -> None:
    with pytest.raises(SkillMetadataValidationError, match="action.name"):
        ActionRef(name=" ", tier="A")
    with pytest.raises(SkillMetadataValidationError, match="invalid tier"):
        ActionRef(name="alert_operator", tier=cast(ActionTier, "Z"))


def test_trigger_constructor_rejects_invalid_identity_and_policy() -> None:
    with pytest.raises(SkillMetadataValidationError, match="invalid name format"):
        _direct_trigger(name="bad trigger")
    with pytest.raises(SkillMetadataValidationError, match="invalid action_tier"):
        _direct_trigger(action_tier=cast(ActionTier, "Z"))
    with pytest.raises(SkillMetadataValidationError, match="escalate_to"):
        _direct_trigger(escalate_to=cast(EscalationTier, "cloud"))
    with pytest.raises(SkillMetadataValidationError, match="non-Tier-D"):
        _direct_trigger(bypass_llm=True)
    with pytest.raises(SkillMetadataValidationError, match="outside Tier B"):
        _direct_trigger(reasoning_policy="post_action")
    with pytest.raises(SkillMetadataValidationError, match="safe_default_action"):
        _direct_trigger(action_tier="C", safe_default_action=" ")


def test_trigger_constructor_canonicalises_tier_d_bypass() -> None:
    trigger = _direct_trigger(action_tier="D", escalate_to="rule", bypass_llm=False)

    assert trigger.bypass_llm is True


def test_actions_section_constructor_rejects_invalid_declarations() -> None:
    action = ActionRef(name="alert_operator", tier="A")
    with pytest.raises(SkillMetadataValidationError, match="non-empty"):
        ActionsSection(available=(), defaults={})
    with pytest.raises(SkillMetadataValidationError, match="duplicate action"):
        ActionsSection(available=(action, action), defaults={"notify": (action.name,)})
    with pytest.raises(SkillMetadataValidationError, match="non-empty"):
        ActionsSection(available=(action,), defaults={"notify": ()})
    with pytest.raises(SkillMetadataValidationError, match="undeclared action"):
        ActionsSection(available=(action,), defaults={"notify": ("missing",)})
    with pytest.raises(SkillMetadataValidationError, match="invalid name format"):
        ActionsSection(available=(action,), defaults={" notify ": (action.name,)})


@pytest.mark.parametrize("field", ["name", "version", "author"])
def test_skill_package_constructor_rejects_empty_metadata(field: str) -> None:
    package = _direct_package()

    with pytest.raises(SkillMetadataValidationError, match=field):
        if field == "name":
            replace(package, name=" ")
        elif field == "version":
            replace(package, version=" ")
        else:
            replace(package, author=" ")


def test_skill_package_constructor_rejects_invalid_signature() -> None:
    with pytest.raises(SkillMetadataValidationError, match="signature"):
        replace(_direct_package(), signature="rsa:not-supported")


def test_skill_package_constructor_rejects_duplicate_triggers() -> None:
    package = _direct_package()
    trigger = package.triggers[0]

    with pytest.raises(SkillMetadataValidationError, match="duplicate trigger"):
        replace(package, triggers=(trigger, trigger))


def test_skill_package_constructor_rejects_invalid_defaults_coverage() -> None:
    package = _direct_package()
    missing_defaults = ActionsSection(
        available=package.actions.available,
        defaults={},
    )
    extra_defaults = ActionsSection(
        available=package.actions.available,
        defaults={
            package.triggers[0].name: (package.actions.available[0].name,),
            "unknown_trigger": (package.actions.available[0].name,),
        },
    )

    with pytest.raises(SkillMetadataValidationError, match="missing actions.defaults"):
        replace(package, actions=missing_defaults)
    with pytest.raises(SkillMetadataValidationError, match="unknown trigger"):
        replace(package, actions=extra_defaults)


def test_skill_package_constructor_rejects_invalid_tier_b_policy() -> None:
    trigger = _direct_trigger(name="shed_load", action_tier="B")
    physical_action = ActionRef(name="shed_noncritical", tier="B")
    actions = ActionsSection(
        available=(physical_action,),
        defaults={trigger.name: (physical_action.name,)},
    )

    with pytest.raises(SkillMetadataValidationError, match="physical Tier B"):
        SkillPackage(
            name="tier-b-skill",
            version="1.0.0",
            author="ori",
            signature="bundled",
            sensors_required=(),
            triggers=(trigger,),
            prompts={},
            actions=actions,
            config={},
        )


def test_skill_package_constructor_enforces_prompt_history_limit() -> None:
    package = _direct_package()
    oversized_prompt = " ".join(
        "{history.last_value('sensor')}" for _ in range(MAX_HISTORY_PLACEHOLDERS + 1)
    )

    with pytest.raises(SkillMetadataValidationError, match="maximum allowed is 16"):
        replace(package, prompts={package.triggers[0].name: oversized_prompt})


def test_preserves_condition_and_prompt_text_verbatim() -> None:
    skill = _fixture()
    condition = "  value > 20  "
    prompt = "  Keep intentional prompt whitespace.  \n"
    _triggers(skill)[0]["condition"] = condition
    cast(dict[str, str], skill["prompts"])["high_usage"] = prompt

    package = SkillYamlNormaliser.normalise(skill)

    assert package.triggers[0].condition == condition
    assert package.prompts["high_usage"] == prompt
    assert (
        cast(list[dict[str, object]], package.to_dict()["triggers"])[0]["condition"]
        == condition
    )
    assert cast(dict[str, str], package.to_dict()["prompts"])["high_usage"] == prompt


def test_rejects_non_json_config_values_with_typed_error() -> None:
    skill = _fixture()
    skill["config"] = {"unsupported": {"mutable-set"}}

    with pytest.raises(SkillMetadataValidationError, match="JSON-compatible") as exc:
        SkillYamlNormaliser.normalise(skill)

    assert exc.value.code == ORI_SDK_SKILL_VALIDATION


def test_rejects_cyclic_config_with_typed_error() -> None:
    skill = _fixture()
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    skill["config"] = cyclic

    with pytest.raises(SkillMetadataValidationError, match="cyclic reference") as exc:
        SkillYamlNormaliser.normalise(skill)

    assert exc.value.code == ORI_SDK_SKILL_VALIDATION


def test_skill_package_rejects_missing_action_tier() -> None:
    skill = _fixture()
    _triggers(skill)[0].pop("action_tier")

    with pytest.raises(SkillMetadataValidationError) as exc_info:
        SkillYamlNormaliser.normalise(skill)

    assert exc_info.value.code == ORI_SDK_SKILL_VALIDATION
    assert "action_tier" in exc_info.value.details


@pytest.mark.parametrize("field", ["name", "version", "author"])
def test_skill_package_rejects_missing_required_metadata(field: str) -> None:
    skill = _fixture()
    skill.pop(field)

    with pytest.raises(SkillMetadataValidationError, match=field) as exc_info:
        SkillYamlNormaliser.normalise(skill)

    assert exc_info.value.code == ORI_SDK_SKILL_VALIDATION


@pytest.mark.parametrize("field,value", [("bypass_llm", 1), ("cooldown_seconds", True)])
def test_rejects_coercible_but_incorrect_scalar_types(
    field: str, value: object
) -> None:
    skill = _fixture()
    _triggers(skill)[0][field] = value

    with pytest.raises(SkillMetadataValidationError, match=field):
        SkillYamlNormaliser.normalise(skill)


def test_skill_package_rejects_cloud_escalation() -> None:
    skill = _fixture()
    _triggers(skill)[0]["escalate_to"] = "cloud"

    with pytest.raises(
        SkillMetadataValidationError, match="rule, local_slm, or gateway"
    ):
        SkillYamlNormaliser.normalise(skill)


def test_rejects_bypass_llm_outside_tier_d() -> None:
    skill = _fixture()
    _triggers(skill)[0]["bypass_llm"] = True

    with pytest.raises(SkillMetadataValidationError, match="non-Tier-D"):
        SkillYamlNormaliser.normalise(skill)


def test_tier_d_always_normalises_to_bypass_llm() -> None:
    skill = _fixture()
    tier_d_trigger = _triggers(skill)[3]
    tier_d_trigger["bypass_llm"] = False
    tier_d_trigger.pop("escalate_to")

    package = SkillYamlNormaliser.normalise(skill)

    assert package.triggers[3].bypass_llm is True
    assert package.triggers[3].escalate_to == "rule"


@pytest.mark.parametrize("escalate_to", ["local_slm", "gateway"])
def test_tier_d_rejects_non_rule_escalation(escalate_to: str) -> None:
    skill = _fixture()
    _triggers(skill)[3]["escalate_to"] = escalate_to

    with pytest.raises(SkillMetadataValidationError, match="Tier D.*rule") as exc:
        SkillYamlNormaliser.normalise(skill)

    assert exc.value.code == ORI_SDK_SKILL_VALIDATION


def test_rejects_post_action_reasoning_outside_tier_b() -> None:
    skill = _fixture()
    _triggers(skill)[0]["reasoning_policy"] = "post_action"

    with pytest.raises(SkillMetadataValidationError, match="outside Tier B"):
        SkillYamlNormaliser.normalise(skill)


def test_skill_package_tier_b_requires_policy() -> None:
    skill = _fixture()
    _triggers(skill)[1].pop("reasoning_policy")

    with pytest.raises(SkillMetadataValidationError, match="physical Tier B"):
        SkillYamlNormaliser.normalise(skill)


def test_rejects_post_action_tier_b_without_tier_a_notification() -> None:
    skill = _fixture()
    _defaults(skill)["shed_noncritical"] = ["shed_load"]

    with pytest.raises(SkillMetadataValidationError, match="Tier A default action"):
        SkillYamlNormaliser.normalise(skill)


def test_rejects_empty_tier_c_safe_default() -> None:
    skill = _fixture()
    _triggers(skill)[2]["safe_default_action"] = "  "

    with pytest.raises(SkillMetadataValidationError, match="Tier C"):
        SkillYamlNormaliser.normalise(skill)


@pytest.mark.parametrize("case", ["missing", "extra", "empty", "undeclared"])
def test_rejects_invalid_action_defaults(case: str) -> None:
    skill = _fixture()
    defaults = _defaults(skill)
    if case == "missing":
        defaults.pop("high_usage")
    elif case == "extra":
        defaults["unknown_trigger"] = ["alert_whatsapp"]
    elif case == "empty":
        defaults["high_usage"] = []
    else:
        defaults["high_usage"] = ["not_declared"]

    with pytest.raises(SkillMetadataValidationError):
        SkillYamlNormaliser.normalise(skill)


def test_rejects_duplicate_trigger_and_action_names() -> None:
    duplicate_trigger = _fixture()
    _triggers(duplicate_trigger).append(copy.deepcopy(_triggers(duplicate_trigger)[0]))

    with pytest.raises(SkillMetadataValidationError, match="duplicate trigger"):
        SkillYamlNormaliser.normalise(duplicate_trigger)

    duplicate_action = _fixture()
    available = cast(list[dict[str, object]], _actions(duplicate_action)["available"])
    available.append(copy.deepcopy(available[0]))

    with pytest.raises(SkillMetadataValidationError, match="duplicate action"):
        SkillYamlNormaliser.normalise(duplicate_action)


@pytest.mark.parametrize("name", ["bad trigger", "_leading-underscore", "bad.name"])
def test_rejects_malformed_trigger_names(name: str) -> None:
    skill = _fixture()
    _triggers(skill)[0]["name"] = name

    with pytest.raises(SkillMetadataValidationError, match="invalid name format"):
        SkillYamlNormaliser.normalise(skill)


def test_rejects_excessive_history_placeholders() -> None:
    skill = _fixture()
    prompts = cast(dict[str, str], skill["prompts"])
    prompts["high_usage"] = " ".join(
        "{history.last_value('mains')}" for _ in range(MAX_HISTORY_PLACEHOLDERS + 1)
    )

    with pytest.raises(SkillMetadataValidationError, match="maximum allowed is 16"):
        SkillYamlNormaliser.normalise(skill)


def test_unknown_top_level_fields_are_ignored_by_model_but_preserved_by_legacy_api() -> (
    None
):
    skill = _fixture()
    skill["future_extension"] = {"enabled": True}

    package = SkillYamlNormaliser.normalise(skill)
    legacy = validate_skill_metadata(skill)

    assert "future_extension" not in package.to_dict()
    assert legacy["future_extension"] == {"enabled": True}


def test_loads_yaml_and_reports_parse_failures(tmp_path: Path) -> None:
    yaml_path = tmp_path / "skill.yaml"
    yaml_path.write_text(
        """
name: yaml-skill
version: 1.0.0
author: ori
triggers:
  - name: notify
    action_tier: A
actions:
  available:
    - name: alert_sms
      tier: A
  defaults:
    notify: [alert_sms]
""".strip(),
        encoding="utf-8",
    )

    assert SkillYamlNormaliser.load_and_validate(yaml_path).name == "yaml-skill"

    yaml_path.write_text("name: [", encoding="utf-8")
    with pytest.raises(SkillMetadataValidationError, match="invalid YAML"):
        SkillYamlNormaliser.load_and_validate(yaml_path)
