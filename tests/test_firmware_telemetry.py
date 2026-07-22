# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Cross-language contract tests for firmware telemetry Layer 1.

The committed vectors are published by ori-edge-firmware. Their source commit
and whole-file hash are pinned below; canonical-byte or signature divergence is
a cross-repository contract break, not an SDK-local serialization choice.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Literal, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import ori_sdk
from ori_sdk.firmware_telemetry import (
    FIRMWARE_DEVICE_ID_MAX_LENGTH,
    FIRMWARE_FAULT_TOKEN_MAX_LENGTH,
    FIRMWARE_JSON_SAFE_INT_MAX,
    FIRMWARE_SIGNATURE_PREFIX,
    FirmwareAction,
    FirmwareActionAuthority,
    FirmwareCapabilityManifest,
    FirmwareCommandRejectionDetail,
    FirmwareFaultCode,
    FirmwareFaultEvent,
    FirmwareFreshnessState,
    FirmwareFreshnessVerdict,
    FirmwareHeartbeatEnvelope,
    FirmwareManifestAction,
    FirmwareManifestChannel,
    FirmwareManifestInterlock,
    FirmwareProvisioningAnchor,
    FirmwareTelemetryEnvelope,
    FirmwareTelemetryError,
    FirmwareTelemetryReading,
    FirmwareUnsignedPayload,
    SignedFirmwareCapabilityManifest,
    SignedFirmwareFaultEvent,
    SignedFirmwareHeartbeat,
    SignedFirmwareTelemetry,
    canonical_firmware_json_bytes,
    evaluate_firmware_freshness,
    firmware_manifest_hash,
    parse_signed_firmware_telemetry,
    verify_firmware_fault_event,
    verify_firmware_heartbeat,
    verify_firmware_manifest,
    verify_firmware_signature,
    verify_firmware_telemetry,
)

FIXTURES = Path(__file__).parent / "fixtures"
LAYER1_PATH = FIXTURES / "firmware_layer1_vectors.json"
FAULT_PATH = FIXTURES / "firmware_fault_vectors.json"
FIRMWARE_LAYER1_SOURCE = (
    "ori-platform/ori-edge-firmware@"
    "66b6fd2f8fa5c3dca2a3da5977c7b050ca5e0b5b:"
    "test/golden/layer1_vectors.json"
)
FIRMWARE_LAYER1_SHA256 = (
    "72e5ed34bd70eee82ad0e9982adf0ff3729e8b9b291cb3d5ab3b16da82ca2359"
)


def _load_object(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


LAYER1 = _load_object(LAYER1_PATH)
FAULTS = _load_object(FAULT_PATH)
PUBLIC_KEY_B64 = cast(str, LAYER1["public_key_b64"])
LAYER1_CASES = {
    cast(str, case["name"]): case
    for case in cast(list[dict[str, object]], LAYER1["cases"])
}
FAULT_CASES = {
    cast(str, case["name"]): case
    for case in cast(list[dict[str, object]], FAULTS["cases"])
}


def _case_input(case: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], case["input"])


def _wire_signature(case: dict[str, object]) -> str:
    return FIRMWARE_SIGNATURE_PREFIX + cast(str, case["signature_b64"])


def _manifest(case_name: str) -> FirmwareCapabilityManifest:
    return FirmwareCapabilityManifest.from_dict(_case_input(LAYER1_CASES[case_name]))


def _signed_manifest(case_name: str) -> SignedFirmwareCapabilityManifest:
    case = LAYER1_CASES[case_name]
    return SignedFirmwareCapabilityManifest.from_dict(
        {
            "manifest": copy.deepcopy(_case_input(case)),
            "manifest_hash": cast(str, case["manifest_hash"]),
            "signature": _wire_signature(case),
        }
    )


def _anchor(case_name: str) -> FirmwareProvisioningAnchor:
    manifest = _manifest(case_name)
    return FirmwareProvisioningAnchor(
        device_id=manifest.device_id,
        public_key_b64=manifest.public_key_b64,
        initial_manifest_hash=firmware_manifest_hash(manifest),
        posture=manifest.posture,
        provisioned_at_ms=0,
    )


