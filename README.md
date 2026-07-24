# ori-sdk-python

Python SDK for [Ori runtime](https://github.com/ori-platform/ori-runtime) integrations and community skill tooling.

## Scope (bootstrap)

This repository intentionally ships a thin, stable v1 bootstrap surface:

- Typed models for [`runtime-health/v1`](https://github.com/ori-platform/ori-specs/blob/main/runtime-health/v1.md) and [`gateway-api/v1`](https://github.com/ori-platform/ori-specs/blob/main/gateway-api/v1.md) contracts.
- Local Unix-socket [`ori-runtime`](https://github.com/ori-platform/ori-runtime) health client (sync + async).
- Immutable skill package models and validation aligned with the
  [`skills-package/v1`](https://github.com/ori-platform/ori-specs/blob/main/skills-package/v1.md)
  contract and runtime loader invariants.
- Gateway topic + request/response helper utilities with `request_id` integrity.
- Product-neutral direct runtime telemetry models with specs-aligned canonical
  JSON bytes and pure HMAC primitives.
- Immutable firmware Layer 1 capability, telemetry, heartbeat, fault, and
  provisioning models with canonical Ed25519 verification and pure freshness
  checks.

Out of scope for this bootstrap:

- Decorator-based skill authoring.
- Local skill execution harness.

These are explicitly deferred and not included in this release branch. Consumers
should not depend on these APIs yet.

Those are post-v1 additions after field usage patterns stabilize.

## Install (local dev)

```bash
pip install -e ".[dev]"
pre-commit install
```

## Quick Example

```python
from ori_sdk.health import RuntimeHealthClient

client = RuntimeHealthClient()
response = client.get_health()

if response.ok and response.health is not None:
    print(response.health.device_id, response.health.uptime_s)
else:
    print(response.error)
```

## Extended Health Helpers

```python
from ori_sdk import (
    RuntimeHealthClient,
    alert_channel_summary,
    evidence_summary,
    runtime_posture_summary,
    sensor_freshness_delta,
    tier_capability_summary,
)

response = RuntimeHealthClient().get_health()
if not response.ok or response.health is None:
    raise RuntimeError("runtime health is unavailable")

status = response.health
freshness = sensor_freshness_delta(status)
alerts = alert_channel_summary(status)
tiers = tier_capability_summary(status)
evidence = evidence_summary(status)
posture = runtime_posture_summary(status)
```

These helpers consume typed `HealthStatus` snapshots and return plain
dictionaries described by exported `TypedDict` result types. They are read-only
diagnostics: tier authority remains a runtime concern, alert availability does
not prove provider delivery, and broad posture summaries omit remote-command
sender identities. Gateway and Local SLM state is reasoning/enrichment posture,
not physical-action authority; cloud providers remain gateway backends.

`posture_interpretation()` is deprecated because its original tier mapping
predates the runtime v2 authority model. Its signature, `PostureReport` return
type, and behavior remain available for compatibility.

## Skill Package Example

```python
from pathlib import Path
from ori_sdk import SkillYamlNormaliser

package = SkillYamlNormaliser.load_and_validate(
    Path("skills/my-skill/skill.yaml")
)
print(package.name, package.triggers[0].action_tier)
```

The legacy `validate_skill_metadata*` helpers remain available for callers that
need the original mapping return type.

## Gateway API v1 Models

```python
from ori_sdk import RuntimeExportRequest, export_request_topic

request = RuntimeExportRequest(
    request_id="report-2026-07",
    export_type="sensor_history",
    device_id="site-a-edge-01",
    since_ms=1717000000000,
    until_ms=1717600000000,
    limit=500,
    params={"sensor_id": "current-main", "bucket_ms": 3600000},
)

print(export_request_topic(request.device_id), request.to_dict())
```

Gateway models represent logical payloads after transport authentication and
decryption. They do not model HMAC or AES-GCM envelopes, open MQTT connections,
or grant mutation or actuation authority. Runtime exports are read-only, and
Tier C enrichment remains advisory.

## Direct Runtime Telemetry

```python
from ori_sdk import (
    RuntimeTelemetryBatch,
    canonical_telemetry_bytes,
    telemetry_hmac_sha256,
)

batch = RuntimeTelemetryBatch.from_dict(payload)
body = canonical_telemetry_bytes(batch)
signature_hex = telemetry_hmac_sha256(api_key, timestamp_ms, body)
```

The telemetry models mirror the observational `runtime.telemetry.v1` body and
its cross-language canonical byte contract. The HMAC helper is a pure signing
primitive: it does not load credentials, build authorization headers, select an
endpoint, or send data. Telemetry remains product-neutral and grants no runtime
mutation or actuation authority.

## Firmware Layer 1 Telemetry

```python
from ori_sdk import (
    FirmwareProvisioningAnchor,
    SignedFirmwareCapabilityManifest,
    canonical_firmware_json_bytes,
    verify_firmware_manifest,
)

anchor = FirmwareProvisioningAnchor.from_dict(anchor_payload)
message = SignedFirmwareCapabilityManifest.from_dict(manifest_payload)
manifest_hash = verify_firmware_manifest(message, anchor)
signed_bytes = canonical_firmware_json_bytes(message.manifest)
```

These models mirror `firmware-telemetry/v1` and keep measurement telemetry,
zero-reading heartbeats, and signed fault evidence as distinct types. The
verification and freshness helpers are pure: callers retain responsibility for
durably storing high-water marks and for using ori-runtime's
`FirmwareTelemetryGate` when ingesting readings. Faults and local firmware
interlocks remain evidence and defense-in-depth; they do not grant Tier C or
Tier D action authority.

## Compatibility

- Python `3.11` and `3.12`

## Contract Compatibility Matrix

| SDK version | Runtime baseline | Specs baseline |
|---|---|---|
| `0.1.x` | [`ori-runtime`](https://github.com/ori-platform/ori-runtime) `v2.0.0+` health, gateway, telemetry, and skill-loader contracts | [`ori-specs`](https://github.com/ori-platform/ori-specs) `v1` |

The SDK mirrors contracts from [`ori-specs`](https://github.com/ori-platform/ori-specs) and must not import from [`ori-runtime`](https://github.com/ori-platform/ori-runtime) internals.
Skill package validation targets runtime `v2.0.0+`. Legacy v0.9 packages using
`escalate_to: cloud` must migrate to `escalate_to: gateway`; cloud reasoning is
gateway-mediated in the current contract.

## License

Apache-2.0
