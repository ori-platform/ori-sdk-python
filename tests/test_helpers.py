# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import ori_sdk
from ori_sdk.errors import ORI_SDK_CONNECTION_REFUSED, HealthClientError
from ori_sdk.helpers import (
    AlertChannelSummary,
    EvidenceSummary,
    RemoteCommandLockoutAggregate,
    RuntimePostureSummary,
    SensorFreshness,
    SensorFreshnessSummary,
    TierCapabilitySummary,
    TierExecutionState,
    alert_channel_summary,
    error_code_from_health_failure,
    evidence_summary,
    posture_interpretation,
    runtime_posture_summary,
    sensor_freshness_delta,
    staleness_summary,
    tier_capability_summary,
)
from ori_sdk.models import HealthResponse, HealthStatus

FIXTURES = Path(__file__).parent / "fixtures"
HEALTHY_FIXTURE = "runtime_health_healthy.json"


def _load_health_status(
    fixture_name: str = "runtime_health_success.json",
) -> HealthStatus:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    resp = HealthResponse.from_dict(payload)
    assert resp.health is not None
    return resp.health


def test_extended_health_helpers_are_public_exports() -> None:
    assert ori_sdk.SensorFreshness is SensorFreshness
    assert ori_sdk.SensorFreshnessSummary is SensorFreshnessSummary
    assert ori_sdk.AlertChannelSummary is AlertChannelSummary
    assert ori_sdk.TierExecutionState is TierExecutionState
    assert ori_sdk.TierCapabilitySummary is TierCapabilitySummary
    assert ori_sdk.EvidenceSummary is EvidenceSummary
    assert ori_sdk.RemoteCommandLockoutAggregate is RemoteCommandLockoutAggregate
    assert ori_sdk.RuntimePostureSummary is RuntimePostureSummary
    assert ori_sdk.sensor_freshness_delta is sensor_freshness_delta
    assert ori_sdk.alert_channel_summary is alert_channel_summary
    assert ori_sdk.tier_capability_summary is tier_capability_summary
    assert ori_sdk.evidence_summary is evidence_summary
    assert ori_sdk.runtime_posture_summary is runtime_posture_summary


def test_extended_health_helper_typed_dict_shapes() -> None:
    assert SensorFreshness.__required_keys__ == frozenset(
        {
            "sensor_id",
            "delta_ms",
            "timestamp_status",
            "runtime_stale",
            "degraded_reasons",
        }
    )
    assert SensorFreshnessSummary.__required_keys__ == frozenset(
        {"sensors", "any_degraded"}
    )
    assert AlertChannelSummary.__required_keys__ == frozenset(
        {
            "sms_runtime_available",
            "whatsapp_runtime_available",
            "internet_available",
            "outbox_backlog_count",
            "outbox_oldest_age_ms",
            "degraded",
            "degraded_reasons",
        }
    )
    assert TierExecutionState.__required_keys__ == frozenset(
        {"authority_model", "execution_ready", "degraded_reasons"}
    )
    assert TierCapabilitySummary.__required_keys__ == frozenset(
        {"tier_a", "tier_b", "tier_c", "tier_d"}
    )
    assert EvidenceSummary.__required_keys__ == frozenset(
        {
            "enabled",
            "available",
            "public_key_hex",
            "artifact_version",
            "protocol_version",
            "action_event_type",
            "chain_head_hash",
            "pending_export_count",
            "last_attested_action_id",
            "attestation_gap_count",
            "degraded",
            "degraded_reasons",
        }
    )
    assert RemoteCommandLockoutAggregate.__required_keys__ == frozenset(
        {
            "enforcement_enabled",
            "total_sender_count",
            "elevated_count",
            "critical_count",
            "locked_out_count",
            "stale_count",
            "degraded",
        }
    )
    assert RuntimePostureSummary.__required_keys__ == frozenset(
        {
            "gateway_broker_degraded",
            "state_store_encryption_degraded",
            "alert_outbox_degraded",
            "evidence_degraded",
            "remote_command_lockout",
            "degraded",
            "degraded_reasons",
        }
    )
    assert SensorFreshness.__optional_keys__ == frozenset()
    assert SensorFreshnessSummary.__optional_keys__ == frozenset()
    assert AlertChannelSummary.__optional_keys__ == frozenset()
    assert TierExecutionState.__optional_keys__ == frozenset()
    assert TierCapabilitySummary.__optional_keys__ == frozenset()
    assert EvidenceSummary.__optional_keys__ == frozenset()
    assert RemoteCommandLockoutAggregate.__optional_keys__ == frozenset()
    assert RuntimePostureSummary.__optional_keys__ == frozenset()