def _signed_telemetry(
    case_name: str,
) -> SignedFirmwareTelemetry | SignedFirmwareHeartbeat:
    case = LAYER1_CASES[case_name]
    return parse_signed_firmware_telemetry(
        {
            "envelope": copy.deepcopy(_case_input(case)),
            "signature": _wire_signature(case),
        }
    )


def _signed_fault(case_name: str) -> SignedFirmwareFaultEvent:
    case = FAULT_CASES[case_name]
    return SignedFirmwareFaultEvent.from_dict(
        {
            "fault": copy.deepcopy(_case_input(case)),
            "signature": _wire_signature(case),
        }
    )


def _sign(payload: FirmwareUnsignedPayload) -> str:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes([0x42]) * 32)
    signature = private_key.sign(canonical_firmware_json_bytes(payload))
    return FIRMWARE_SIGNATURE_PREFIX + base64.b64encode(signature).decode("ascii")


def _resign_telemetry(envelope: FirmwareTelemetryEnvelope) -> SignedFirmwareTelemetry:
    return SignedFirmwareTelemetry(envelope=envelope, signature=_sign(envelope))


def test_firmware_telemetry_api_is_publicly_exported() -> None:
    expected = {
        "FirmwareAction",
        "FirmwareActionAuthority",
        "FirmwareCapabilityManifest",
        "FirmwareCommandRejectionDetail",
        "FirmwareFaultEvent",
        "FirmwareFreshnessState",
        "FirmwareFreshnessVerdict",
        "FirmwareHeartbeatEnvelope",
        "FirmwareManifestAction",
        "FirmwareManifestChannel",
        "FirmwareManifestInterlock",
        "FirmwareProvisioningAnchor",
        "FirmwareTelemetryEnvelope",
        "FirmwareTelemetryError",
        "FirmwareTelemetryReading",
        "SignedFirmwareCapabilityManifest",
        "SignedFirmwareFaultEvent",
        "SignedFirmwareHeartbeat",
        "SignedFirmwareTelemetry",
        "canonical_firmware_json_bytes",
        "evaluate_firmware_freshness",
        "firmware_manifest_hash",
        "parse_signed_firmware_telemetry",
        "verify_firmware_fault_event",
        "verify_firmware_heartbeat",
        "verify_firmware_manifest",
        "verify_firmware_signature",
        "verify_firmware_telemetry",
    }
    assert expected <= set(ori_sdk.__all__)
    assert ori_sdk.FirmwareCapabilityManifest is FirmwareCapabilityManifest
    assert ori_sdk.verify_firmware_telemetry is verify_firmware_telemetry


def test_layer1_fixture_is_byte_identical_to_pinned_firmware_source() -> None:
    actual_sha256 = hashlib.sha256(LAYER1_PATH.read_bytes()).hexdigest()

    assert actual_sha256 == FIRMWARE_LAYER1_SHA256, (
        f"Layer 1 fixture drifted from {FIRMWARE_LAYER1_SOURCE}"
    )


@pytest.mark.parametrize("case_name", list(LAYER1_CASES))
def test_layer1_golden_canonical_bytes_hash_and_signature(case_name: str) -> None:
    case = LAYER1_CASES[case_name]
    payload = _case_input(case)
    if case["kind"] == "manifest":
        model: FirmwareUnsignedPayload = FirmwareCapabilityManifest.from_dict(payload)
    elif cast(list[object], payload["readings"]):
        model = FirmwareTelemetryEnvelope.from_dict(payload)
    else:
        model = FirmwareHeartbeatEnvelope.from_dict(payload)

    canonical = canonical_firmware_json_bytes(model)

    assert canonical.hex() == case["canonical_hex"]
    assert hashlib.sha256(canonical).hexdigest() == case["canonical_sha256_hex"]
    assert model.to_dict() == payload
    verify_firmware_signature(model, _wire_signature(case), PUBLIC_KEY_B64)


@pytest.mark.parametrize("case_name", list(FAULT_CASES))
def test_fault_golden_canonical_bytes_hash_and_signature(case_name: str) -> None:
    case = FAULT_CASES[case_name]
    model = FirmwareFaultEvent.from_dict(_case_input(case))
    canonical = canonical_firmware_json_bytes(model)

    assert canonical.hex() == case["canonical_hex"]
    assert hashlib.sha256(canonical).hexdigest() == case["canonical_sha256_hex"]
    assert model.to_dict() == _case_input(case)
    verify_firmware_signature(model, _wire_signature(case), PUBLIC_KEY_B64)


