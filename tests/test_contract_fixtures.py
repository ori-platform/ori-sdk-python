# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ori_sdk.models import HealthResponse

FIXTURES = Path(__file__).parent / "fixtures"


def test_runtime_health_success_fixture_round_trips() -> None:
    payload = json.loads((FIXTURES / "runtime_health_success.json").read_text())
    parsed = HealthResponse.from_dict(payload)
    assert parsed.to_dict() == payload


def test_runtime_health_error_fixture_round_trips() -> None:
    payload = json.loads((FIXTURES / "runtime_health_error.json").read_text())
    parsed = HealthResponse.from_dict(payload)
    assert parsed.to_dict() == payload
