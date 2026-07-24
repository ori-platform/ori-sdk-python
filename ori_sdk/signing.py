# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Profile-separated Ed25519 signing for community skill packages.

The artifact profile signs exact opaque bytes before extraction. The manifest
profile signs canonical JSON derived from a parsed ``skill.yaml`` mapping.
Their APIs are deliberately separate so callers cannot confuse trust domains.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Final, TypedDict, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ori_sdk.errors import (
    ORI_SDK_ARTIFACT_DIGEST_MISMATCH,
    ORI_SDK_BUNDLED_SIGNATURE_NOT_ALLOWED,
    ORI_SDK_INVALID_ARTIFACT_SIGNATURE_METADATA,
    ORI_SDK_INVALID_MANIFEST,
    ORI_SDK_INVALID_PRIVATE_KEY,
    ORI_SDK_INVALID_PUBLIC_KEY,
    ORI_SDK_INVALID_SIGNATURE_FORMAT,
    ORI_SDK_SIGNATURE_VERIFICATION_FAILED,
    SkillSigningError,
)

SIGNATURE_PREFIX: Final = "ed25519:"
ARTIFACT_DIGEST_PREFIX: Final = "sha256:"
ARTIFACT_SIGNATURE_SCHEMA: Final = "ori.skill_artifact_signature.v1"
BUNDLED_SENTINEL: Final = "bundled"
_SIGNATURE_LENGTH: Final = 64
_PUBLIC_KEY_LENGTH: Final = 32
_PRIVATE_KEY_LENGTH: Final = 32


class ArtifactSignatureMetadata(TypedDict):
    """Strict detached metadata for an exact-byte artifact signature."""

    artifact_sha256: str
    schema: str
    signature: str


def _decode_standard_base64(
    value: str,
    *,
    expected_length: int,
    code: str,
    field_name: str,
) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SkillSigningError(
            f"{field_name} is not canonical standard base64", code=code
        ) from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        raise SkillSigningError(
            f"{field_name} is not canonical padded standard base64", code=code
        )
    if len(decoded) != expected_length:
        raise SkillSigningError(
            f"{field_name} must decode to {expected_length} bytes", code=code
        )
    return decoded


def _decode_signature(signature: str) -> bytes:
    if signature == BUNDLED_SENTINEL:
        raise SkillSigningError(
            "bundled is not valid for community signatures",
            code=ORI_SDK_BUNDLED_SIGNATURE_NOT_ALLOWED,
        )
    if not signature.startswith(SIGNATURE_PREFIX):
        raise SkillSigningError(
            "signature must use the exact ed25519: prefix",
            code=ORI_SDK_INVALID_SIGNATURE_FORMAT,
        )
    return _decode_standard_base64(
        signature[len(SIGNATURE_PREFIX) :],
        expected_length=_SIGNATURE_LENGTH,
        code=ORI_SDK_INVALID_SIGNATURE_FORMAT,
        field_name="signature",
    )


def _load_public_key(public_key_b64: str) -> Ed25519PublicKey:
    public_key_bytes = _decode_standard_base64(
        public_key_b64,
        expected_length=_PUBLIC_KEY_LENGTH,
        code=ORI_SDK_INVALID_PUBLIC_KEY,
        field_name="public key",
    )
    try:
        return Ed25519PublicKey.from_public_bytes(public_key_bytes)
    except ValueError as exc:
        raise SkillSigningError(
            "public key is not a valid Ed25519 public key",
            code=ORI_SDK_INVALID_PUBLIC_KEY,
        ) from exc


def _load_private_key(private_key_bytes: bytes) -> Ed25519PrivateKey:
    if len(private_key_bytes) != _PRIVATE_KEY_LENGTH:
        raise SkillSigningError(
            "private key seed must be exactly 32 bytes",
            code=ORI_SDK_INVALID_PRIVATE_KEY,
        )
    try:
        return Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    except ValueError as exc:
        raise SkillSigningError(
            "private key seed is not valid Ed25519 material",
            code=ORI_SDK_INVALID_PRIVATE_KEY,
        ) from exc


def _wire_signature(signature_bytes: bytes) -> str:
    return SIGNATURE_PREFIX + base64.b64encode(signature_bytes).decode("ascii")


def sign_artifact(
    artifact_bytes: bytes, private_key_bytes: bytes
) -> ArtifactSignatureMetadata:
    """Sign exact artifact bytes and return strict detached metadata."""

    signature = _load_private_key(private_key_bytes).sign(artifact_bytes)
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    return {
        "artifact_sha256": ARTIFACT_DIGEST_PREFIX + digest,
        "schema": ARTIFACT_SIGNATURE_SCHEMA,
        "signature": _wire_signature(signature),
    }