@pytest.mark.parametrize(
    "case_name",
    ["manifest_minimal_dev", "manifest_full_sealed", "manifest_command_bench"],
)
def test_signed_manifest_round_trip_and_anchor_verification(case_name: str) -> None:
    message = _signed_manifest(case_name)

    assert message.to_dict()["manifest"] == _case_input(LAYER1_CASES[case_name])
    assert verify_firmware_manifest(message, _anchor(case_name)) == (
        message.manifest_hash
    )


def test_manifest_update_requires_an_explicit_accepted_hash() -> None:
    anchor = _anchor("manifest_full_sealed")
    updated = _signed_manifest("manifest_command_bench")

    with pytest.raises(FirmwareTelemetryError) as unapproved:
        verify_firmware_manifest(updated, anchor)

    assert unapproved.value.code == "capability_hash_mismatch"
    assert (
        verify_firmware_manifest(
            updated,
            anchor,
            expected_manifest_hash=updated.manifest_hash,
        )
        == updated.manifest_hash
    )


def test_parser_returns_distinct_measurement_and_heartbeat_types() -> None:
    measurement = _signed_telemetry("telemetry_single_reading")
    heartbeat = _signed_telemetry("telemetry_heartbeat_zero_readings")

    assert isinstance(measurement, SignedFirmwareTelemetry)
    assert isinstance(measurement.envelope, FirmwareTelemetryEnvelope)
    assert isinstance(heartbeat, SignedFirmwareHeartbeat)
    assert isinstance(heartbeat.envelope, FirmwareHeartbeatEnvelope)
    assert heartbeat.to_dict()["envelope"] == _case_input(
        LAYER1_CASES["telemetry_heartbeat_zero_readings"]
    )
    assert "readings" not in heartbeat.envelope.__slots__


def test_measurement_and_heartbeat_verification_return_next_state() -> None:
    manifest = _manifest("manifest_full_sealed")
    anchor = _anchor("manifest_full_sealed")
    measurement = _signed_telemetry("telemetry_single_reading")
    heartbeat = _signed_telemetry("telemetry_heartbeat_zero_readings")
    assert isinstance(measurement, SignedFirmwareTelemetry)
    assert isinstance(heartbeat, SignedFirmwareHeartbeat)

    first = verify_firmware_telemetry(
        measurement, anchor=anchor, accepted_manifest=manifest
    )
    second = verify_firmware_heartbeat(
        heartbeat,
        anchor=anchor,
        accepted_manifest=manifest,
        previous_state=first,
    )

    assert first.seq == measurement.envelope.seq
    assert second.seq == heartbeat.envelope.seq
    assert second.device_id == anchor.device_id


@pytest.mark.parametrize("case_name", list(FAULT_CASES))
def test_every_fault_vector_verifies_as_fault_evidence(case_name: str) -> None:
    message = _signed_fault(case_name)
    manifest_name = (
        "manifest_minimal_dev"
        if message.fault.posture == "development"
        else "manifest_full_sealed"
    )

    state = verify_firmware_fault_event(
        message,
        anchor=_anchor(manifest_name),
        accepted_manifest=_manifest(manifest_name),
    )

    assert state.seq == message.fault.seq
    assert "readings" not in message.fault.to_dict()
    assert "action_tier" not in message.fault.to_dict()


def test_fault_vectors_cover_closed_vocabulary_and_bounds() -> None:
    covered = {cast(str, _case_input(case)["code"]) for case in FAULT_CASES.values()}
    assert covered == {
        "brownout_relay_fault",
        "command_rejected",
        "ingress_degraded",
        "interlock_input_fault",
        "interlock_recovered",
        "interlock_tripped",
        "sensor_fault",
    }
    maximum = _signed_fault("fault_max_bounds").fault
    assert len(maximum.subject) == FIRMWARE_FAULT_TOKEN_MAX_LENGTH
    assert len(maximum.detail) == FIRMWARE_FAULT_TOKEN_MAX_LENGTH