def test_extended_health_helpers_return_plain_json_dictionaries() -> None:
    status = _load_health_status(HEALTHY_FIXTURE)
    results = (
        sensor_freshness_delta(status, now_ms=200),
        alert_channel_summary(status),
        tier_capability_summary(status),
        evidence_summary(status),
        runtime_posture_summary(status),
    )
    for result in results:
        assert type(result) is dict
        assert json.loads(json.dumps(result)) == result


def test_extended_health_helpers_do_not_mutate_health_status() -> None:
    status = _load_health_status("runtime_health_degraded.json")
    before = status.to_dict()

    sensor_freshness_delta(status, now_ms=10_000)
    alert_channel_summary(status)
    tier_capability_summary(status)
    evidence_summary(status)
    runtime_posture_summary(status)

    assert status.to_dict() == before


def test_sensor_freshness_delta() -> None:
    healthy = sensor_freshness_delta(
        _load_health_status(HEALTHY_FIXTURE),
        now_ms=200,
    )
    assert healthy == {
        "sensors": [
            {
                "sensor_id": "mains-current",
                "delta_ms": 100,
                "timestamp_status": "observed",
                "runtime_stale": False,
                "degraded_reasons": [],
            }
        ],
        "any_degraded": False,
    }
    old_but_runtime_fresh = sensor_freshness_delta(
        _load_health_status(HEALTHY_FIXTURE),
        now_ms=10_000_000,
    )
    assert old_but_runtime_fresh["sensors"][0]["delta_ms"] == 9_999_900
    assert old_but_runtime_fresh["sensors"][0]["runtime_stale"] is False
    assert old_but_runtime_fresh["sensors"][0]["degraded_reasons"] == []
    assert old_but_runtime_fresh["any_degraded"] is False

    degraded = sensor_freshness_delta(
        _load_health_status("runtime_health_degraded.json"),
        now_ms=10_000,
    )
    sensors = {sensor["sensor_id"]: sensor for sensor in degraded["sensors"]}
    assert degraded["any_degraded"] is True
    assert sensors["stale-current"] == {
        "sensor_id": "stale-current",
        "delta_ms": 9_900,
        "timestamp_status": "observed",
        "runtime_stale": True,
        "degraded_reasons": ["runtime_stale"],
    }
    assert sensors["missing-temperature"] == {
        "sensor_id": "missing-temperature",
        "delta_ms": None,
        "timestamp_status": "missing",
        "runtime_stale": False,
        "degraded_reasons": ["sensor_disconnected", "timestamp_missing"],
    }
    assert sensors["future-voltage"] == {
        "sensor_id": "future-voltage",
        "delta_ms": -2_000,
        "timestamp_status": "future",
        "runtime_stale": False,
        "degraded_reasons": ["timestamp_in_future"],
    }


def test_alert_channel_summary() -> None:
    healthy = alert_channel_summary(_load_health_status(HEALTHY_FIXTURE))
    assert healthy == {
        "sms_runtime_available": True,
        "whatsapp_runtime_available": True,
        "internet_available": True,
        "outbox_backlog_count": 0,
        "outbox_oldest_age_ms": None,
        "degraded": False,
        "degraded_reasons": [],
    }

    degraded = alert_channel_summary(
        _load_health_status("runtime_health_degraded.json")
    )
    assert degraded == {
        "sms_runtime_available": False,
        "whatsapp_runtime_available": False,
        "internet_available": False,
        "outbox_backlog_count": 3,
        "outbox_oldest_age_ms": 9_000,
        "degraded": True,
        "degraded_reasons": [
            "sms_runtime_unavailable",
            "whatsapp_runtime_unavailable",
            "internet_unavailable",
            "alert_outbox_backlog",
        ],
    }

    healthy_status = _load_health_status(HEALTHY_FIXTURE)
    backlog_without_age = alert_channel_summary(
        replace(
            healthy_status,
            alert_outbox=replace(
                healthy_status.alert_outbox,
                backlog_count=1,
                oldest_queued_age_ms=None,
            ),
        )
    )
    assert backlog_without_age["outbox_backlog_count"] == 1
    assert backlog_without_age["outbox_oldest_age_ms"] is None
    assert backlog_without_age["degraded"] is True
    assert backlog_without_age["degraded_reasons"] == ["alert_outbox_backlog"]


