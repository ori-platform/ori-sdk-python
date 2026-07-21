# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Literal, cast

import pytest

import ori_sdk
from ori_sdk.telemetry import (
    JSON_SAFE_INT_MAX,
    RUNTIME_TELEMETRY_SCHEMA_VERSION,
    RuntimeTelemetryBatch,
    RuntimeTelemetryEvent,
    RuntimeTelemetryEventType,
    RuntimeTelemetryReading,
    TelemetryJsonObject,
    canonical_telemetry_bytes,
    telemetry_hmac_sha256,
)

FIXTURE = Path(__file__).parent / "fixtures" / "runtime_telemetry_golden.json"
GOLDEN_DIGEST = "51e7a268d28c96f7ba516593b7d4ca160848ff641888ce1b3b513f2bbf2370ea"
GOLDEN_HMAC = "5ed66b6fc38a5d68e8c0c16bf18ade62968549432fb52baeb8b56625927dba79"


def _payload() -> dict[str, object]:
    payload: object = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def _batch() -> RuntimeTelemetryBatch:
    return RuntimeTelemetryBatch.from_dict(_payload())


def test_runtime_telemetry_models_are_public_exports() -> None:
    assert ori_sdk.RuntimeTelemetryReading is RuntimeTelemetryReading
    assert ori_sdk.RuntimeTelemetryEvent is RuntimeTelemetryEvent
    assert ori_sdk.RuntimeTelemetryBatch is RuntimeTelemetryBatch
    assert ori_sdk.RUNTIME_TELEMETRY_SCHEMA_VERSION == (
        RUNTIME_TELEMETRY_SCHEMA_VERSION
    )
    assert ori_sdk.JSON_SAFE_INT_MAX == JSON_SAFE_INT_MAX
    assert ori_sdk.canonical_telemetry_bytes is canonical_telemetry_bytes
    assert ori_sdk.telemetry_hmac_sha256 is telemetry_hmac_sha256
    assert {
        "RuntimeTelemetryReading",
        "RuntimeTelemetryEvent",
        "RuntimeTelemetryBatch",
        "RuntimeTelemetryEventType",
        "JSON_SAFE_INT_MAX",
        "RUNTIME_TELEMETRY_SCHEMA_VERSION",
        "TelemetryCanonicalizationError",
        "TelemetryJsonObject",
        "TelemetryJsonScalar",
        "TelemetryJsonValue",
        "canonical_telemetry_bytes",
        "telemetry_hmac_sha256",
    } <= set(ori_sdk.__all__)


def test_runtime_telemetry_golden_body_digest_and_hmac() -> None:
    batch = _batch()
    expected_body = FIXTURE.read_bytes().rstrip(b"\n")

    body = canonical_telemetry_bytes(batch)

    assert batch.to_dict() == _payload()
    assert body == expected_body
    assert hashlib.sha256(body).hexdigest() == GOLDEN_DIGEST
    assert (
        telemetry_hmac_sha256("test-runtime-telemetry-key", 1_719_000_000_123, body)
        == GOLDEN_HMAC
    )
    assert (
        telemetry_hmac_sha256(b"test-runtime-telemetry-key", b"1719000000123", body)
        == GOLDEN_HMAC
    )
    signature_header = "v1=" + telemetry_hmac_sha256(
        "test-runtime-telemetry-key", 1_719_000_000_123, body
    )
    assert signature_header == f"v1={GOLDEN_HMAC}"
    assert "Ìkẹjà".encode() in body
    assert b"\\u" not in body


