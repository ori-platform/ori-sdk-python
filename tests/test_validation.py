# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from ori_sdk.validation import (
    MAX_HISTORY_PLACEHOLDERS,
    SkillMetadataValidationError,
    validate_skill_metadata,
    validate_skill_metadata_file,
)


def _valid_skill() -> dict[str, object]:
    return {
        "name": "sample-skill",
        "version": "0.1.0",
        "author": "ori",
        "signature": "bundled",
        "triggers": [
            {
                "name": "dangerous_overcurrent",
                "condition": "value > 10",
                "action_tier": "D",
                "bypass_llm": True,
            }
        ],
        "actions": {
            "available": [{"name": "trip_relay", "tier": "D"}],
            "defaults": {"dangerous_overcurrent": ["trip_relay"]},
        },
        "prompts": {
            "dangerous_overcurrent": "Now={value}. Last={history.last_value('mains-current')}"
        },
    }


def test_validate_skill_metadata_accepts_valid_shape() -> None:
    parsed = validate_skill_metadata(_valid_skill())
    assert parsed["name"] == "sample-skill"


def test_validate_skill_metadata_rejects_bypass_llm_on_non_tier_d() -> None:
    skill = _valid_skill()
    skill["triggers"] = [
        {
            "name": "bad",
            "action_tier": "A",
            "bypass_llm": True,
        }
    ]
    skill["actions"] = {
        "available": [{"name": "alert_sms", "tier": "A"}],
        "defaults": {"bad": ["alert_sms"]},
    }
    with pytest.raises(SkillMetadataValidationError, match="bypass_llm=true"):
        validate_skill_metadata(skill)


def test_validate_skill_metadata_rejects_excessive_history_placeholders() -> None:
    skill = _valid_skill()
    placeholders = " ".join(
        "{history.last_value('mains-current')}"
        for _ in range(MAX_HISTORY_PLACEHOLDERS + 1)
    )
    skill["prompts"] = {"dangerous_overcurrent": placeholders}
    with pytest.raises(SkillMetadataValidationError, match="maximum allowed is 16"):
        validate_skill_metadata(skill)


def test_validate_skill_metadata_file_reads_yaml(tmp_path: Path) -> None:
    skill_yaml = tmp_path / "skill.yaml"
    skill_yaml.write_text(
        """
name: sample-skill
version: 0.1.0
author: ori
signature: bundled
triggers:
  - name: dangerous_overcurrent
    action_tier: D
    bypass_llm: true
actions:
  available:
    - name: trip_relay
      tier: D
  defaults:
    dangerous_overcurrent: [trip_relay]
""".strip(),
        encoding="utf-8",
    )
    parsed = validate_skill_metadata_file(skill_yaml)
    assert parsed["name"] == "sample-skill"