def test_tier_capability_summary() -> None:
    healthy = tier_capability_summary(_load_health_status(HEALTHY_FIXTURE))
    assert healthy == {
        "tier_a": {
            "authority_model": "advisory",
            "execution_ready": True,
            "degraded_reasons": [],
        },
        "tier_b": {
            "authority_model": "runtime_policy",
            "execution_ready": None,
            "degraded_reasons": ["deployment_context_unavailable"],
        },
        "tier_c": {
            "authority_model": "operator_approval",
            "execution_ready": None,
            "degraded_reasons": ["deployment_context_unavailable"],
        },
        "tier_d": {
            "authority_model": "deterministic_safety",
            "execution_ready": None,
            "degraded_reasons": ["deployment_context_unavailable"],
        },
    }

    status = _load_health_status("runtime_health_degraded.json")
    degraded = tier_capability_summary(status)
    assert degraded["tier_b"] == {
        "authority_model": "runtime_policy",
        "execution_ready": False,
        "degraded_reasons": [
            "relay_disconnected",
            "device_policy_expired",
            "device_policy_relay_b_disabled",
        ],
    }
    assert degraded["tier_c"] == {
        "authority_model": "operator_approval",
        "execution_ready": False,
        "degraded_reasons": [
            "relay_disconnected",
            "device_policy_expired",
            "device_policy_relay_c_disabled",
        ],
    }
    assert degraded["tier_d"] == {
        "authority_model": "deterministic_safety",
        "execution_ready": False,
        "degraded_reasons": ["relay_disconnected"],
    }

    sms_without_internet = tier_capability_summary(
        replace(
            status,
            capability_posture=replace(
                status.capability_posture,
                sms_available=True,
                whatsapp_available=False,
                internet_available=False,
            ),
            alert_outbox=replace(
                status.alert_outbox,
                backlog_count=0,
                oldest_queued_age_ms=None,
            ),
        )
    )
    assert sms_without_internet["tier_a"] == {
        "authority_model": "advisory",
        "execution_ready": True,
        "degraded_reasons": [
            "whatsapp_runtime_unavailable",
            "internet_unavailable",
        ],
    }

    whatsapp_without_internet = tier_capability_summary(
        replace(
            status,
            capability_posture=replace(
                status.capability_posture,
                sms_available=False,
                whatsapp_available=True,
                internet_available=False,
            ),
            alert_outbox=replace(
                status.alert_outbox,
                backlog_count=0,
                oldest_queued_age_ms=None,
            ),
        )
    )
    assert whatsapp_without_internet["tier_a"]["execution_ready"] is False

    without_reasoners = replace(
        status,
        capability_posture=replace(
            status.capability_posture,
            relay_connected=True,
            gateway_reachable=False,
            local_slm_loaded=False,
        ),
        device_policy=replace(
            status.device_policy,
            is_expired=False,
            relay_b_enabled=True,
            relay_c_enabled=True,
        ),
    )
    reasoner_independent = tier_capability_summary(without_reasoners)
    for tier_state in (
        reasoner_independent["tier_b"],
        reasoner_independent["tier_c"],
        reasoner_independent["tier_d"],
    ):
        assert tier_state["execution_ready"] is None
        assert tier_state["degraded_reasons"] == ["deployment_context_unavailable"]

    unknown_policy = replace(
        without_reasoners,
        device_policy=replace(
            without_reasoners.device_policy,
            available=False,
            relay_b_enabled=None,
            relay_c_enabled=None,
            is_expired=None,
        ),
    )
    unknown_policy_summary = tier_capability_summary(unknown_policy)
    for tier_state in (
        unknown_policy_summary["tier_b"],
        unknown_policy_summary["tier_c"],
    ):
        assert tier_state["execution_ready"] is None
        assert tier_state["degraded_reasons"] == [
            "device_policy_unavailable",
            "deployment_context_unavailable",
        ]

    incomplete_policy = replace(
        without_reasoners,
        device_policy=replace(
            without_reasoners.device_policy,
            available=True,
            is_expired=None,
            relay_b_enabled=None,
            relay_c_enabled=None,
        ),
    )
    incomplete_policy_summary = tier_capability_summary(incomplete_policy)
    for tier_state in (
        incomplete_policy_summary["tier_b"],
        incomplete_policy_summary["tier_c"],
    ):
        assert tier_state["execution_ready"] is None
        assert tier_state["degraded_reasons"] == [
            "device_policy_state_incomplete",
            "deployment_context_unavailable",
        ]

    posture_unavailable = tier_capability_summary(
        replace(
            status,
            capability_posture=replace(
                status.capability_posture,
                available=False,
            ),
            device_policy=replace(
                status.device_policy,
                is_expired=False,
                relay_b_enabled=True,
                relay_c_enabled=True,
            ),
        )
    )
    for tier_state in (
        posture_unavailable["tier_b"],
        posture_unavailable["tier_c"],
        posture_unavailable["tier_d"],
    ):
        assert tier_state["execution_ready"] is None
        assert tier_state["degraded_reasons"] == [
            "capability_posture_unavailable",
            "deployment_context_unavailable",
        ]

    posture_unavailable_with_policy_blocks = tier_capability_summary(
        replace(
            status,
            capability_posture=replace(
                status.capability_posture,
                available=False,
            ),
            device_policy=replace(
                status.device_policy,
                available=True,
                enabled=True,
                is_expired=True,
                relay_b_enabled=False,
                relay_c_enabled=False,
            ),
        )
    )
    assert posture_unavailable_with_policy_blocks["tier_b"] == {
        "authority_model": "runtime_policy",
        "execution_ready": False,
        "degraded_reasons": [
            "capability_posture_unavailable",
            "device_policy_expired",
            "device_policy_relay_b_disabled",
        ],
    }
    assert posture_unavailable_with_policy_blocks["tier_c"] == {
        "authority_model": "operator_approval",
        "execution_ready": False,
        "degraded_reasons": [
            "capability_posture_unavailable",
            "device_policy_expired",
            "device_policy_relay_c_disabled",
        ],
    }
    assert posture_unavailable_with_policy_blocks["tier_d"] == {
        "authority_model": "deterministic_safety",
        "execution_ready": None,
        "degraded_reasons": [
            "capability_posture_unavailable",
            "deployment_context_unavailable",
        ],
    }


