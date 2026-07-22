# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Pure SDK models and verification helpers for firmware telemetry v1.

The types in this module mirror ``ori-specs/firmware-telemetry/v1.md``. They
perform no network I/O, persist no replay state, construct no runtime sensor
readings, and grant no action authority. Runtime ingestion remains the
responsibility of ``FirmwareTelemetryGate`` in ori-runtime.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Literal, Mapping, TypeAlias, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

FIRMWARE_TELEMETRY_VERSION: Literal[1] = 1
FIRMWARE_SIGNATURE_ALGORITHM: Literal["ed25519"] = "ed25519"
FIRMWARE_SIGNATURE_PREFIX = "ed25519:"
FIRMWARE_JSON_SAFE_INT_MAX = 9_007_199_254_740_991
FIRMWARE_DEVICE_ID_MAX_LENGTH = 48
FIRMWARE_FAULT_TOKEN_MAX_LENGTH = 63

FirmwareDeviceMode = Literal["sensor_node", "bridge_node", "actuator_node", "mixed"]
FirmwarePosture = Literal["development", "sealed_flash", "hardware_key"]
FirmwareKeyStorage = Literal[
    "efuse_derived", "nvs_encrypted", "hardware_key", "dev_flash"
]
FirmwareTransport = Literal["mqtt", "uart", "rs485"]
FirmwareChannelProtocol = Literal[
    "adc", "gpio", "i2c", "uart", "modbus_rtu", "rs232", "pulse", "one_wire"
]
FirmwareAction = Literal["relay_open", "relay_close"]
FirmwareActionAuthority = Literal["local_interlock_only", "runtime_commanded"]
FirmwareCommandRejectionDetail = Literal[
    "malformed",
    "wrong_device",
    "bad_signature",
    "replayed",
    "capability_mismatch",
    "unknown_action",
    "storage_failure",
]
FirmwareFaultCode = Literal[
    "command_rejected",
    "interlock_input_fault",
    "interlock_recovered",
    "interlock_tripped",
    "sensor_fault",
    "brownout_relay_fault",
    "ingress_degraded",
]
FirmwareErrorCode = Literal[
    "unknown_device",
    "anchor_missing",
    "invalid_signature_format",
    "public_key_mismatch",
    "signature_verification_failed",
    "capability_hash_mismatch",
    "sequence_replay",
    "boot_rollback",
    "unsupported_channel",
    "invalid_posture",
    "invalid_reading",
    "invalid_envelope",
    "unsupported_alg",
]

_DEVICE_MODES = frozenset({"sensor_node", "bridge_node", "actuator_node", "mixed"})
_POSTURES = frozenset({"development", "sealed_flash", "hardware_key"})
_PRODUCTION_POSTURES = frozenset({"sealed_flash", "hardware_key"})
_KEY_STORAGES = frozenset(
    {"efuse_derived", "nvs_encrypted", "hardware_key", "dev_flash"}
)
_TRANSPORTS = frozenset({"mqtt", "uart", "rs485"})
_CHANNEL_PROTOCOLS = frozenset(
    {"adc", "gpio", "i2c", "uart", "modbus_rtu", "rs232", "pulse", "one_wire"}
)
_FIRMWARE_ACTIONS = frozenset({"relay_open", "relay_close"})
_ACTION_AUTHORITIES = frozenset({"local_interlock_only", "runtime_commanded"})
_COMMAND_REJECTION_DETAILS = frozenset(
    {
        "malformed",
        "wrong_device",
        "bad_signature",
        "replayed",
        "capability_mismatch",
        "unknown_action",
        "storage_failure",
    }
)
_FAULT_CODES = frozenset(
    {
        "command_rejected",
        "interlock_input_fault",
        "interlock_recovered",
        "interlock_tripped",
        "sensor_fault",
        "brownout_relay_fault",
        "ingress_degraded",
    }
)
_FLEET_IDENTIFIER_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
)
_HASH_PREFIX = "sha256:"

_MANIFEST_CHANNEL_FIELDS = frozenset(
    {"channel", "sensor_type", "unit", "protocol", "source", "quality_floor"}
)
_MANIFEST_ACTION_FIELDS = frozenset({"action", "channel", "authority"})
_MANIFEST_INTERLOCK_FIELDS = frozenset({"name", "channel", "action"})
_MANIFEST_FIELDS = frozenset(
    {
        "v",
        "alg",
        "device_id",
        "firmware_version",
        "board_profile",
        "device_mode",
        "public_key_b64",
        "posture",
        "secure_boot_enabled",
        "flash_encryption_enabled",
        "key_storage",
        "transports",
        "channels",
        "actions",
        "interlocks",
    }
)
_SIGNED_MANIFEST_FIELDS = frozenset({"manifest", "manifest_hash", "signature"})
_READING_FIELDS = frozenset({"channel", "sensor_type", "unit", "value", "quality"})
_TELEMETRY_ENVELOPE_FIELDS = frozenset(
    {
        "v",
        "alg",
        "device_id",
        "boot_id",
        "seq",
        "capability_hash",
        "posture",
        "device_uptime_ms",
        "emitted_at_ms",
        "readings",
    }
)
_SIGNED_TELEMETRY_FIELDS = frozenset({"envelope", "signature"})
_FAULT_FIELDS = frozenset(
    {
        "v",
        "alg",
        "device_id",
        "boot_id",
        "seq",
        "capability_hash",
        "posture",
        "device_uptime_ms",
        "code",
        "subject",
        "detail",
    }
)
_SIGNED_FAULT_FIELDS = frozenset({"fault", "signature"})
_PROVISIONING_ANCHOR_FIELDS = frozenset(
    {
        "device_id",
        "public_key_b64",
        "initial_manifest_hash",
        "posture",
        "provisioned_at_ms",
    }
)