def _parse_artifact_metadata(
    metadata: Mapping[str, object],
) -> ArtifactSignatureMetadata:
    expected_fields = {"artifact_sha256", "schema", "signature"}
    if set(metadata) != expected_fields:
        raise SkillSigningError(
            "artifact signature metadata must contain exactly the v1 fields",
            code=ORI_SDK_INVALID_ARTIFACT_SIGNATURE_METADATA,
        )
    if not all(isinstance(metadata[field], str) for field in expected_fields):
        raise SkillSigningError(
            "artifact signature metadata fields must be strings",
            code=ORI_SDK_INVALID_ARTIFACT_SIGNATURE_METADATA,
        )
    parsed = cast(ArtifactSignatureMetadata, dict(metadata))
    if parsed["schema"] != ARTIFACT_SIGNATURE_SCHEMA:
        raise SkillSigningError(
            "unsupported artifact signature metadata schema",
            code=ORI_SDK_INVALID_ARTIFACT_SIGNATURE_METADATA,
        )
    digest = parsed["artifact_sha256"]
    if (
        not digest.startswith(ARTIFACT_DIGEST_PREFIX)
        or len(digest) != len(ARTIFACT_DIGEST_PREFIX) + 64
        or any(character not in "0123456789abcdef" for character in digest[7:])
    ):
        raise SkillSigningError(
            "artifact_sha256 must use sha256: followed by 64 lowercase hex digits",
            code=ORI_SDK_INVALID_ARTIFACT_SIGNATURE_METADATA,
        )
    return parsed


def verify_artifact_signature(
    artifact_bytes: bytes,
    metadata: Mapping[str, object],
    public_key_b64: str,
) -> None:
    """Verify detached metadata and signature over exact artifact bytes.

    ``metadata`` must already be parsed. Callers that originate it as JSON are
    responsible for rejecting duplicate object fields during parsing.
    """

    parsed = _parse_artifact_metadata(metadata)
    actual_digest = ARTIFACT_DIGEST_PREFIX + hashlib.sha256(artifact_bytes).hexdigest()
    if parsed["artifact_sha256"] != actual_digest:
        raise SkillSigningError(
            "artifact digest does not match the exact received bytes",
            code=ORI_SDK_ARTIFACT_DIGEST_MISMATCH,
        )
    signature = _decode_signature(parsed["signature"])
    public_key = _load_public_key(public_key_b64)
    try:
        public_key.verify(signature, artifact_bytes)
    except InvalidSignature as exc:
        raise SkillSigningError(
            "artifact signature verification failed",
            code=ORI_SDK_SIGNATURE_VERIFICATION_FAILED,
        ) from exc


def _validate_json_value(value: object, *, ancestors: set[int]) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SkillSigningError(
                "manifest contains a non-finite number",
                code=ORI_SDK_INVALID_MANIFEST,
            )
        return
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in ancestors:
            raise SkillSigningError(
                "manifest contains a cycle", code=ORI_SDK_INVALID_MANIFEST
            )
        ancestors.add(identity)
        try:
            for key, nested in value.items():
                if not isinstance(key, str):
                    raise SkillSigningError(
                        "manifest mapping keys must be strings",
                        code=ORI_SDK_INVALID_MANIFEST,
                    )
                _validate_json_value(nested, ancestors=ancestors)
        finally:
            ancestors.remove(identity)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        identity = id(value)
        if identity in ancestors:
            raise SkillSigningError(
                "manifest contains a cycle", code=ORI_SDK_INVALID_MANIFEST
            )
        ancestors.add(identity)
        try:
            for nested in value:
                _validate_json_value(nested, ancestors=ancestors)
        finally:
            ancestors.remove(identity)
        return
    raise SkillSigningError(
        f"manifest contains non-JSON value of type {type(value).__name__}",
        code=ORI_SDK_INVALID_MANIFEST,
    )


def canonical_manifest_bytes(parsed_skill: Mapping[str, object]) -> bytes:
    """Return canonical unsigned manifest bytes for the manifest profile."""

    _validate_json_value(parsed_skill, ancestors=set())
    unsigned = {key: value for key, value in parsed_skill.items() if key != "signature"}
    return json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sign_manifest(parsed_skill: Mapping[str, object], private_key_bytes: bytes) -> str:
    """Sign the canonical unsigned manifest profile."""

    signature = _load_private_key(private_key_bytes).sign(
        canonical_manifest_bytes(parsed_skill)
    )
    return _wire_signature(signature)


def verify_manifest_signature(
    parsed_skill: Mapping[str, object], public_key_b64: str
) -> None:
    """Verify the embedded signature over canonical manifest bytes."""

    signature_field = parsed_skill.get("signature")
    if not isinstance(signature_field, str):
        raise SkillSigningError(
            "manifest signature must be a string",
            code=ORI_SDK_INVALID_SIGNATURE_FORMAT,
        )
    signature = _decode_signature(signature_field)
    public_key = _load_public_key(public_key_b64)
    try:
        public_key.verify(signature, canonical_manifest_bytes(parsed_skill))
    except InvalidSignature as exc:
        raise SkillSigningError(
            "manifest signature verification failed",
            code=ORI_SDK_SIGNATURE_VERIFICATION_FAILED,
        ) from exc