@pytest.mark.parametrize(
    "signature",
    [
        "not-prefixed",
        "ecdsa:" + ("A" * 88),
        "ed25519:not-base64!",
        "ed25519:" + base64.b64encode(bytes(63)).decode("ascii"),
    ],
)
def test_malformed_signature_is_rejected(signature: str) -> None:
    envelope = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    ).envelope

    with pytest.raises(FirmwareTelemetryError) as excinfo:
        verify_firmware_signature(envelope, signature, PUBLIC_KEY_B64)

    assert excinfo.value.code == "invalid_signature_format"


def test_wrong_public_key_and_tampered_payload_are_rejected() -> None:
    message = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )
    other_key = base64.b64encode(bytes(32)).decode("ascii")
    tampered = replace(
        message.envelope,
        readings=(replace(message.envelope.readings[0], value=9.21),),
    )

    with pytest.raises(FirmwareTelemetryError) as wrong_key:
        verify_firmware_signature(message.envelope, message.signature, other_key)
    with pytest.raises(FirmwareTelemetryError) as changed_payload:
        verify_firmware_signature(tampered, message.signature, PUBLIC_KEY_B64)

    assert wrong_key.value.code == "signature_verification_failed"
    assert changed_payload.value.code == "signature_verification_failed"


def test_bad_manifest_hash_is_rejected_by_parser_and_constructor() -> None:
    message = _signed_manifest("manifest_full_sealed")
    payload = message.to_dict()
    payload["manifest_hash"] = "sha256:" + ("0" * 64)

    with pytest.raises(FirmwareTelemetryError) as parsed:
        SignedFirmwareCapabilityManifest.from_dict(payload)
    with pytest.raises(FirmwareTelemetryError) as constructed:
        replace(message, manifest_hash="sha256:" + ("0" * 64))

    assert parsed.value.code == "capability_hash_mismatch"
    assert constructed.value.code == "capability_hash_mismatch"


def test_payload_capability_drift_is_rejected() -> None:
    message = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )

    with pytest.raises(FirmwareTelemetryError) as excinfo:
        verify_firmware_telemetry(
            message,
            anchor=_anchor("manifest_full_sealed"),
            accepted_manifest=_manifest("manifest_command_bench"),
        )

    assert excinfo.value.code == "capability_hash_mismatch"


def test_replay_and_boot_rollback_verdicts_fail_closed() -> None:
    message = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )
    envelope = message.envelope

    replay = evaluate_firmware_freshness(
        envelope,
        FirmwareFreshnessState(
            device_id=envelope.device_id,
            boot_id=envelope.boot_id,
            seq=envelope.seq,
            device_uptime_ms=envelope.device_uptime_ms,
        ),
    )
    rollback = evaluate_firmware_freshness(
        envelope,
        FirmwareFreshnessState(
            device_id=envelope.device_id,
            boot_id=envelope.boot_id + 1,
            seq=envelope.seq - 1,
            device_uptime_ms=0,
        ),
    )

    assert not replay.accepted and replay.error_code == "sequence_replay"
    assert replay.next_state is None
    assert not rollback.accepted and rollback.error_code == "boot_rollback"


def test_verifier_rejects_replay_after_signature_verification() -> None:
    message = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )
    state = FirmwareFreshnessState(
        device_id=message.envelope.device_id,
        boot_id=message.envelope.boot_id,
        seq=message.envelope.seq,
        device_uptime_ms=message.envelope.device_uptime_ms,
    )

    with pytest.raises(FirmwareTelemetryError) as excinfo:
        verify_firmware_telemetry(
            message,
            anchor=_anchor("manifest_full_sealed"),
            accepted_manifest=_manifest("manifest_full_sealed"),
            previous_state=state,
        )

    assert excinfo.value.code == "sequence_replay"


def test_verifier_rejects_boot_rollback_after_signature_verification() -> None:
    message = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )
    state = FirmwareFreshnessState(
        device_id=message.envelope.device_id,
        boot_id=message.envelope.boot_id + 1,
        seq=message.envelope.seq - 1,
        device_uptime_ms=0,
    )

    with pytest.raises(FirmwareTelemetryError) as excinfo:
        verify_firmware_telemetry(
            message,
            anchor=_anchor("manifest_full_sealed"),
            accepted_manifest=_manifest("manifest_full_sealed"),
            previous_state=state,
        )

    assert excinfo.value.code == "boot_rollback"