def test_unknown_fields_round_trip_without_mutable_aliases() -> None:
    payload = _payload()
    events = cast(list[dict[str, object]], payload["events"])
    event = events[0]
    reading = cast(dict[str, object], event["reading"])
    payload["batch_extension"] = {"flags": ["first", "second"]}
    event["event_extension"] = {"enabled": True}
    reading["reading_extension"] = {"sample_count": 2}

    batch = RuntimeTelemetryBatch.from_dict(payload)
    cast(list[str], cast(dict[str, object], payload["batch_extension"])["flags"])[0] = (
        "changed"
    )

    assert batch.to_dict()["batch_extension"] == {"flags": ["first", "second"]}
    assert batch.events[0].to_dict()["event_extension"] == {"enabled": True}
    assert batch.events[0].reading.to_dict()["reading_extension"] == {"sample_count": 2}
    with pytest.raises(TypeError):
        cast(dict[str, object], batch.additional_fields)["new"] = True


def test_models_and_nested_json_are_immutable() -> None:
    batch = _batch()

    with pytest.raises(FrozenInstanceError):
        batch.sequence = 2  # type: ignore[misc]
    with pytest.raises(TypeError):
        cast(dict[str, object], batch.events[0].context)["location"] = "changed"
    with pytest.raises(TypeError):
        cast(dict[str, object], batch.events[0].reading.metadata)["label"] = "changed"


def test_empty_batch_and_nonpositive_temporal_values_are_allowed() -> None:
    batch = RuntimeTelemetryBatch(
        schema_version=RUNTIME_TELEMETRY_SCHEMA_VERSION,
        device_id="device-01",
        sequence=-1,
        sent_at_ms=0,
        events=(),
    )

    assert batch.to_dict() == {
        "schema_version": RUNTIME_TELEMETRY_SCHEMA_VERSION,
        "device_id": "device-01",
        "sequence": -1,
        "sent_at_ms": 0,
        "events": [],
    }

    payload = batch.to_dict()
    payload["sent_at_ms"] = -1
    assert RuntimeTelemetryBatch.from_dict(payload).to_dict() == payload


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), 1e-5, -1e-5, 1e16],
)
def test_reading_constructor_rejects_noncanonical_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="non-finite|canonical zone"):
        replace(_batch().events[0].reading, value=value)


@pytest.mark.parametrize("value", [JSON_SAFE_INT_MAX + 1, -JSON_SAFE_INT_MAX - 1])
def test_models_reject_integers_outside_json_safe_range(value: int) -> None:
    with pytest.raises(ValueError, match="JSON-safe"):
        replace(_batch(), sequence=value)
    with pytest.raises(ValueError, match="JSON-safe"):
        replace(_batch().events[0].reading, value=value)


def test_canonical_numeric_boundaries_and_negative_zero() -> None:
    reading = replace(_batch().events[0].reading, value=1e-4, quality=-0.0)
    event = replace(_batch().events[0], reading=reading)
    batch = replace(_batch(), events=(event,))
    body = canonical_telemetry_bytes(batch)

    assert b'"quality":-0.0' in body
    assert b'"value":0.0001' in body


def test_arbitrary_json_fields_enforce_canonical_number_zone() -> None:
    event = _batch().events[0]

    with pytest.raises(ValueError, match="canonical zone"):
        replace(
            event,
            context=cast(TelemetryJsonObject, {"nested": [1e-5]}),
        )
    with pytest.raises(ValueError, match="JSON-safe"):
        replace(event.reading, metadata={"count": JSON_SAFE_INT_MAX + 1})


def test_arbitrary_json_fields_reject_cycles() -> None:
    context: dict[str, object] = {}
    context["self"] = context

    with pytest.raises(ValueError, match="cyclic"):
        replace(_batch().events[0], context=cast(TelemetryJsonObject, context))


def test_models_reject_text_that_cannot_be_encoded_as_utf8() -> None:
    invalid_text = "\ud800"

    with pytest.raises(ValueError, match="valid UTF-8"):
        replace(_batch().events[0], source=invalid_text)
    with pytest.raises(ValueError, match="valid UTF-8"):
        replace(
            _batch().events[0],
            context=cast(TelemetryJsonObject, {"label": invalid_text}),
        )
    with pytest.raises(ValueError, match="valid UTF-8"):
        replace(
            _batch(),
            additional_fields=cast(TelemetryJsonObject, {invalid_text: True}),
        )


