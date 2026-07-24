# Copyright 2026 Ori Nexus Systems LTD
# SPDX-License-Identifier: Apache-2.0

"""Cross-repository tests for both skill-signing v1 profiles."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

import ori_sdk
from ori_sdk.errors import (
    ORI_SDK_ARTIFACT_DIGEST_MISMATCH,
    ORI_SDK_BUNDLED_SIGNATURE_NOT_ALLOWED,
    ORI_SDK_INVALID_ARTIFACT_SIGNATURE_METADATA,
    ORI_SDK_INVALID_MANIFEST,
    ORI_SDK_INVALID_PRIVATE_KEY,
    ORI_SDK_SIGNATURE_VERIFICATION_FAILED,
    SkillSigningError,
)
from ori_sdk.signing import (
    ArtifactSignatureMetadata,
    canonical_manifest_bytes,
    sign_artifact,
    sign_manifest,
    verify_artifact_signature,
    verify_manifest_signature,
)

VECTOR_PATH = Path(__file__).parent / "fixtures" / "skill_signing_vectors_v1.json"
VECTOR_SHA256 = "13832babac98468ddd368aafd04c5140bba771f568500c50d4bac60c8588fddc"
VECTORS = cast(dict[str, object], json.loads(VECTOR_PATH.read_text(encoding="utf-8")))
PUBLIC_KEY_B64 = cast(str, VECTORS["public_key_b64"])
PRIVATE_SEED = base64.b64decode(cast(str, VECTORS["private_seed_b64"]))
MANIFEST_PROFILE = cast(dict[str, object], VECTORS["manifest_profile"])
ARTIFACT_PROFILE = cast(dict[str, object], VECTORS["artifact_profile"])
PARSED_SKILL = cast(dict[str, object], MANIFEST_PROFILE["parsed_skill"])
ARTIFACT_BYTES = base64.b64decode(cast(str, ARTIFACT_PROFILE["artifact_bytes_b64"]))
ARTIFACT_METADATA = cast(
    ArtifactSignatureMetadata, ARTIFACT_PROFILE["detached_metadata"]
)


def test_signing_api_is_publicly_exported() -> None:
    expected = {
        "ArtifactSignatureMetadata",
        "SkillSigningError",
        "canonical_manifest_bytes",
        "sign_artifact",
        "sign_manifest",
        "verify_artifact_signature",
        "verify_manifest_signature",
    }
    assert expected <= set(ori_sdk.__all__)


def test_shared_vector_file_is_byte_identical() -> None:
    assert hashlib.sha256(VECTOR_PATH.read_bytes()).hexdigest() == VECTOR_SHA256


def test_manifest_vector_canonical_bytes_hash_and_signature() -> None:
    canonical = canonical_manifest_bytes(PARSED_SKILL)
    assert base64.b64encode(canonical).decode("ascii") == cast(
        str, MANIFEST_PROFILE["canonical_unsigned_b64"]
    )
    assert hashlib.sha256(canonical).hexdigest() == cast(
        str, MANIFEST_PROFILE["canonical_unsigned_sha256"]
    )

    signed = dict(PARSED_SKILL)
    signed["signature"] = MANIFEST_PROFILE["signature"]
    verify_manifest_signature(signed, PUBLIC_KEY_B64)


def test_artifact_vector_digest_and_signature() -> None:
    verify_artifact_signature(ARTIFACT_BYTES, ARTIFACT_METADATA, PUBLIC_KEY_B64)


def test_signing_round_trips_match_shared_vectors() -> None:
    assert sign_manifest(PARSED_SKILL, PRIVATE_SEED) == MANIFEST_PROFILE["signature"]
    assert sign_artifact(ARTIFACT_BYTES, PRIVATE_SEED) == ARTIFACT_METADATA


def test_signing_rejects_invalid_private_key_with_private_key_code() -> None:
    with pytest.raises(SkillSigningError) as error:
        sign_artifact(ARTIFACT_BYTES, b"short")
    assert error.value.code == ORI_SDK_INVALID_PRIVATE_KEY


def test_profiles_cannot_be_substituted() -> None:
    wrong_artifact_metadata = dict(ARTIFACT_METADATA)
    wrong_artifact_metadata["signature"] = cast(str, MANIFEST_PROFILE["signature"])
    with pytest.raises(SkillSigningError) as artifact_error:
        verify_artifact_signature(
            ARTIFACT_BYTES, wrong_artifact_metadata, PUBLIC_KEY_B64
        )
    assert artifact_error.value.code == ORI_SDK_SIGNATURE_VERIFICATION_FAILED

    wrong_manifest = dict(PARSED_SKILL)
    wrong_manifest["signature"] = ARTIFACT_PROFILE["signature"]
    with pytest.raises(SkillSigningError) as manifest_error:
        verify_manifest_signature(wrong_manifest, PUBLIC_KEY_B64)
    assert manifest_error.value.code == ORI_SDK_SIGNATURE_VERIFICATION_FAILED


def test_artifact_tamper_fails_at_digest_before_signature() -> None:
    with pytest.raises(SkillSigningError) as error:
        verify_artifact_signature(
            ARTIFACT_BYTES + b"!", ARTIFACT_METADATA, PUBLIC_KEY_B64
        )
    assert error.value.code == ORI_SDK_ARTIFACT_DIGEST_MISMATCH


def test_artifact_metadata_is_strict() -> None:
    metadata: dict[str, object] = dict(ARTIFACT_METADATA)
    metadata["signer"] = "untrusted-label"
    with pytest.raises(SkillSigningError) as error:
        verify_artifact_signature(ARTIFACT_BYTES, metadata, PUBLIC_KEY_B64)
    assert error.value.code == ORI_SDK_INVALID_ARTIFACT_SIGNATURE_METADATA


def test_bundled_is_rejected_for_both_community_profiles() -> None:
    metadata = dict(ARTIFACT_METADATA)
    metadata["signature"] = "bundled"
    with pytest.raises(SkillSigningError) as artifact_error:
        verify_artifact_signature(ARTIFACT_BYTES, metadata, PUBLIC_KEY_B64)
    assert artifact_error.value.code == ORI_SDK_BUNDLED_SIGNATURE_NOT_ALLOWED

    manifest = dict(PARSED_SKILL)
    manifest["signature"] = "bundled"
    with pytest.raises(SkillSigningError) as manifest_error:
        verify_manifest_signature(manifest, PUBLIC_KEY_B64)
    assert manifest_error.value.code == ORI_SDK_BUNDLED_SIGNATURE_NOT_ALLOWED


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), object()])
def test_manifest_rejects_non_json_values(invalid_value: object) -> None:
    manifest = dict(PARSED_SKILL)
    manifest["invalid"] = invalid_value
    with pytest.raises(SkillSigningError) as error:
        canonical_manifest_bytes(manifest)
    assert error.value.code == ORI_SDK_INVALID_MANIFEST


def test_manifest_rejects_non_string_keys_and_cycles() -> None:
    non_string_key: dict[object, object] = {1: "value"}
    with pytest.raises(SkillSigningError) as key_error:
        canonical_manifest_bytes(cast(dict[str, object], non_string_key))
    assert key_error.value.code == ORI_SDK_INVALID_MANIFEST

    cyclic = copy.deepcopy(PARSED_SKILL)
    cyclic["cycle"] = cyclic
    with pytest.raises(SkillSigningError) as cycle_error:
        canonical_manifest_bytes(cyclic)
    assert cycle_error.value.code == ORI_SDK_INVALID_MANIFEST