class FirmwareTelemetryError(ValueError):
    """Fail-closed contract or signature verification error."""

    def __init__(self, code: FirmwareErrorCode, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FirmwareTelemetryError(
            "invalid_envelope", f"{field_name} must be an object"
        )
    for key in value:
        if not isinstance(key, str):
            raise FirmwareTelemetryError(
                "invalid_envelope", f"{field_name} keys must be strings"
            )
    return cast(Mapping[str, object], value)


def _require_exact_fields(
    payload: Mapping[str, object], expected: frozenset[str], field_name: str
) -> None:
    if any(not isinstance(key, str) for key in payload):
        raise FirmwareTelemetryError(
            "invalid_envelope", f"{field_name} keys must be strings"
        )
    actual = set(payload)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    parts: list[str] = []
    if missing:
        parts.append("missing " + ", ".join(repr(item) for item in missing))
    if unexpected:
        parts.append("unexpected " + ", ".join(repr(item) for item in unexpected))
    raise FirmwareTelemetryError(
        "invalid_envelope", f"{field_name} fields: {'; '.join(parts)}"
    )


def _require_string(
    value: object, field_name: str, *, allow_empty: bool = False
) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise FirmwareTelemetryError(
            "invalid_envelope", f"{field_name} must be {qualifier}"
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise FirmwareTelemetryError(
            "invalid_envelope", f"{field_name} must be valid UTF-8 text"
        ) from exc
    return value


def _require_device_id(value: object) -> str:
    device_id = _require_string(value, "device_id")
    if len(device_id) > FIRMWARE_DEVICE_ID_MAX_LENGTH or any(
        char not in _FLEET_IDENTIFIER_CHARS for char in device_id
    ):
        raise FirmwareTelemetryError(
            "invalid_envelope",
            "device_id must use [A-Za-z0-9._-] and be at most 48 characters",
        )
    return device_id


def _require_fault_token(value: object, field_name: str) -> str:
    token = _require_string(value, field_name, allow_empty=True)
    if len(token) > FIRMWARE_FAULT_TOKEN_MAX_LENGTH or any(
        char not in _FLEET_IDENTIFIER_CHARS for char in token
    ):
        raise FirmwareTelemetryError(
            "invalid_envelope",
            f"{field_name} must use the fleet identifier alphabet and be at most 63 characters",
        )
    return token


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise FirmwareTelemetryError(
            "invalid_envelope", f"{field_name} must be a boolean"
        )
    return value


def _require_safe_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FirmwareTelemetryError(
            "invalid_envelope", f"{field_name} must be an integer"
        )
    if abs(value) > FIRMWARE_JSON_SAFE_INT_MAX:
        raise FirmwareTelemetryError(
            "invalid_envelope", f"{field_name} is outside the JSON-safe range"
        )
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    parsed = _require_safe_int(value, field_name)
    if parsed < 0:
        raise FirmwareTelemetryError(
            "invalid_envelope", f"{field_name} must be non-negative"
        )
    return parsed


def _require_number(
    value: object, field_name: str, *, error_code: FirmwareErrorCode
) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FirmwareTelemetryError(error_code, f"{field_name} must be numeric")
    _validate_canonical_number(value, field_name, error_code=error_code)
    return value


def _validate_canonical_number(
    value: int | float, field_name: str, *, error_code: FirmwareErrorCode
) -> None:
    if isinstance(value, int):
        if abs(value) > FIRMWARE_JSON_SAFE_INT_MAX:
            raise FirmwareTelemetryError(
                error_code, f"integer outside JSON-safe range at {field_name}"
            )
        return
    if not math.isfinite(value):
        raise FirmwareTelemetryError(error_code, f"non-finite number at {field_name}")
    magnitude = abs(value)
    if magnitude != 0.0 and not (1e-4 <= magnitude < 1e16):
        raise FirmwareTelemetryError(
            error_code,
            f"float outside the cross-language canonical zone at {field_name}",
        )


def _require_array(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise FirmwareTelemetryError(
            "invalid_envelope", f"{field_name} must be an array"
        )
    return cast(list[object], value)


def _require_literal(
    value: object,
    allowed: frozenset[str],
    field_name: str,
    *,
    error_code: FirmwareErrorCode = "invalid_envelope",
) -> str:
    parsed = _require_string(value, field_name)
    if parsed not in allowed:
        raise FirmwareTelemetryError(error_code, f"unsupported {field_name} {parsed!r}")
    return parsed


def _require_version(value: object, field_name: str) -> Literal[1]:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value != FIRMWARE_TELEMETRY_VERSION
    ):
        raise FirmwareTelemetryError("invalid_envelope", f"{field_name} must be 1")
    return FIRMWARE_TELEMETRY_VERSION


def _require_algorithm(value: object, field_name: str) -> Literal["ed25519"]:
    if value != FIRMWARE_SIGNATURE_ALGORITHM:
        raise FirmwareTelemetryError("unsupported_alg", f"{field_name} must be ed25519")
    return FIRMWARE_SIGNATURE_ALGORITHM


def _require_hash(value: object, field_name: str) -> str:
    digest = _require_string(value, field_name)
    hex_part = digest[len(_HASH_PREFIX) :] if digest.startswith(_HASH_PREFIX) else ""
    if len(hex_part) != 64 or any(char not in "0123456789abcdef" for char in hex_part):
        raise FirmwareTelemetryError(
            "capability_hash_mismatch",
            f"{field_name} must be sha256:<64-lowercase-hex>",
        )
    return digest


def _decode_public_key(public_key_b64: object) -> tuple[str, bytes]:
    if not isinstance(public_key_b64, str):
        raise FirmwareTelemetryError(
            "public_key_mismatch", "public key must be a base64 string"
        )
    try:
        raw = base64.b64decode(public_key_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FirmwareTelemetryError("public_key_mismatch", str(exc)) from exc
    if len(raw) != 32 or base64.b64encode(raw).decode("ascii") != public_key_b64:
        raise FirmwareTelemetryError(
            "public_key_mismatch", "public key is not canonical 32-byte base64"
        )
    return public_key_b64, raw


def _decode_signature(signature: object) -> tuple[str, bytes]:
    if not isinstance(signature, str) or not signature.startswith(
        FIRMWARE_SIGNATURE_PREFIX
    ):
        raise FirmwareTelemetryError(
            "invalid_signature_format", "signature must use ed25519:<base64>"
        )
    encoded = signature[len(FIRMWARE_SIGNATURE_PREFIX) :]
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FirmwareTelemetryError("invalid_signature_format", str(exc)) from exc
    if len(raw) != 64 or base64.b64encode(raw).decode("ascii") != encoded:
        raise FirmwareTelemetryError(
            "invalid_signature_format",
            "signature must contain canonical base64 for 64 bytes",
        )
    return signature, raw


@dataclass(frozen=True, slots=True)
class FirmwareManifestChannel:
    """One measurement channel declared by a capability manifest."""

    channel: str
    sensor_type: str
    unit: str
    protocol: FirmwareChannelProtocol
    source: str
    quality_floor: int | float

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel", _require_string(self.channel, "channel"))
        object.__setattr__(
            self, "sensor_type", _require_string(self.sensor_type, "sensor_type")
        )
        object.__setattr__(self, "unit", _require_string(self.unit, "unit"))
        object.__setattr__(
            self,
            "protocol",
            _require_literal(
                self.protocol,
                _CHANNEL_PROTOCOLS,
                "protocol",
                error_code="unsupported_channel",
            ),
        )
        object.__setattr__(self, "source", _require_string(self.source, "source"))
        quality_floor = _require_number(
            self.quality_floor, "quality_floor", error_code="invalid_reading"
        )
        if not 0.0 <= quality_floor <= 1.0:
            raise FirmwareTelemetryError(
                "invalid_reading", "quality_floor must be between 0 and 1"
            )
        object.__setattr__(self, "quality_floor", quality_floor)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FirmwareManifestChannel:
        _require_exact_fields(payload, _MANIFEST_CHANNEL_FIELDS, "manifest channel")
        protocol = _require_literal(
            payload.get("protocol"),
            _CHANNEL_PROTOCOLS,
            "protocol",
            error_code="unsupported_channel",
        )
        return cls(
            channel=_require_string(payload.get("channel"), "channel"),
            sensor_type=_require_string(payload.get("sensor_type"), "sensor_type"),
            unit=_require_string(payload.get("unit"), "unit"),
            protocol=cast(FirmwareChannelProtocol, protocol),
            source=_require_string(payload.get("source"), "source"),
            quality_floor=_require_number(
                payload.get("quality_floor"),
                "quality_floor",
                error_code="invalid_reading",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "channel": self.channel,
            "sensor_type": self.sensor_type,
            "unit": self.unit,
            "protocol": self.protocol,
            "source": self.source,
            "quality_floor": self.quality_floor,
        }


@dataclass(frozen=True, slots=True)
class FirmwareManifestAction:
    """A firmware capability, never a runtime Tier C or Tier D grant."""

    action: FirmwareAction
    channel: str
    authority: FirmwareActionAuthority

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action",
            _require_literal(self.action, _FIRMWARE_ACTIONS, "firmware action"),
        )
        object.__setattr__(self, "channel", _require_string(self.channel, "channel"))
        object.__setattr__(
            self,
            "authority",
            _require_literal(self.authority, _ACTION_AUTHORITIES, "authority"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FirmwareManifestAction:
        _require_exact_fields(payload, _MANIFEST_ACTION_FIELDS, "manifest action")
        action = _require_literal(
            payload.get("action"), _FIRMWARE_ACTIONS, "firmware action"
        )
        authority = _require_literal(
            payload.get("authority"), _ACTION_AUTHORITIES, "authority"
        )
        return cls(
            action=cast(FirmwareAction, action),
            channel=_require_string(payload.get("channel"), "channel"),
            authority=cast(FirmwareActionAuthority, authority),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "channel": self.channel,
            "authority": self.authority,
        }


@dataclass(frozen=True, slots=True)
class FirmwareManifestInterlock:
    """A local defense-in-depth interlock declared by firmware."""

    name: str
    channel: str
    action: FirmwareAction

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_string(self.name, "name"))
        object.__setattr__(self, "channel", _require_string(self.channel, "channel"))
        object.__setattr__(
            self,
            "action",
            _require_literal(self.action, _FIRMWARE_ACTIONS, "firmware action"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FirmwareManifestInterlock:
        _require_exact_fields(payload, _MANIFEST_INTERLOCK_FIELDS, "manifest interlock")
        action = _require_literal(
            payload.get("action"), _FIRMWARE_ACTIONS, "firmware action"
        )
        return cls(
            name=_require_string(payload.get("name"), "name"),
            channel=_require_string(payload.get("channel"), "channel"),
            action=cast(FirmwareAction, action),
        )

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "channel": self.channel, "action": self.action}


@dataclass(frozen=True, slots=True)
class FirmwareCapabilityManifest:
    """Unsigned, immutable capability manifest covered by a device signature."""

    v: Literal[1]
    alg: Literal["ed25519"]
    device_id: str
    firmware_version: str
    board_profile: str
    device_mode: FirmwareDeviceMode
    public_key_b64: str
    posture: FirmwarePosture
    secure_boot_enabled: bool
    flash_encryption_enabled: bool
    key_storage: FirmwareKeyStorage
    transports: tuple[FirmwareTransport, ...]
    channels: tuple[FirmwareManifestChannel, ...]
    actions: tuple[FirmwareManifestAction, ...]
    interlocks: tuple[FirmwareManifestInterlock, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "v", _require_version(self.v, "manifest.v"))
        object.__setattr__(self, "alg", _require_algorithm(self.alg, "manifest.alg"))
        object.__setattr__(self, "device_id", _require_device_id(self.device_id))
        object.__setattr__(
            self,
            "firmware_version",
            _require_string(self.firmware_version, "firmware_version"),
        )
        object.__setattr__(
            self,
            "board_profile",
            _require_string(self.board_profile, "board_profile"),
        )
        object.__setattr__(
            self,
            "device_mode",
            _require_literal(self.device_mode, _DEVICE_MODES, "device_mode"),
        )
        public_key_b64, _ = _decode_public_key(self.public_key_b64)
        object.__setattr__(self, "public_key_b64", public_key_b64)
        posture = _require_literal(
            self.posture, _POSTURES, "posture", error_code="invalid_posture"
        )
        object.__setattr__(self, "posture", posture)
        secure_boot = _require_bool(self.secure_boot_enabled, "secure_boot_enabled")
        flash_encryption = _require_bool(
            self.flash_encryption_enabled, "flash_encryption_enabled"
        )
        if posture in _PRODUCTION_POSTURES and not (secure_boot and flash_encryption):
            raise FirmwareTelemetryError(
                "invalid_posture",
                "production posture requires secure boot and flash encryption",
            )
        object.__setattr__(self, "secure_boot_enabled", secure_boot)
        object.__setattr__(self, "flash_encryption_enabled", flash_encryption)
        object.__setattr__(
            self,
            "key_storage",
            _require_literal(self.key_storage, _KEY_STORAGES, "key_storage"),
        )
        if not isinstance(self.transports, tuple) or not self.transports:
            raise FirmwareTelemetryError(
                "invalid_envelope", "transports must be a non-empty tuple"
            )
        transports = tuple(
            cast(
                FirmwareTransport,
                _require_literal(transport, _TRANSPORTS, "transport"),
            )
            for transport in self.transports
        )
        object.__setattr__(self, "transports", transports)
        if not isinstance(self.channels, tuple) or not self.channels:
            raise FirmwareTelemetryError(
                "invalid_envelope", "channels must be a non-empty tuple"
            )
        if not all(isinstance(item, FirmwareManifestChannel) for item in self.channels):
            raise FirmwareTelemetryError(
                "unsupported_channel", "channels must contain manifest channel models"
            )
        channel_names = [item.channel for item in self.channels]
        if len(channel_names) != len(set(channel_names)):
            raise FirmwareTelemetryError(
                "unsupported_channel", "manifest channel names must be unique"
            )
        if not isinstance(self.actions, tuple) or not all(
            isinstance(item, FirmwareManifestAction) for item in self.actions
        ):
            raise FirmwareTelemetryError(
                "invalid_envelope", "actions must be a tuple of manifest actions"
            )
        if not isinstance(self.interlocks, tuple) or not all(
            isinstance(item, FirmwareManifestInterlock) for item in self.interlocks
        ):
            raise FirmwareTelemetryError(
                "invalid_envelope", "interlocks must be a tuple of manifest interlocks"
            )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FirmwareCapabilityManifest:
        _require_exact_fields(payload, _MANIFEST_FIELDS, "manifest")
        transports = _require_array(payload.get("transports"), "transports")
        channels = _require_array(payload.get("channels"), "channels")
        actions = _require_array(payload.get("actions"), "actions")
        interlocks = _require_array(payload.get("interlocks"), "interlocks")
        device_mode = _require_literal(
            payload.get("device_mode"), _DEVICE_MODES, "device_mode"
        )
        posture = _require_literal(
            payload.get("posture"),
            _POSTURES,
            "posture",
            error_code="invalid_posture",
        )
        key_storage = _require_literal(
            payload.get("key_storage"), _KEY_STORAGES, "key_storage"
        )
        return cls(
            v=_require_version(payload.get("v"), "manifest.v"),
            alg=_require_algorithm(payload.get("alg"), "manifest.alg"),
            device_id=_require_device_id(payload.get("device_id")),
            firmware_version=_require_string(
                payload.get("firmware_version"), "firmware_version"
            ),
            board_profile=_require_string(
                payload.get("board_profile"), "board_profile"
            ),
            device_mode=cast(FirmwareDeviceMode, device_mode),
            public_key_b64=_decode_public_key(payload.get("public_key_b64"))[0],
            posture=cast(FirmwarePosture, posture),
            secure_boot_enabled=_require_bool(
                payload.get("secure_boot_enabled"), "secure_boot_enabled"
            ),
            flash_encryption_enabled=_require_bool(
                payload.get("flash_encryption_enabled"),
                "flash_encryption_enabled",
            ),
            key_storage=cast(FirmwareKeyStorage, key_storage),
            transports=tuple(
                cast(
                    FirmwareTransport,
                    _require_literal(item, _TRANSPORTS, "transport"),
                )
                for item in transports
            ),
            channels=tuple(
                FirmwareManifestChannel.from_dict(
                    _require_mapping(item, "manifest channel")
                )
                for item in channels
            ),
            actions=tuple(
                FirmwareManifestAction.from_dict(
                    _require_mapping(item, "manifest action")
                )
                for item in actions
            ),
            interlocks=tuple(
                FirmwareManifestInterlock.from_dict(
                    _require_mapping(item, "manifest interlock")
                )
                for item in interlocks
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "v": self.v,
            "alg": self.alg,
            "device_id": self.device_id,
            "firmware_version": self.firmware_version,
            "board_profile": self.board_profile,
            "device_mode": self.device_mode,
            "public_key_b64": self.public_key_b64,
            "posture": self.posture,
            "secure_boot_enabled": self.secure_boot_enabled,
            "flash_encryption_enabled": self.flash_encryption_enabled,
            "key_storage": self.key_storage,
            "transports": list(self.transports),
            "channels": [channel.to_dict() for channel in self.channels],
            "actions": [action.to_dict() for action in self.actions],
            "interlocks": [interlock.to_dict() for interlock in self.interlocks],
        }


@dataclass(frozen=True, slots=True)
class SignedFirmwareCapabilityManifest:
    """Wire wrapper for a signed capability manifest."""

    manifest: FirmwareCapabilityManifest
    manifest_hash: str
    signature: str

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, FirmwareCapabilityManifest):
            raise FirmwareTelemetryError(
                "invalid_envelope", "manifest must be a capability manifest"
            )
        manifest_hash = _require_hash(self.manifest_hash, "manifest_hash")
        expected = firmware_manifest_hash(self.manifest)
        if manifest_hash != expected:
            raise FirmwareTelemetryError(
                "capability_hash_mismatch", "manifest_hash does not match manifest"
            )
        object.__setattr__(self, "manifest_hash", manifest_hash)
        object.__setattr__(self, "signature", _decode_signature(self.signature)[0])

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, object]
    ) -> SignedFirmwareCapabilityManifest:
        _require_exact_fields(payload, _SIGNED_MANIFEST_FIELDS, "signed manifest")
        return cls(
            manifest=FirmwareCapabilityManifest.from_dict(
                _require_mapping(payload.get("manifest"), "manifest")
            ),
            manifest_hash=_require_hash(payload.get("manifest_hash"), "manifest_hash"),
            signature=_decode_signature(payload.get("signature"))[0],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.to_dict(),
            "manifest_hash": self.manifest_hash,
            "signature": self.signature,
        }


@dataclass(frozen=True, slots=True)
class FirmwareTelemetryReading:
    """One exact-shape v1 reading inside a signed telemetry envelope."""

    channel: str
    sensor_type: str
    unit: str
    value: int | float
    quality: int | float

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel", _require_string(self.channel, "channel"))
        object.__setattr__(
            self, "sensor_type", _require_string(self.sensor_type, "sensor_type")
        )
        object.__setattr__(self, "unit", _require_string(self.unit, "unit"))
        object.__setattr__(
            self,
            "value",
            _require_number(self.value, "value", error_code="invalid_reading"),
        )
        quality = _require_number(self.quality, "quality", error_code="invalid_reading")
        if not 0.0 <= quality <= 1.0:
            raise FirmwareTelemetryError(
                "invalid_reading", "quality must be between 0 and 1"
            )
        object.__setattr__(self, "quality", quality)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FirmwareTelemetryReading:
        try:
            _require_exact_fields(payload, _READING_FIELDS, "reading")
        except FirmwareTelemetryError as exc:
            raise FirmwareTelemetryError("invalid_reading", exc.detail) from exc
        return cls(
            channel=_require_string(payload.get("channel"), "channel"),
            sensor_type=_require_string(payload.get("sensor_type"), "sensor_type"),
            unit=_require_string(payload.get("unit"), "unit"),
            value=_require_number(
                payload.get("value"), "value", error_code="invalid_reading"
            ),
            quality=_require_number(
                payload.get("quality"), "quality", error_code="invalid_reading"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "channel": self.channel,
            "sensor_type": self.sensor_type,
            "unit": self.unit,
            "value": self.value,
            "quality": self.quality,
        }


@dataclass(frozen=True, slots=True)
class _ValidatedEnvelopeFields:
    v: Literal[1]
    alg: Literal["ed25519"]
    device_id: str
    boot_id: int
    seq: int
    capability_hash: str
    posture: FirmwarePosture
    device_uptime_ms: int
    emitted_at_ms: int | None


def _validate_envelope_fields(
    *,
    v: object,
    alg: object,
    device_id: object,
    boot_id: object,
    seq: object,
    capability_hash: object,
    posture: object,
    device_uptime_ms: object,
    emitted_at_ms: object,
) -> _ValidatedEnvelopeFields:
    parsed_posture = _require_literal(
        posture, _POSTURES, "posture", error_code="invalid_posture"
    )
    parsed_emitted_at = (
        None
        if emitted_at_ms is None
        else _require_safe_int(emitted_at_ms, "emitted_at_ms")
    )
    return _ValidatedEnvelopeFields(
        v=_require_version(v, "envelope.v"),
        alg=_require_algorithm(alg, "envelope.alg"),
        device_id=_require_device_id(device_id),
        boot_id=_require_non_negative_int(boot_id, "boot_id"),
        seq=_require_non_negative_int(seq, "seq"),
        capability_hash=_require_hash(capability_hash, "capability_hash"),
        posture=cast(FirmwarePosture, parsed_posture),
        device_uptime_ms=_require_non_negative_int(
            device_uptime_ms, "device_uptime_ms"
        ),
        emitted_at_ms=parsed_emitted_at,
    )


def _set_envelope_fields(
    target: FirmwareTelemetryEnvelope | FirmwareHeartbeatEnvelope,
    fields: _ValidatedEnvelopeFields,
) -> None:
    for field_name in (
        "v",
        "alg",
        "device_id",
        "boot_id",
        "seq",
        "capability_hash",
        "posture",
        "device_uptime_ms",
        "emitted_at_ms",
    ):
        object.__setattr__(target, field_name, getattr(fields, field_name))


def _envelope_dict(
    envelope: FirmwareTelemetryEnvelope | FirmwareHeartbeatEnvelope,
    readings: list[object],
) -> dict[str, object]:
    return {
        "v": envelope.v,
        "alg": envelope.alg,
        "device_id": envelope.device_id,
        "boot_id": envelope.boot_id,
        "seq": envelope.seq,
        "capability_hash": envelope.capability_hash,
        "posture": envelope.posture,
        "device_uptime_ms": envelope.device_uptime_ms,
        "emitted_at_ms": envelope.emitted_at_ms,
        "readings": readings,
    }


@dataclass(frozen=True, slots=True)
class FirmwareTelemetryEnvelope:
    """A signed measurement payload; it always contains at least one reading."""

    v: Literal[1]
    alg: Literal["ed25519"]
    device_id: str
    boot_id: int
    seq: int
    capability_hash: str
    posture: FirmwarePosture
    device_uptime_ms: int
    emitted_at_ms: int | None
    readings: tuple[FirmwareTelemetryReading, ...]

    def __post_init__(self) -> None:
        fields = _validate_envelope_fields(
            v=self.v,
            alg=self.alg,
            device_id=self.device_id,
            boot_id=self.boot_id,
            seq=self.seq,
            capability_hash=self.capability_hash,
            posture=self.posture,
            device_uptime_ms=self.device_uptime_ms,
            emitted_at_ms=self.emitted_at_ms,
        )
        _set_envelope_fields(self, fields)
        if not isinstance(self.readings, tuple):
            raise FirmwareTelemetryError(
                "invalid_reading", "readings must be an immutable tuple"
            )
        if not self.readings:
            raise FirmwareTelemetryError(
                "invalid_reading",
                "measurement telemetry requires at least one reading; use a heartbeat for an empty array",
            )
        if not all(
            isinstance(item, FirmwareTelemetryReading) for item in self.readings
        ):
            raise FirmwareTelemetryError(
                "invalid_reading", "readings must contain telemetry reading models"
            )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FirmwareTelemetryEnvelope:
        _require_exact_fields(payload, _TELEMETRY_ENVELOPE_FIELDS, "envelope")
        readings = _require_array(payload.get("readings"), "readings")
        if not readings:
            raise FirmwareTelemetryError(
                "invalid_reading", "empty readings belong to a heartbeat envelope"
            )
        fields = _validate_envelope_fields(
            v=payload.get("v"),
            alg=payload.get("alg"),
            device_id=payload.get("device_id"),
            boot_id=payload.get("boot_id"),
            seq=payload.get("seq"),
            capability_hash=payload.get("capability_hash"),
            posture=payload.get("posture"),
            device_uptime_ms=payload.get("device_uptime_ms"),
            emitted_at_ms=payload.get("emitted_at_ms"),
        )
        return cls(
            v=fields.v,
            alg=fields.alg,
            device_id=fields.device_id,
            boot_id=fields.boot_id,
            seq=fields.seq,
            capability_hash=fields.capability_hash,
            posture=fields.posture,
            device_uptime_ms=fields.device_uptime_ms,
            emitted_at_ms=fields.emitted_at_ms,
            readings=tuple(
                FirmwareTelemetryReading.from_dict(_require_mapping(item, "reading"))
                for item in readings
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return _envelope_dict(
            self, [cast(object, reading.to_dict()) for reading in self.readings]
        )


@dataclass(frozen=True, slots=True)
class FirmwareHeartbeatEnvelope:
    """A distinct liveness payload whose wire ``readings`` value is empty."""

    v: Literal[1]
    alg: Literal["ed25519"]
    device_id: str
    boot_id: int
    seq: int
    capability_hash: str
    posture: FirmwarePosture
    device_uptime_ms: int
    emitted_at_ms: int | None

    def __post_init__(self) -> None:
        fields = _validate_envelope_fields(
            v=self.v,
            alg=self.alg,
            device_id=self.device_id,
            boot_id=self.boot_id,
            seq=self.seq,
            capability_hash=self.capability_hash,
            posture=self.posture,
            device_uptime_ms=self.device_uptime_ms,
            emitted_at_ms=self.emitted_at_ms,
        )
        _set_envelope_fields(self, fields)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FirmwareHeartbeatEnvelope:
        _require_exact_fields(payload, _TELEMETRY_ENVELOPE_FIELDS, "envelope")
        readings = _require_array(payload.get("readings"), "readings")
        if readings:
            raise FirmwareTelemetryError(
                "invalid_reading", "heartbeat readings must be empty"
            )
        fields = _validate_envelope_fields(
            v=payload.get("v"),
            alg=payload.get("alg"),
            device_id=payload.get("device_id"),
            boot_id=payload.get("boot_id"),
            seq=payload.get("seq"),
            capability_hash=payload.get("capability_hash"),
            posture=payload.get("posture"),
            device_uptime_ms=payload.get("device_uptime_ms"),
            emitted_at_ms=payload.get("emitted_at_ms"),
        )
        return cls(
            v=fields.v,
            alg=fields.alg,
            device_id=fields.device_id,
            boot_id=fields.boot_id,
            seq=fields.seq,
            capability_hash=fields.capability_hash,
            posture=fields.posture,
            device_uptime_ms=fields.device_uptime_ms,
            emitted_at_ms=fields.emitted_at_ms,
        )

    def to_dict(self) -> dict[str, object]:
        return _envelope_dict(self, [])


@dataclass(frozen=True, slots=True)
class SignedFirmwareTelemetry:
    """Signed wire message carrying measurement telemetry."""

    envelope: FirmwareTelemetryEnvelope
    signature: str

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, FirmwareTelemetryEnvelope):
            raise FirmwareTelemetryError(
                "invalid_envelope", "envelope must be measurement telemetry"
            )
        object.__setattr__(self, "signature", _decode_signature(self.signature)[0])

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> SignedFirmwareTelemetry:
        _require_exact_fields(payload, _SIGNED_TELEMETRY_FIELDS, "signed telemetry")
        return cls(
            envelope=FirmwareTelemetryEnvelope.from_dict(
                _require_mapping(payload.get("envelope"), "envelope")
            ),
            signature=_decode_signature(payload.get("signature"))[0],
        )

    def to_dict(self) -> dict[str, object]:
        return {"envelope": self.envelope.to_dict(), "signature": self.signature}


@dataclass(frozen=True, slots=True)
class SignedFirmwareHeartbeat:
    """Signed wire message carrying liveness evidence and no measurement."""

    envelope: FirmwareHeartbeatEnvelope
    signature: str

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, FirmwareHeartbeatEnvelope):
            raise FirmwareTelemetryError(
                "invalid_envelope", "envelope must be a heartbeat"
            )
        object.__setattr__(self, "signature", _decode_signature(self.signature)[0])

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> SignedFirmwareHeartbeat:
        _require_exact_fields(payload, _SIGNED_TELEMETRY_FIELDS, "signed heartbeat")
        return cls(
            envelope=FirmwareHeartbeatEnvelope.from_dict(
                _require_mapping(payload.get("envelope"), "envelope")
            ),
            signature=_decode_signature(payload.get("signature"))[0],
        )

    def to_dict(self) -> dict[str, object]:
        return {"envelope": self.envelope.to_dict(), "signature": self.signature}


def parse_signed_firmware_telemetry(
    payload: Mapping[str, object],
) -> SignedFirmwareTelemetry | SignedFirmwareHeartbeat:
    """Parse telemetry and dispatch an empty reading array to heartbeat type."""

    _require_exact_fields(payload, _SIGNED_TELEMETRY_FIELDS, "signed telemetry")
    envelope = _require_mapping(payload.get("envelope"), "envelope")
    readings = _require_array(envelope.get("readings"), "readings")
    if readings:
        return SignedFirmwareTelemetry.from_dict(payload)
    return SignedFirmwareHeartbeat.from_dict(payload)


@dataclass(frozen=True, slots=True)
class FirmwareFaultEvent:
    """Signed device fault evidence; never telemetry or action authority."""

    v: Literal[1]
    alg: Literal["ed25519"]
    device_id: str
    boot_id: int
    seq: int
    capability_hash: str
    posture: FirmwarePosture
    device_uptime_ms: int
    code: FirmwareFaultCode
    subject: str
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "v", _require_version(self.v, "fault.v"))
        object.__setattr__(self, "alg", _require_algorithm(self.alg, "fault.alg"))
        object.__setattr__(self, "device_id", _require_device_id(self.device_id))
        object.__setattr__(
            self, "boot_id", _require_non_negative_int(self.boot_id, "boot_id")
        )
        object.__setattr__(self, "seq", _require_non_negative_int(self.seq, "seq"))
        object.__setattr__(
            self,
            "capability_hash",
            _require_hash(self.capability_hash, "capability_hash"),
        )
        object.__setattr__(
            self,
            "posture",
            _require_literal(
                self.posture, _POSTURES, "posture", error_code="invalid_posture"
            ),
        )
        object.__setattr__(
            self,
            "device_uptime_ms",
            _require_non_negative_int(self.device_uptime_ms, "device_uptime_ms"),
        )
        code = _require_literal(self.code, _FAULT_CODES, "fault code")
        object.__setattr__(self, "code", code)
        object.__setattr__(
            self, "subject", _require_fault_token(self.subject, "subject")
        )
        detail = _require_fault_token(self.detail, "detail")
        if code == "command_rejected":
            detail = _require_literal(
                detail,
                _COMMAND_REJECTION_DETAILS,
                "command rejection detail",
            )
        object.__setattr__(self, "detail", detail)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FirmwareFaultEvent:
        _require_exact_fields(payload, _FAULT_FIELDS, "fault")
        posture = _require_literal(
            payload.get("posture"),
            _POSTURES,
            "posture",
            error_code="invalid_posture",
        )
        code = _require_literal(payload.get("code"), _FAULT_CODES, "fault code")
        return cls(
            v=_require_version(payload.get("v"), "fault.v"),
            alg=_require_algorithm(payload.get("alg"), "fault.alg"),
            device_id=_require_device_id(payload.get("device_id")),
            boot_id=_require_non_negative_int(payload.get("boot_id"), "boot_id"),
            seq=_require_non_negative_int(payload.get("seq"), "seq"),
            capability_hash=_require_hash(
                payload.get("capability_hash"), "capability_hash"
            ),
            posture=cast(FirmwarePosture, posture),
            device_uptime_ms=_require_non_negative_int(
                payload.get("device_uptime_ms"), "device_uptime_ms"
            ),
            code=cast(FirmwareFaultCode, code),
            subject=_require_fault_token(payload.get("subject"), "subject"),
            detail=_require_fault_token(payload.get("detail"), "detail"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "v": self.v,
            "alg": self.alg,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "seq": self.seq,
            "capability_hash": self.capability_hash,
            "posture": self.posture,
            "device_uptime_ms": self.device_uptime_ms,
            "code": self.code,
            "subject": self.subject,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class SignedFirmwareFaultEvent:
    """Wire wrapper for a device-signed fault event."""

    fault: FirmwareFaultEvent
    signature: str

    def __post_init__(self) -> None:
        if not isinstance(self.fault, FirmwareFaultEvent):
            raise FirmwareTelemetryError(
                "invalid_envelope", "fault must be a firmware fault event"
            )
        object.__setattr__(self, "signature", _decode_signature(self.signature)[0])

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> SignedFirmwareFaultEvent:
        _require_exact_fields(payload, _SIGNED_FAULT_FIELDS, "signed fault")
        return cls(
            fault=FirmwareFaultEvent.from_dict(
                _require_mapping(payload.get("fault"), "fault")
            ),
            signature=_decode_signature(payload.get("signature"))[0],
        )

    def to_dict(self) -> dict[str, object]:
        return {"fault": self.fault.to_dict(), "signature": self.signature}


@dataclass(frozen=True, slots=True)
class FirmwareProvisioningAnchor:
    """Off-device identity and initial capability pin for one firmware node."""

    device_id: str
    public_key_b64: str
    initial_manifest_hash: str
    posture: FirmwarePosture
    provisioned_at_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "device_id", _require_device_id(self.device_id))
        object.__setattr__(
            self, "public_key_b64", _decode_public_key(self.public_key_b64)[0]
        )
        object.__setattr__(
            self,
            "initial_manifest_hash",
            _require_hash(self.initial_manifest_hash, "initial_manifest_hash"),
        )
        object.__setattr__(
            self,
            "posture",
            _require_literal(
                self.posture, _POSTURES, "posture", error_code="invalid_posture"
            ),
        )
        object.__setattr__(
            self,
            "provisioned_at_ms",
            _require_non_negative_int(self.provisioned_at_ms, "provisioned_at_ms"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FirmwareProvisioningAnchor:
        _require_exact_fields(payload, _PROVISIONING_ANCHOR_FIELDS, "anchor")
        posture = _require_literal(
            payload.get("posture"),
            _POSTURES,
            "posture",
            error_code="invalid_posture",
        )
        return cls(
            device_id=_require_device_id(payload.get("device_id")),
            public_key_b64=_decode_public_key(payload.get("public_key_b64"))[0],
            initial_manifest_hash=_require_hash(
                payload.get("initial_manifest_hash"), "initial_manifest_hash"
            ),
            posture=cast(FirmwarePosture, posture),
            provisioned_at_ms=_require_non_negative_int(
                payload.get("provisioned_at_ms"), "provisioned_at_ms"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "device_id": self.device_id,
            "public_key_b64": self.public_key_b64,
            "initial_manifest_hash": self.initial_manifest_hash,
            "posture": self.posture,
            "provisioned_at_ms": self.provisioned_at_ms,
        }


@dataclass(frozen=True, slots=True)
class FirmwareFreshnessState:
    """Caller-persisted high-water mark for one device and public-key epoch."""

    device_id: str
    boot_id: int
    seq: int
    device_uptime_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "device_id", _require_device_id(self.device_id))
        object.__setattr__(
            self, "boot_id", _require_non_negative_int(self.boot_id, "boot_id")
        )
        object.__setattr__(self, "seq", _require_non_negative_int(self.seq, "seq"))
        object.__setattr__(
            self,
            "device_uptime_ms",
            _require_non_negative_int(self.device_uptime_ms, "device_uptime_ms"),
        )


@dataclass(frozen=True, slots=True)
class FirmwareFreshnessVerdict:
    """Pure replay/rollback decision; callers decide if and how to persist it."""

    accepted: bool
    next_state: FirmwareFreshnessState | None
    error_code: FirmwareErrorCode | None = None
    error_detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ValueError("accepted must be a boolean")
        if not isinstance(self.error_detail, str):
            raise ValueError("error_detail must be a string")
        if self.accepted:
            if not isinstance(self.next_state, FirmwareFreshnessState):
                raise ValueError("accepted verdict requires next_state")
            if self.error_code is not None or self.error_detail:
                raise ValueError("accepted verdict cannot carry an error")
            return
        if self.next_state is not None:
            raise ValueError("rejected verdict cannot advance freshness state")
        if self.error_code not in {
            "sequence_replay",
            "boot_rollback",
            "invalid_envelope",
        }:
            raise ValueError("rejected verdict requires a freshness error code")


FirmwareUnsignedPayload: TypeAlias = (
    FirmwareCapabilityManifest
    | FirmwareTelemetryEnvelope
    | FirmwareHeartbeatEnvelope
    | FirmwareFaultEvent
)
FirmwareSequencedPayload: TypeAlias = (
    FirmwareTelemetryEnvelope | FirmwareHeartbeatEnvelope | FirmwareFaultEvent
)


def canonical_firmware_json_bytes(payload: FirmwareUnsignedPayload) -> bytes:
    """Return the exact cross-language signed bytes for a validated model."""

    if not isinstance(
        payload,
        (
            FirmwareCapabilityManifest,
            FirmwareTelemetryEnvelope,
            FirmwareHeartbeatEnvelope,
            FirmwareFaultEvent,
        ),
    ):
        raise TypeError("payload must be a firmware telemetry unsigned model")
    try:
        return json.dumps(
            payload.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise FirmwareTelemetryError("invalid_envelope", str(exc)) from exc


def firmware_manifest_hash(manifest: FirmwareCapabilityManifest) -> str:
    """Return the specs-owned ``sha256:<hex>`` capability hash."""

    if not isinstance(manifest, FirmwareCapabilityManifest):
        raise TypeError("manifest must be a FirmwareCapabilityManifest")
    digest = hashlib.sha256(canonical_firmware_json_bytes(manifest)).hexdigest()
    return _HASH_PREFIX + digest


def verify_firmware_signature(
    payload: FirmwareUnsignedPayload,
    signature: str,
    public_key_b64: str,
) -> None:
    """Verify one model's signature against an explicit anchored public key."""

    _, public_key = _decode_public_key(public_key_b64)
    _, signature_bytes = _decode_signature(signature)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature_bytes, canonical_firmware_json_bytes(payload)
        )
    except (InvalidSignature, ValueError) as exc:
        raise FirmwareTelemetryError(
            "signature_verification_failed", "signature does not verify"
        ) from exc


def verify_firmware_manifest(
    message: SignedFirmwareCapabilityManifest,
    anchor: FirmwareProvisioningAnchor,
    *,
    expected_manifest_hash: str | None = None,
) -> str:
    """Verify a signed manifest against an off-device provisioning anchor.

    By default the initial hash is pinned. A caller handling an explicitly
    approved capability update may provide that accepted hash instead.
    """

    if not isinstance(message, SignedFirmwareCapabilityManifest):
        raise TypeError("message must be a SignedFirmwareCapabilityManifest")
    if not isinstance(anchor, FirmwareProvisioningAnchor):
        raise TypeError("anchor must be a FirmwareProvisioningAnchor")
    manifest = message.manifest
    if manifest.device_id != anchor.device_id:
        raise FirmwareTelemetryError(
            "unknown_device", "manifest device_id does not match anchor"
        )
    if manifest.public_key_b64 != anchor.public_key_b64:
        raise FirmwareTelemetryError(
            "public_key_mismatch", "manifest public key does not match anchor"
        )
    if manifest.posture != anchor.posture:
        raise FirmwareTelemetryError(
            "invalid_posture", "manifest posture does not match anchor"
        )
    pinned_hash = (
        anchor.initial_manifest_hash
        if expected_manifest_hash is None
        else _require_hash(expected_manifest_hash, "expected_manifest_hash")
    )
    if message.manifest_hash != pinned_hash:
        raise FirmwareTelemetryError(
            "capability_hash_mismatch", "manifest hash does not match accepted pin"
        )
    verify_firmware_signature(manifest, message.signature, anchor.public_key_b64)
    return message.manifest_hash


def evaluate_firmware_freshness(
    payload: FirmwareSequencedPayload,
    previous_state: FirmwareFreshnessState | None,
) -> FirmwareFreshnessVerdict:
    """Evaluate monotonic boot, sequence, and same-boot uptime constraints."""

    if not isinstance(
        payload,
        (FirmwareTelemetryEnvelope, FirmwareHeartbeatEnvelope, FirmwareFaultEvent),
    ):
        raise TypeError("payload must be a sequenced firmware model")
    if previous_state is not None and not isinstance(
        previous_state, FirmwareFreshnessState
    ):
        raise TypeError("previous_state must be FirmwareFreshnessState or None")
    if previous_state is not None:
        if payload.device_id != previous_state.device_id:
            return FirmwareFreshnessVerdict(
                accepted=False,
                next_state=None,
                error_code="invalid_envelope",
                error_detail="freshness state belongs to a different device",
            )
        if payload.boot_id < previous_state.boot_id:
            return FirmwareFreshnessVerdict(
                accepted=False,
                next_state=None,
                error_code="boot_rollback",
                error_detail=(f"boot_id {payload.boot_id} < {previous_state.boot_id}"),
            )
        if payload.seq <= previous_state.seq:
            return FirmwareFreshnessVerdict(
                accepted=False,
                next_state=None,
                error_code="sequence_replay",
                error_detail=f"seq {payload.seq} <= {previous_state.seq}",
            )
        if (
            payload.boot_id == previous_state.boot_id
            and payload.device_uptime_ms < previous_state.device_uptime_ms
        ):
            return FirmwareFreshnessVerdict(
                accepted=False,
                next_state=None,
                error_code="invalid_envelope",
                error_detail="device_uptime_ms decreased without a new boot_id",
            )
    return FirmwareFreshnessVerdict(
        accepted=True,
        next_state=FirmwareFreshnessState(
            device_id=payload.device_id,
            boot_id=payload.boot_id,
            seq=payload.seq,
            device_uptime_ms=payload.device_uptime_ms,
        ),
    )


def _verify_event_binding(
    payload: FirmwareSequencedPayload,
    signature: str,
    anchor: FirmwareProvisioningAnchor,
    accepted_manifest: FirmwareCapabilityManifest,
    previous_state: FirmwareFreshnessState | None,
) -> FirmwareFreshnessState:
    if not isinstance(anchor, FirmwareProvisioningAnchor):
        raise TypeError("anchor must be a FirmwareProvisioningAnchor")
    if not isinstance(accepted_manifest, FirmwareCapabilityManifest):
        raise TypeError("accepted_manifest must be a FirmwareCapabilityManifest")
    if previous_state is not None and not isinstance(
        previous_state, FirmwareFreshnessState
    ):
        raise TypeError("previous_state must be FirmwareFreshnessState or None")
    if payload.device_id != anchor.device_id:
        raise FirmwareTelemetryError(
            "unknown_device", "payload device_id does not match anchor"
        )
    if payload.posture != anchor.posture:
        raise FirmwareTelemetryError(
            "invalid_posture", "payload posture does not match anchor"
        )
    if accepted_manifest.device_id != anchor.device_id:
        raise FirmwareTelemetryError(
            "unknown_device", "accepted manifest belongs to a different device"
        )
    if accepted_manifest.public_key_b64 != anchor.public_key_b64:
        raise FirmwareTelemetryError(
            "public_key_mismatch", "accepted manifest key does not match anchor"
        )
    if accepted_manifest.posture != anchor.posture:
        raise FirmwareTelemetryError(
            "invalid_posture", "accepted manifest posture does not match anchor"
        )
    if payload.capability_hash != firmware_manifest_hash(accepted_manifest):
        raise FirmwareTelemetryError(
            "capability_hash_mismatch",
            "payload capability hash does not match accepted manifest",
        )
    verify_firmware_signature(payload, signature, anchor.public_key_b64)
    verdict = evaluate_firmware_freshness(payload, previous_state)
    if not verdict.accepted:
        assert verdict.error_code is not None
        raise FirmwareTelemetryError(verdict.error_code, verdict.error_detail)
    assert verdict.next_state is not None
    return verdict.next_state


def _validate_readings_against_manifest(
    readings: tuple[FirmwareTelemetryReading, ...],
    manifest: FirmwareCapabilityManifest,
) -> None:
    channels = {channel.channel: channel for channel in manifest.channels}
    for index, reading in enumerate(readings):
        expected = channels.get(reading.channel)
        if expected is None:
            raise FirmwareTelemetryError(
                "unsupported_channel",
                f"reading {index} channel {reading.channel!r} is not in the accepted manifest",
            )
        if reading.sensor_type != expected.sensor_type or reading.unit != expected.unit:
            raise FirmwareTelemetryError(
                "invalid_reading",
                f"reading {index} does not match the accepted manifest channel",
            )
        if reading.quality < expected.quality_floor:
            raise FirmwareTelemetryError(
                "invalid_reading", f"reading {index} quality is below manifest floor"
            )


def verify_firmware_telemetry(
    message: SignedFirmwareTelemetry,
    *,
    anchor: FirmwareProvisioningAnchor,
    accepted_manifest: FirmwareCapabilityManifest,
    previous_state: FirmwareFreshnessState | None = None,
) -> FirmwareFreshnessState:
    """Verify measurement telemetry and return the caller's next pure state."""

    if not isinstance(message, SignedFirmwareTelemetry):
        raise TypeError("message must be SignedFirmwareTelemetry")
    state = _verify_event_binding(
        message.envelope,
        message.signature,
        anchor,
        accepted_manifest,
        previous_state,
    )
    _validate_readings_against_manifest(message.envelope.readings, accepted_manifest)
    return state


def verify_firmware_heartbeat(
    message: SignedFirmwareHeartbeat,
    *,
    anchor: FirmwareProvisioningAnchor,
    accepted_manifest: FirmwareCapabilityManifest,
    previous_state: FirmwareFreshnessState | None = None,
) -> FirmwareFreshnessState:
    """Verify liveness evidence without constructing a measurement."""

    if not isinstance(message, SignedFirmwareHeartbeat):
        raise TypeError("message must be SignedFirmwareHeartbeat")
    return _verify_event_binding(
        message.envelope,
        message.signature,
        anchor,
        accepted_manifest,
        previous_state,
    )


def verify_firmware_fault_event(
    message: SignedFirmwareFaultEvent,
    *,
    anchor: FirmwareProvisioningAnchor,
    accepted_manifest: FirmwareCapabilityManifest,
    previous_state: FirmwareFreshnessState | None = None,
) -> FirmwareFreshnessState:
    """Verify signed fault evidence without interpreting it as telemetry/action."""

    if not isinstance(message, SignedFirmwareFaultEvent):
        raise TypeError("message must be SignedFirmwareFaultEvent")
    return _verify_event_binding(
        message.fault,
        message.signature,
        anchor,
        accepted_manifest,
        previous_state,
    )


__all__ = [
    "FIRMWARE_DEVICE_ID_MAX_LENGTH",
    "FIRMWARE_FAULT_TOKEN_MAX_LENGTH",
    "FIRMWARE_JSON_SAFE_INT_MAX",
    "FIRMWARE_SIGNATURE_ALGORITHM",
    "FIRMWARE_SIGNATURE_PREFIX",
    "FIRMWARE_TELEMETRY_VERSION",
    "FirmwareActionAuthority",
    "FirmwareCapabilityManifest",
    "FirmwareChannelProtocol",
    "FirmwareDeviceMode",
    "FirmwareErrorCode",
    "FirmwareFaultCode",
    "FirmwareFaultEvent",
    "FirmwareFreshnessState",
    "FirmwareFreshnessVerdict",
    "FirmwareHeartbeatEnvelope",
    "FirmwareKeyStorage",
    "FirmwareManifestAction",
    "FirmwareManifestChannel",
    "FirmwareManifestInterlock",
    "FirmwarePosture",
    "FirmwareProvisioningAnchor",
    "FirmwareSequencedPayload",
    "FirmwareTelemetryEnvelope",
    "FirmwareTelemetryError",
    "FirmwareTelemetryReading",
    "FirmwareTransport",
    "FirmwareUnsignedPayload",
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
]
