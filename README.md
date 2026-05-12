# ori-sdk-python

Python SDK for Ori runtime integrations and community skill tooling.

## Scope (bootstrap)

This repository intentionally ships a thin, stable v1 bootstrap surface:

- Typed models for `runtime-health/v1` and `gateway-api/v1` contracts.
- Local Unix-socket runtime health client (sync + async).
- Skill metadata validation helpers aligned with runtime loader invariants.
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

## Validation Example

```python
from pathlib import Path
from ori_sdk.validation import validate_skill_metadata_file

validate_skill_metadata_file(Path("skills/my-skill/skill.yaml"))
```

## Compatibility

- Python `3.11` and `3.12`

## Contract Compatibility Matrix

| SDK version | Runtime baseline | Specs baseline |
|---|---|---|
| `0.1.x` | `v0.9.0-beta.2+` | `ori-specs v1` |

The SDK mirrors contracts from `ori-specs` and must not import from runtime internals.

## License

Apache-2.0