def test_tier_d_summary_ignores_non_authoritative_degradation() -> None:
    status = _load_health_status("runtime_health_evidence_unavailable.json")
    status = replace(
        status,
        capability_posture=replace(
            status.capability_posture,
            sms_available=False,
            whatsapp_available=False,
            gateway_reachable=False,
            local_slm_loaded=False,
            relay_connected=True,
            internet_available=False,
        ),
        alert_outbox=replace(
            status.alert_outbox,
            backlog_count=5,
            oldest_queued_age_ms=60_000,
        ),
        device_policy=replace(
            status.device_policy,
            available=True,
            enabled=True,
            relay_b_enabled=False,
            relay_c_enabled=False,
            cloud_llm_enabled=False,
            is_expired=True,
            alert_sms_monthly_cap=0,
            alert_whatsapp_monthly_cap=0,
        ),
    )

    assert tier_capability_summary(status)["tier_d"] == {
        "authority_model": "deterministic_safety",
        "execution_ready": None,
        "degraded_reasons": ["deployment_context_unavailable"],
    }


def test_evidence_summary() -> None:
    healthy = evidence_summary(_load_health_status(HEALTHY_FIXTURE))
    assert healthy == {
        "enabled": True,
        "available": True,
        "public_key_hex": "ab" * 32,
        "artifact_version": "0.2.0",
        "protocol_version": "evidence.v1",
        "action_event_type": "SAFETY_ACTION_EXECUTED",
        "chain_head_hash": "chain-head-1",
        "pending_export_count": 0,
        "last_attested_action_id": 42,
        "attestation_gap_count": 0,
        "degraded": False,
        "degraded_reasons": [],
    }

    degraded = evidence_summary(_load_health_status("runtime_health_degraded.json"))
    assert degraded == {
        "enabled": True,
        "available": True,
        "public_key_hex": "cd" * 32,
        "artifact_version": "0.2.0",
        "protocol_version": "evidence.v1",
        "action_event_type": "SAFETY_ACTION_EXECUTED",
        "chain_head_hash": "chain-head-degraded",
        "pending_export_count": 2,
        "last_attested_action_id": 41,
        "attestation_gap_count": 2,
        "degraded": True,
        "degraded_reasons": ["attestation_gaps_present"],
    }

    unavailable = evidence_summary(
        _load_health_status("runtime_health_evidence_unavailable.json")
    )
    assert unavailable == {
        "enabled": True,
        "available": False,
        "public_key_hex": "",
        "artifact_version": "",
        "protocol_version": "",
        "action_event_type": "",
        "chain_head_hash": None,
        "pending_export_count": None,
        "last_attested_action_id": None,
        "attestation_gap_count": 2,
        "degraded": True,
        "degraded_reasons": [
            "evidence_unavailable",
            "attestation_gaps_present",
        ],
    }

    status = _load_health_status(HEALTHY_FIXTURE)
    opaque_protocol = evidence_summary(
        replace(
            status,
            evidence=replace(
                status.evidence,
                protocol_version="future-evidence-contract",
            ),
        )
    )
    assert opaque_protocol["protocol_version"] == "future-evidence-contract"
    assert opaque_protocol["degraded"] is False


