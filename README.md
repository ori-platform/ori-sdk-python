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

## Compatibility

- Python `3.11` and `3.12`

## Contract Compatibility Matrix

| SDK version | Runtime baseline | Specs baseline |
|---|---|---|
| `0.1.x` | [`ori-runtime`](https://github.com/ori-platform/ori-runtime) `v2.0.0+` health, gateway, and skill-loader contracts | [`ori-specs`](https://github.com/ori-platform/ori-specs) `v1` |

The SDK mirrors contracts from [`ori-specs`](https://github.com/ori-platform/ori-specs) and must not import from [`ori-runtime`](https://github.com/ori-platform/ori-runtime) internals.
Skill package validation targets runtime `v2.0.0+`. Legacy v0.9 packages using
`escalate_to: cloud` must migrate to `escalate_to: gateway`; cloud reasoning is
gateway-mediated in the current contract.

## License

Apache-2.0
