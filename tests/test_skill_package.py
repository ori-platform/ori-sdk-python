# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from ori_sdk import ActionsSection, SkillPackage, SkillYamlNormaliser
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
    defaults = {"high_usage": ("alert_whatsapp",)}

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


def test_rejects_cloud_as_an_escalation_tier() -> None:
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
    _triggers(skill)[3]["bypass_llm"] = False

    package = SkillYamlNormaliser.normalise(skill)

    assert package.triggers[3].bypass_llm is True


def test_rejects_post_action_reasoning_outside_tier_b() -> None:
    skill = _fixture()
    _triggers(skill)[0]["reasoning_policy"] = "post_action"

    with pytest.raises(SkillMetadataValidationError, match="outside Tier B"):
        SkillYamlNormaliser.normalise(skill)


def test_rejects_physical_tier_b_without_approval_or_post_action() -> None:
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