def test_evidence_summary_disabled_is_not_degraded() -> None:
    status = _load_health_status(HEALTHY_FIXTURE)
    disabled = replace(
        status,
        evidence=replace(
            status.evidence,
            enabled=False,
            available=False,
            public_key_hex="",
            artifact_version="",
            protocol_version="",
            action_event_type="",
            chain_head_hash=None,
            pending_export_count=None,
            last_attested_action_id=None,
        ),
    )
    summary = evidence_summary(disabled)
    assert summary["enabled"] is False
    assert summary["available"] is False
    assert summary["degraded"] is False
    assert summary["degraded_reasons"] == []


def test_runtime_posture_summary_redacts_sender_keys() -> None:
    status = _load_health_status("runtime_health_degraded.json")
    summary = runtime_posture_summary(status)
    assert summary == {
        "gateway_broker_degraded": True,
        "state_store_encryption_degraded": True,
        "alert_outbox_degraded": True,
        "evidence_degraded": True,
        "remote_command_lockout": {
            "enforcement_enabled": False,
            "total_sender_count": 2,
            "elevated_count": 1,
            "critical_count": 1,
            "locked_out_count": 1,
            "stale_count": 1,
            "degraded": True,
        },
        "degraded": True,
        "degraded_reasons": [
            "gateway_broker_posture_degraded",
            "state_store_encryption_degraded",
            "alert_outbox_degraded",
            "evidence_degraded",
            "remote_command_lockout_degraded",
        ],
    }

    serialized = json.dumps(summary, sort_keys=True)
    for sender in status.remote_command_lockout.senders:
        assert sender.channel not in serialized
        assert sender.from_number not in serialized
        assert sender.reason not in serialized
    assert "from_number" not in serialized
    assert "reason" not in summary["remote_command_lockout"]