def test_uptime_may_reset_only_when_boot_increases() -> None:
    message = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )
    envelope = message.envelope
    previous = FirmwareFreshnessState(
        device_id=envelope.device_id,
        boot_id=envelope.boot_id,
        seq=envelope.seq - 1,
        device_uptime_ms=envelope.device_uptime_ms + 1,
    )
    same_boot = evaluate_firmware_freshness(envelope, previous)
    next_boot = replace(
        envelope,
        boot_id=envelope.boot_id + 1,
        seq=envelope.seq + 1,
        device_uptime_ms=0,
    )

    assert not same_boot.accepted
    assert same_boot.error_code == "invalid_envelope"
    assert evaluate_firmware_freshness(next_boot, previous).accepted


def test_freshness_state_is_bound_to_device() -> None:
    envelope = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    ).envelope
    verdict = evaluate_firmware_freshness(
        envelope,
        FirmwareFreshnessState(
            device_id="another-device",
            boot_id=0,
            seq=0,
            device_uptime_ms=0,
        ),
    )

    assert not verdict.accepted
    assert verdict.error_code == "invalid_envelope"


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), 1e-5, -1e-5, 1e16],
)
def test_reading_rejects_noncanonical_values(value: float) -> None:
    with pytest.raises(FirmwareTelemetryError) as excinfo:
        FirmwareTelemetryReading(
            channel="ch0",
            sensor_type="current",
            unit="ampere",
            value=value,
            quality=1.0,
        )

    assert excinfo.value.code == "invalid_reading"


@pytest.mark.parametrize("quality", [-0.01, 1.01, True])
def test_reading_rejects_invalid_quality(quality: object) -> None:
    with pytest.raises(FirmwareTelemetryError) as excinfo:
        FirmwareTelemetryReading(
            channel="ch0",
            sensor_type="current",
            unit="ampere",
            value=1.0,
            quality=cast(int | float, quality),
        )

    assert excinfo.value.code == "invalid_reading"


def test_reading_rejects_missing_and_additional_fields() -> None:
    reading = _manifest("manifest_full_sealed").channels[0]
    payload: dict[str, object] = {
        "channel": reading.channel,
        "sensor_type": reading.sensor_type,
        "unit": reading.unit,
        "value": 8.2,
        "quality": 1.0,
        "note": "not-v1",
    }

    with pytest.raises(FirmwareTelemetryError) as extra:
        FirmwareTelemetryReading.from_dict(payload)
    del payload["note"]
    del payload["unit"]
    with pytest.raises(FirmwareTelemetryError) as missing:
        FirmwareTelemetryReading.from_dict(payload)

    assert extra.value.code == "invalid_reading"
    assert missing.value.code == "invalid_reading"


def test_high_level_verifier_checks_manifest_channel_and_quality_floor() -> None:
    original = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    ).envelope
    mismatched = replace(
        original,
        readings=(replace(original.readings[0], sensor_type="voltage"),),
    )
    low_quality = replace(
        original,
        readings=(replace(original.readings[0], quality=0.5),),
    )
    anchor = _anchor("manifest_full_sealed")
    manifest = _manifest("manifest_full_sealed")

    with pytest.raises(FirmwareTelemetryError) as wrong_type:
        verify_firmware_telemetry(
            _resign_telemetry(mismatched),
            anchor=anchor,
            accepted_manifest=manifest,
        )
    with pytest.raises(FirmwareTelemetryError) as below_floor:
        verify_firmware_telemetry(
            _resign_telemetry(low_quality),
            anchor=anchor,
            accepted_manifest=manifest,
        )

    assert wrong_type.value.code == "invalid_reading"
    assert below_floor.value.code == "invalid_reading"


def test_golden_unicode_channel_signature_verifies_but_manifest_gate_rejects_it() -> (
    None
):
    message = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_unicode_channel")
    )
    verify_firmware_signature(message.envelope, message.signature, PUBLIC_KEY_B64)

    with pytest.raises(FirmwareTelemetryError) as excinfo:
        verify_firmware_telemetry(
            message,
            anchor=_anchor("manifest_minimal_dev"),
            accepted_manifest=_manifest("manifest_minimal_dev"),
        )

    assert excinfo.value.code == "unsupported_channel"


