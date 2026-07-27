# ori-sdk-python

Python SDK for building integrations with the Ori runtime, Gateway consumers, and community skill tooling.

> ## Table of contents

- [Overview](#overview)
- [Design principles](#design-principles)
- [Scope](#scope)
- [Technologies](#technologies)
- [Project setup](#project-setup)
- [Using the SDK](#using-the-sdk)
  - [Read runtime health](#read-runtime-health)
  - [Validate skill packages](#validate-skill-packages)
  - [Describe deployments](#describe-deployments)
  - [Build gateway messages](#build-gateway-messages)
  - [Build runtime telemetry](#build-runtime-telemetry)
  - [Verify firmware telemetry](#verify-firmware-telemetry)
  - [Sign artifacts and manifests](#sign-artifacts-and-manifests)
- [Verification checklist](#verification-checklist)
  - [Tests](#tests)
  - [Code quality](#code-quality)
  - [Repository checks](#repository-checks)
- [Contract compatibility](#contract-compatibility)
- [Contributing](#contributing)
  - [Contribution rules](#contribution-rules)
  - [Recommended contribution workflow](#recommended-contribution-workflow)
- [Security and distribution](#security-and-distribution)
- [Project links](#project-links)
- [Status](#status)
- [License](#license)

> ## Overview

Ori is made up of several applications that exchange structured health, gateway, skill, telemetry, and firmware data. `ori-sdk-python` provides shared Python models and helpers so those applications interpret the same contracts in the same way.

This SDK mirrors the contracts defined in
[`ori-specs`](https://github.com/ori-platform/ori-specs) without depending on [`ori-runtime`](https://github.com/ori-platform/ori-runtime) internals. It provides typed models, validation, and helper utilities for Ori consumers while leaving runtime policy and action authority to the runtime itself.

The SDK is a library rather than a standalone application. It includes a read-only Unix socket client for runtime health but does not provide networking, hardware control, database access, or local skill execution.

> ## Design principles

The SDK is designed around a few core principles:

- Mirror runtime and `ori-specs` contracts rather than redefine them.
- Keep public APIs fully typed and immutable where practical.
- Avoid dependencies on `ori-runtime` internals.
- Provide reusable models and helpers without implementing runtime policy.
- Keep networking and hardware control outside the SDK, except for the
  read-only runtime health client.

> ## Scope

The `0.1.x` release includes:

- - Typed runtime-health models and synchronous/asynchronous local health-socket clients.
- Read-only health diagnostic helpers.
- Deployment-aware configuration models for CLI and Gateway consumers.
- Immutable skill package models and validation.
- Gateway topics, payload models, and response-correlation helpers.
- Runtime telemetry models, canonical JSON serialization, and HMAC helpers.
- Ed25519 signing and verification helpers for artifacts and skill manifests.
- Firmware Layer 1 capability, telemetry, heartbeat, fault, and freshness models.

The following are intentionally out of scope:

- Runtime policy enforcement.
- Hardware control.
- Local skill execution.
- MQTT or HTTP clients.
- Database persistence.
- Decorator-based skill authoring.

> ## Technologies

| Technology | Purpose |
| --- | --- |
| Python 3.11 and 3.12 | Supported and CI-tested Python versions |
| Dataclasses | Typed, mostly immutable SDK models |
| PyYAML | Safe loading and validation of skill-package documents |
| cryptography | Ed25519 signing and signature verification |
| Unix domain sockets | Read-only communication with the local runtime health socket |
| asyncio | Asynchronous runtime health requests |
| pytest | Unit and integration testing |
| mypy | Static type checking |
| Ruff | Linting and formatting |
| pre-commit | Local quality and repository policy checks |
| GitHub Actions | Continuous integration |

Runtime dependencies are limited to `cryptography` and `PyYAML`.

Development dependencies are managed through `pyproject.toml` and pinned in
`requirements-dev.txt`.

> ## Project setup

#### 1. Clone the repository

Before contributing or experimenting with the SDK, clone the repository and set up a local development environment.

```bash
git clone <repository-url>
cd ori-sdk-python
```

#### 2. Create a virtual environment

```bash
python -m venv .venv
```

#### 3. Activate the environment

*For macOS / Linux*

```bash
source .venv/bin/activate
```

*For command prompt*

```cmd
.venv\Scripts\activate.bat
```

*for Windows powerShell*

```powershell
.venv\Scripts\Activate.ps1
```

#### 4. Install the project and its dependencies

```bash
pip install -e ".[dev]"
```

#### 5. Install the pre-commit hooks

```bash
pre-commit install
```

**<u>Requirements</u>**

- Python 3.11 or 3.12
- `pip`

>## Using the SDK

`ori-sdk-python` is a Python library rather than a standalone application. It does not provide a server or daemon to start. Instead, import the SDK into your own applications and tools.

- #### Read Runtime Health

    The SDK provides typed health models and read-only diagnostic helpers. Health clients support synchronous and asynchronous local socket access. These helpers summarize runtime state but do not grant authority or make action decisions. 

    ```python
    from ori_sdk import (
        RuntimeHealthClient,
        runtime_posture_summary,
        sensor_freshness_delta,
    )

    response = RuntimeHealthClient().get_health()
    if response.ok and response.health is not None:
        posture = runtime_posture_summary(response.health)
        freshness = sensor_freshness_delta(response.health)
    ```

- #### Validate skill packages

    The SDK provides immutable skill-package models and validation helpers aligned with the Ori skill-package contract. Validation checks package structure and metadata consistency.

    ```python
    from pathlib import Path
    from ori_sdk import SkillYamlNormaliser
    
    package = SkillYamlNormaliser.load_and_validate(
        Path("skills/my-skill/skill.yaml")
        )
        print(package.name, package.triggers[0].action_tier)
    ```

- #### Describe deployments

    The SDK provides typed deployment models that describe deployment capabilities and constraints. These summaries help CLI and Gateway consumers understand the deployment class.

    ```python
    from ori_sdk import DeviceConfig, DeploymentType

    config = DeviceConfig(DeploymentType.EDGE_NODE, device_id="site-a-edge-01")
    print(config.constraints.max_action_tier)  # "D"
    ```

    | Deployment type | Physical actuation supported | Maximum action tier |
    | --- | ---: | ---: |
    | `edge_node` | conditional | D |
    | `phone` | unsupported | B |
    | `pi` | conditional | D |
    | `server` | unsupported | None |

- #### Build gateway messages

    Gateway models represent logical messages after transport handling. They do not implement transport security, open MQTT connections, or grant mutation or physical-action authority.

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

- #### Build runtime telemetry

    The SDK validates the telemetry payload, serializes it into canonical JSON bytes, and computes the HMAC signature. It does not load credentials, build HTTP headers, choose an endpoint, or send telemetry.

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

- #### Verify firmware telemetry

    Firmware helpers verify signed capability manifests, measurements, heartbeats,
    and fault events. Applications are responsible for storing freshness state and replay protection. Verification does not persist data, grant physical-action authority, or enable Tier C/D actions.

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

- #### Sign artifacts and manifests

    Artifact signing protects the exact artifact bytes. Use `sign_manifest()` and
    `verify_manifest_signature()` for canonical skill metadata instead. These two
    signing profiles are intentionally separate and cannot replace one another.

    ```python
    from ori_sdk import sign_artifact, verify_artifact_signature

    metadata = sign_artifact(artifact_bytes, private_key_bytes)
    verify_artifact_signature(artifact_bytes, metadata, public_key_b64)
    ```

The examples above demonstrate the SDK's core building blocks. Each helper is designed to mirror an Ori contract without introducing runtime policy,
networking, or hardware dependencies.

>## Verification checklist

Before opening a pull request, run the following checks locally.

#### **<u>Tests</u>**

- Run the full test suite

    ```bash
    pytest -q
    ```

- Run a single test file

    ```bash
    pytest -q tests/test_device_config.py
    ```

- Run a single test

    ```bash
    pytest -q tests/test_device_config.py::test_deployment_type_from_value
    ```

#### **<u>Code quality</u>**

- Run Ruff for linting

    ```bash
    ruff check .
    ```

- Verify formatting

    ```bash
    ruff format --check .
    ```

- Run static type checks

    ```bash
    mypy ori_sdk tests
    ```

#### **<u>Repository checks</u>**

- Run pre-commit hooks

    ```bash
    pre-commit run --all-files
    ```

- Run the workflow checker

    This is applicable **IF** GitHub workflows or `.pre-commit-config.yaml` were modified

    ```bash
    python scripts/check_workflows.py
    ```

These checks mirror the project's continuous integration (CI) pipeline.

> ## Contract compatibility

| SDK version | Runtime compatibility | Specification compatibility |
| --- | --- | --- |
| `0.1.x` | `ori-runtime` `v2.0.0+` (health, gateway, telemetry, firmware telemetry, and skill-loader contracts) | `ori-specs` `v1` |

The SDK mirrors the following contract families:

- [`runtime-health/v1`](https://github.com/ori-platform/ori-specs/blob/main/runtime-health/v1.md)
- [`gateway-api/v1`](https://github.com/ori-platform/ori-specs/blob/main/gateway-api/v1.md)
- [`skills-package/v1`](https://github.com/ori-platform/ori-specs/blob/main/skills-package/v1.md)

Legacy skill packages using `escalate_to: cloud` must migrate to
`escalate_to: gateway`. Cloud reasoning is gateway-mediated in the current
contract.

**<u>Compatibility notes</u>**

The SDK maintains compatibility with existing consumers where possible.

Deprecated APIs remain available for existing integrations but should not be used
for new development.

- `posture_interpretation()` is deprecated in favor of the runtime v2 posture
  model.
- Legacy skill metadata validation helpers remain available for existing skill
  package integrations.

>## Contributing

Contributions are welcome. Changes should preserve the SDK's contract
compatibility, strict typing, runtime independence, and security requirements.

Before contributing, read:

1. [`README.md`](README.md)
2. [`PRINCIPLES.md`](PRINCIPLES.md)
3. [`AGENTS.md`](AGENTS.md)
4. [`SECURITY.md`](SECURITY.md)

#### **<u>Contribution rules</u>**

Before opening a pull request, ensure that you:

- Add only fields and semantics defined by the relevant Ori contract (`ori-specs`).
- Do not import `ori-runtime` internals.
- Keep public APIs fully typed. Avoid public `Any` types.
- Use typed SDK errors at public API boundaries.
- Do not expose raw socket or parsing errors.
- Preserve gateway request/response correlation IDs throughout the request lifecycle.
- Preserve the separation between diagnostics/reasoning and runtime action authority.
- Preserve skill-package safety guarantees.
- Add appropriate tests for new behavior and fixtures for contract-facing changes.
- Export new public APIs through `ori_sdk/__init__.py`.
- Workflow changes must pass `scripts/check_workflows.py`.
- All local verification commands must pass.

#### **<u>Recommended contribution workflow</u>**

1. Create a feature branch:

    ```bash
    git switch -c test/health-timeout-coverage
    ```

2. Make your changes and complete the [Verification checklist](#verification-checklist).

3. Commit using the required format:

    ```bash
    git commit -m "test(health): cover timeout failures"
    ```

    Commit messages must follow:

    ```bash
    type(scope): description
    ```

4. Open a pull request that explains:
    - What changed.
    - Why the change is required.
    - Which contract or repository rule applies.
    - How the change was tested.
    - Whether public behavior or compatibility changed.
    - Whether security-sensitive files were modified.

**<u>Note:</u>**

Common commit types include:

| | | |
| ------------------------ | --- | --- |
| `feat` | `build` | `fix` |
| `ci` | `docs` | `chore` |
| `test` | `revert` | `perf` |
 `security` | `refactor` | |

Contributions that improve reliability, usability, and contract compatibility are welcome.

>## Security and distribution

`ori-sdk-python` is distributed as a Python library rather than a standalone
application.

Consumers deploying the SDK in production should follow the project's
artifact-signing, dependency, and supply-chain requirements documented in
[`AGENTS.md`](AGENTS.md) and [`SECURITY.md`](SECURITY.md).

To report a security vulnerability, use GitHub private vulnerability reporting.
Do not open a public issue for undisclosed security concerns.

> ## Project links

- Ori runtime: [ori-runtime](https://github.com/ori-platform/ori-runtime)
- Ori specifications: [ori-specs](https://github.com/ori-platform/ori-specs)
- Ori skills hub: [ori-skills-hub](https://github.com/ori-platform/ori-skills-hub)
- Ori cli: [ori-cli](https://github.com/ori-platform/ori-cli)
- Ori gateway: [ori-gateway](https://github.com/ori-platform/ori-gateway)

> ## Status

This project is currently in its `0.1.x` bootstrap stage, focused on
establishing stable SDK contracts and shared models for Ori integrations.

The current release provides:

- Runtime-health contract models and local health communication.
- Deployment-aware configuration models for CLI and Gateway consumers.
- Gateway contract models and request/response validation helpers.
- Skill-package models, validation, and signing helpers.
- Runtime telemetry models and canonical serialization helpers.
- Firmware telemetry capability and verification models.

> ## License

Apache-2.0. See [LICENSE](LICENSE).