def test_runtime_posture_summary_enforcement_disabled_is_not_degraded_alone() -> None:
    status = _load_health_status(HEALTHY_FIXTURE)
    status = replace(
        status,
        remote_command_lockout=replace(
            status.remote_command_lockout,
            enforcement_enabled=False,
            senders=[],
        ),
    )
    summary = runtime_posture_summary(status)
    assert summary["remote_command_lockout"]["enforcement_enabled"] is False
    assert summary["remote_command_lockout"]["degraded"] is False
    assert summary["degraded"] is False
    assert summary["degraded_reasons"] == []


def test_runtime_posture_summary_disabled_optional_postures_are_not_degraded() -> None:
    status = _load_health_status(HEALTHY_FIXTURE)
    status = replace(
        status,
        gateway_broker_posture=replace(
            status.gateway_broker_posture,
            gateway_enabled=False,
            requires_acl_hardening=True,
        ),
        state_store_encryption=replace(
            status.state_store_encryption,
            mode="disabled",
            satisfied=False,
        ),
        evidence=replace(
            status.evidence,
            enabled=False,
            available=False,
            public_key_hex="",
            artifact_version="",
            protocol_version="",
            action_event_type="",
            chain_head_hash=None,
            pending_export_count=None,
            last_attested_action_id=None,
        ),
        remote_command_lockout=replace(
            status.remote_command_lockout,
            enforcement_enabled=False,
            senders=[],
        ),
    )

    summary = runtime_posture_summary(status)
    assert summary["gateway_broker_degraded"] is False
    assert summary["state_store_encryption_degraded"] is False
    assert summary["evidence_degraded"] is False
    assert summary["remote_command_lockout"]["degraded"] is False
    assert summary["degraded"] is False
    assert summary["degraded_reasons"] == []


def test_staleness_summary_no_stale_sensors() -> None:
    status = _load_health_status()
    report = staleness_summary(status, now_ms=200)
    assert not report.any_stale
    assert "mains-current" in report.fresh_sensors
    assert report.stale_sensors == {}


def test_staleness_summary_with_stale_sensor() -> None:
    status = _load_health_status()
    # Patch: create a status with a stale sensor using model fields.
    stale_sensor = replace(status.sensors[0], stale=True, last_seen_ms=100)
    stale_status = replace(status, sensors=[stale_sensor])

    report = staleness_summary(stale_status, now_ms=5100)
    assert report.any_stale
    assert "mains-current" in report.stale_sensors
    assert report.stale_sensors["mains-current"] == 5000


def test_staleness_summary_stale_no_last_seen() -> None:
    status = _load_health_status()
    stale_sensor = replace(status.sensors[0], stale=True, last_seen_ms=None)
    stale_status = replace(status, sensors=[stale_sensor])

    report = staleness_summary(stale_status, now_ms=9999)
    assert report.stale_sensors["mains-current"] == -1


def test_posture_interpretation_all_available() -> None:
    status = _load_health_status()
    report = posture_interpretation(status)
    assert report.available is True
    assert "A" in report.available_tiers
    assert "D" in report.available_tiers
    # Fixture has sms_available=True → Tier B available
    assert "B" in report.available_tiers
    # Fixture has local_slm_loaded=True → Tier C available
    assert "C" in report.available_tiers
    assert "Tiers available:" in report.summary


def test_posture_interpretation_unavailable_posture() -> None:
    status = _load_health_status()
    posture = replace(status.capability_posture, available=False)
    status2 = replace(status, capability_posture=posture)
    report = posture_interpretation(status2)
    assert report.available is False
    assert report.available_tiers == []
    assert "unavailable" in report.summary.lower()


def test_posture_interpretation_compatibility() -> None:
    report = posture_interpretation(_load_health_status())
    assert report.available is True
    assert report.gateway_reachable is False
    assert report.local_slm_loaded is True
    assert report.sms_available is True
    assert report.whatsapp_available is False
    assert report.relay_connected is True
    assert report.internet_available is True
    assert report.available_tiers == ["A", "B", "C", "D"]
    assert report.summary == "Tiers available: A, B, C, D. Gateway unreachable."


def test_error_code_from_health_failure() -> None:
    exc = HealthClientError("refused", code=ORI_SDK_CONNECTION_REFUSED)
    assert error_code_from_health_failure(exc) == ORI_SDK_CONNECTION_REFUSED