@pytest.mark.parametrize("schema_version", ["runtime.telemetry.v2", "", 1])
def test_schema_version_is_fixed_for_parser_and_constructor(
    schema_version: object,
) -> None:
    payload = _payload()
    payload["schema_version"] = schema_version

    with pytest.raises(ValueError, match="schema_version"):
        RuntimeTelemetryBatch.from_dict(payload)
    with pytest.raises(ValueError, match="schema_version"):
        replace(
            _batch(),
            schema_version=cast(Literal["runtime.telemetry.v1"], schema_version),
        )


def test_reading_raw_is_rejected_by_parser_and_constructor() -> None:
    payload = _payload()
    reading = cast(
        dict[str, object],
        cast(list[dict[str, object]], payload["events"])[0]["reading"],
    )
    reading["raw"] = "not-part-of-the-contract"

    with pytest.raises(ValueError, match="reading.raw"):
        RuntimeTelemetryBatch.from_dict(payload)
    with pytest.raises(ValueError, match="forbidden fields: 'raw'"):
        replace(_batch().events[0].reading, additional_fields={"raw": "bytes"})


def test_identifier_consistency_is_enforced_by_public_constructors() -> None:
    event = _batch().events[0]

    with pytest.raises(ValueError, match="event_type"):
        replace(
            event,
            event_type=cast(RuntimeTelemetryEventType, "action.executed"),
        )
    with pytest.raises(ValueError, match="sensor_id must match"):
        replace(event, sensor_id="different-sensor")
    with pytest.raises(ValueError, match="device_id must match"):
        replace(_batch(), device_id="different-device")


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("event_type", "action.executed", "event_type"),
        ("sensor_id", "different-sensor", "sensor_id must match"),
        ("device_id", "different-device", "device_id must match"),
    ],
)
def test_parser_enforces_event_contract(
    field_name: str, value: object, message: str
) -> None:
    payload = _payload()
    event = cast(list[dict[str, object]], payload["events"])[0]
    event[field_name] = value

    with pytest.raises(ValueError, match=message):
        RuntimeTelemetryBatch.from_dict(payload)


def test_parser_enforces_canonical_number_rules() -> None:
    payload = _payload()
    event = cast(list[dict[str, object]], payload["events"])[0]
    reading = cast(dict[str, object], event["reading"])
    reading["value"] = 1e-5

    with pytest.raises(ValueError, match="canonical zone"):
        RuntimeTelemetryBatch.from_dict(payload)


def test_additional_fields_cannot_override_contract_fields() -> None:
    with pytest.raises(ValueError, match="duplicates known fields: 'sequence'"):
        replace(_batch(), additional_fields={"sequence": 100})
    with pytest.raises(ValueError, match="duplicates known fields: 'reading'"):
        replace(_batch().events[0], additional_fields={"reading": {}})


def test_canonical_json_sorts_object_keys_and_preserves_array_order() -> None:
    batch = replace(
        _batch(),
        additional_fields={"z": {"b": 2, "a": 1}, "a": [3, 2, 1]},
    )
    body = canonical_telemetry_bytes(batch)

    assert body.startswith(b'{"a":[3,2,1],"device_id"')
    assert b'"z":{"a":1,"b":2}' in body


def test_canonical_helper_requires_a_validated_batch() -> None:
    with pytest.raises(TypeError, match="RuntimeTelemetryBatch"):
        canonical_telemetry_bytes(cast(RuntimeTelemetryBatch, _payload()))


def test_hmac_helper_rejects_ambiguous_inputs() -> None:
    body = canonical_telemetry_bytes(_batch())

    with pytest.raises(TypeError, match="timestamp_ms"):
        telemetry_hmac_sha256("key", True, body)
    with pytest.raises(ValueError, match="ASCII"):
        telemetry_hmac_sha256("key", "Ìkẹjà", body)
    with pytest.raises(TypeError, match="body"):
        telemetry_hmac_sha256("key", 1, cast(bytes, "body"))