def test_direct_constructors_cannot_blur_heartbeat_and_measurement() -> None:
    heartbeat = cast(
        SignedFirmwareHeartbeat,
        _signed_telemetry("telemetry_heartbeat_zero_readings"),
    )
    fields = heartbeat.envelope

    with pytest.raises(FirmwareTelemetryError, match="at least one reading"):
        FirmwareTelemetryEnvelope(
            v=fields.v,
            alg=fields.alg,
            device_id=fields.device_id,
            boot_id=fields.boot_id,
            seq=fields.seq,
            capability_hash=fields.capability_hash,
            posture=fields.posture,
            device_uptime_ms=fields.device_uptime_ms,
            emitted_at_ms=fields.emitted_at_ms,
            readings=(),
        )
    measurement = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )
    with pytest.raises(FirmwareTelemetryError, match="heartbeat readings"):
        FirmwareHeartbeatEnvelope.from_dict(measurement.envelope.to_dict())


def test_manifest_action_authority_cannot_claim_runtime_tiers() -> None:
    with pytest.raises(FirmwareTelemetryError):
        FirmwareManifestAction(
            action="relay_open",
            channel="relay0",
            authority=cast(FirmwareActionAuthority, "tier_d"),
        )

    payload = _signed_manifest("manifest_full_sealed").to_dict()
    manifest = cast(dict[str, object], payload["manifest"])
    actions = cast(list[dict[str, object]], manifest["actions"])
    actions[0]["authority"] = "tier_c"
    with pytest.raises(FirmwareTelemetryError):
        SignedFirmwareCapabilityManifest.from_dict(payload)


@pytest.mark.parametrize("action", ["relay_open", "relay_close"])
def test_manifest_action_vocabulary_accepts_both_actions(
    action: FirmwareAction,
) -> None:
    capability = FirmwareManifestAction(
        action=action,
        channel="relay0",
        authority="runtime_commanded",
    )
    interlock = FirmwareManifestInterlock(
        name="local_overcurrent_interlock",
        channel="ch0",
        action=action,
    )

    assert capability.action == action
    assert interlock.action == action


@pytest.mark.parametrize("action", ["", "relay_toggle", "tier_d_cutoff"])
def test_manifest_action_vocabulary_is_closed_for_constructors_and_parsers(
    action: str,
) -> None:
    with pytest.raises(FirmwareTelemetryError, match="firmware action"):
        FirmwareManifestAction(
            action=cast(FirmwareAction, action),
            channel="relay0",
            authority="runtime_commanded",
        )
    with pytest.raises(FirmwareTelemetryError, match="firmware action"):
        FirmwareManifestInterlock(
            name="local_overcurrent_interlock",
            channel="ch0",
            action=cast(FirmwareAction, action),
        )

    capability_payload = _manifest("manifest_full_sealed").to_dict()
    capabilities = cast(list[dict[str, object]], capability_payload["actions"])
    capabilities[0]["action"] = action
    with pytest.raises(FirmwareTelemetryError, match="firmware action"):
        FirmwareCapabilityManifest.from_dict(capability_payload)

    interlock_payload = _manifest("manifest_full_sealed").to_dict()
    interlocks = cast(list[dict[str, object]], interlock_payload["interlocks"])
    interlocks[0]["action"] = action
    with pytest.raises(FirmwareTelemetryError, match="firmware action"):
        FirmwareCapabilityManifest.from_dict(interlock_payload)


def test_production_posture_requires_security_booleans() -> None:
    manifest = _manifest("manifest_full_sealed")

    with pytest.raises(FirmwareTelemetryError) as secure_boot:
        replace(manifest, secure_boot_enabled=False)
    with pytest.raises(FirmwareTelemetryError) as flash_encryption:
        replace(manifest, flash_encryption_enabled=False)

    assert secure_boot.value.code == "invalid_posture"
    assert flash_encryption.value.code == "invalid_posture"


def test_manifest_rejects_duplicate_channels() -> None:
    manifest = _manifest("manifest_full_sealed")

    with pytest.raises(FirmwareTelemetryError) as excinfo:
        replace(manifest, channels=(manifest.channels[0], manifest.channels[0]))

    assert excinfo.value.code == "unsupported_channel"


@pytest.mark.parametrize(
    "device_id",
    ["", "bad/device", "bad device", "é", "x" * (FIRMWARE_DEVICE_ID_MAX_LENGTH + 1)],
)
def test_device_id_contract_is_enforced(device_id: str) -> None:
    anchor = _anchor("manifest_full_sealed")

    with pytest.raises(FirmwareTelemetryError):
        replace(anchor, device_id=device_id)

    assert replace(anchor, device_id="x" * FIRMWARE_DEVICE_ID_MAX_LENGTH).device_id == (
        "x" * FIRMWARE_DEVICE_ID_MAX_LENGTH
    )


def test_public_key_must_be_canonical_standard_base64() -> None:
    anchor = _anchor("manifest_full_sealed")

    urlsafe_key = base64.urlsafe_b64encode(base64.b64decode(PUBLIC_KEY_B64)).decode()
    assert urlsafe_key != PUBLIC_KEY_B64
    for value in ["", "not-base64", urlsafe_key]:
        with pytest.raises(FirmwareTelemetryError) as excinfo:
            replace(anchor, public_key_b64=value)
        assert excinfo.value.code == "public_key_mismatch"


@pytest.mark.parametrize("field_name", ["subject", "detail"])
@pytest.mark.parametrize("value", ["bad/token", "bad token", "réf", "x" * 64])
def test_fault_tokens_enforce_fleet_alphabet_and_bound(
    field_name: str, value: str
) -> None:
    fault = _signed_fault("fault_command_rejected").fault

    with pytest.raises(FirmwareTelemetryError):
        if field_name == "subject":
            replace(fault, subject=value)
        else:
            replace(fault, detail=value)


def test_fault_code_is_closed_for_parser_and_constructor() -> None:
    fault = _signed_fault("fault_command_rejected").fault
    payload = fault.to_dict()
    payload["code"] = "made_up_fault"

    with pytest.raises(FirmwareTelemetryError):
        FirmwareFaultEvent.from_dict(payload)
    with pytest.raises(FirmwareTelemetryError):
        replace(fault, code=cast(FirmwareFaultCode, "made_up_fault"))


@pytest.mark.parametrize(
    "detail",
    [
        "malformed",
        "wrong_device",
        "bad_signature",
        "replayed",
        "capability_mismatch",
        "unknown_action",
        "storage_failure",
    ],
)
def test_command_rejection_accepts_every_contract_verdict(
    detail: FirmwareCommandRejectionDetail,
) -> None:
    fault = _signed_fault("fault_command_rejected").fault

    assert replace(fault, detail=detail).detail == detail
    payload = fault.to_dict()
    payload["detail"] = detail
    assert FirmwareFaultEvent.from_dict(payload).detail == detail


@pytest.mark.parametrize("detail", ["", "invented_verdict"])
def test_command_rejection_detail_is_closed_for_constructor_and_parser(
    detail: str,
) -> None:
    fault = _signed_fault("fault_command_rejected").fault

    with pytest.raises(FirmwareTelemetryError, match="command rejection detail"):
        replace(fault, detail=detail)
    payload = fault.to_dict()
    payload["detail"] = detail
    with pytest.raises(FirmwareTelemetryError, match="command rejection detail"):
        FirmwareFaultEvent.from_dict(payload)


@pytest.mark.parametrize("detail", ["", "vendor_defined_detail"])
def test_non_command_fault_detail_remains_open_and_may_be_empty(
    detail: str,
) -> None:
    fault = _signed_fault("fault_command_rejected").fault
    sensor_fault = replace(fault, code="sensor_fault", detail=detail)

    assert sensor_fault.detail == detail
    assert FirmwareFaultEvent.from_dict(sensor_fault.to_dict()) == sensor_fault


def test_models_are_frozen_and_nested_collections_are_tuples() -> None:
    manifest = _manifest("manifest_full_sealed")
    telemetry = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )

    with pytest.raises(FrozenInstanceError):
        manifest.device_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        telemetry.envelope.seq = 1  # type: ignore[misc]
    assert isinstance(manifest.channels, tuple)
    assert isinstance(manifest.actions, tuple)
    assert isinstance(telemetry.envelope.readings, tuple)


def test_model_constructors_reject_mutable_nested_sequences() -> None:
    manifest = _manifest("manifest_full_sealed")

    with pytest.raises(FirmwareTelemetryError, match="channels"):
        replace(
            manifest,
            channels=cast(tuple[FirmwareManifestChannel, ...], [manifest.channels[0]]),
        )
    telemetry = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    ).envelope
    with pytest.raises(FirmwareTelemetryError, match="readings"):
        replace(
            telemetry,
            readings=cast(
                tuple[FirmwareTelemetryReading, ...], [telemetry.readings[0]]
            ),
        )


def test_counters_and_numeric_boundaries() -> None:
    maximum = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_max_counters")
    ).envelope
    edge = replace(
        maximum,
        readings=(replace(maximum.readings[0], value=-0.0, quality=0.0),),
    )

    assert maximum.seq == FIRMWARE_JSON_SAFE_INT_MAX
    assert b'"value":-0.0' in canonical_firmware_json_bytes(edge)
    with pytest.raises(FirmwareTelemetryError):
        replace(maximum, seq=FIRMWARE_JSON_SAFE_INT_MAX + 1)


def test_unknown_wire_fields_are_rejected() -> None:
    payload = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    ).to_dict()
    payload["transport"] = "mqtt"

    with pytest.raises(FirmwareTelemetryError, match="unexpected 'transport'"):
        parse_signed_firmware_telemetry(payload)


def test_version_requires_an_integer_for_parser_and_constructor() -> None:
    message = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )
    payload = message.to_dict()
    envelope = cast(dict[str, object], payload["envelope"])
    envelope["v"] = 1.0

    with pytest.raises(FirmwareTelemetryError, match="envelope.v"):
        parse_signed_firmware_telemetry(payload)
    with pytest.raises(FirmwareTelemetryError, match="envelope.v"):
        replace(message.envelope, v=cast(Literal[1], 1.0))


def test_signature_algorithm_is_fixed_for_parser_and_constructor() -> None:
    message = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    )
    payload = message.to_dict()
    envelope = cast(dict[str, object], payload["envelope"])
    envelope["alg"] = "ecdsa-p256"

    with pytest.raises(FirmwareTelemetryError) as parsed:
        parse_signed_firmware_telemetry(payload)
    with pytest.raises(FirmwareTelemetryError) as constructed:
        replace(message.envelope, alg=cast(Literal["ed25519"], "ecdsa-p256"))

    assert parsed.value.code == "unsupported_alg"
    assert constructed.value.code == "unsupported_alg"


def test_wire_parser_rejects_non_string_object_keys() -> None:
    payload = cast(
        SignedFirmwareTelemetry, _signed_telemetry("telemetry_single_reading")
    ).to_dict()
    malformed = cast(dict[str, object], payload["envelope"])
    malformed[cast(str, 1)] = "not-a-json-object-key"

    with pytest.raises(FirmwareTelemetryError, match="keys must be strings"):
        parse_signed_firmware_telemetry(payload)


def test_canonical_helper_accepts_only_validated_models() -> None:
    with pytest.raises(TypeError, match="unsigned model"):
        canonical_firmware_json_bytes({"value": 1.0})  # type: ignore[arg-type]


def test_freshness_verdict_constructor_enforces_consistent_outcomes() -> None:
    state = FirmwareFreshnessState(
        device_id="device-01", boot_id=1, seq=1, device_uptime_ms=1
    )

    with pytest.raises(ValueError, match="requires next_state"):
        FirmwareFreshnessVerdict(accepted=True, next_state=None)
    with pytest.raises(ValueError, match="cannot advance"):
        FirmwareFreshnessVerdict(
            accepted=False,
            next_state=state,
            error_code="sequence_replay",
        )
    with pytest.raises(ValueError, match="freshness error code"):
        FirmwareFreshnessVerdict(
            accepted=False,
            next_state=None,
            error_code="unknown_device",
        )
