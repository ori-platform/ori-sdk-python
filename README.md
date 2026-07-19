# ori-sdk-python

Python SDK for [Ori runtime](https://github.com/ori-platform/ori-runtime) integrations and community skill tooling.

> ## Table of Contents

* [Overview](#overview)
* [Project Features](#project-features)
* [Technologies](#technologies)
* [Repo Setup](#repo-setup)
* [Setting Up the Project](#setting-up-the-project)

  * [Install the Project](#install-the-project)
  * [Use the SDK](#use-the-sdk)
  * [Pre-commit and Lint Checks](#pre-commit-and-lint-checks)
  * [Running Tests](#running-tests)
* [Compatibility](#compatibility)
* [Links to the Project](#links-to-the-project)
* [Status](#status)
* [Contributing to the Project](#contributing-to-the-project)
* [License](#license)

#

> ## Overview

<p align="justify">
<code>ori-sdk-python</code> provides shared Python models and utilities for applications that integrate with the Ori platform.
</p>

<p align="justify">
It includes typed runtime-health and gateway contract models, a local Unix-socket health client, immutable skill-package validation, and gateway request and response helpers.
</p>

<p align="justify">
The SDK mirrors contracts defined in <a href="https://github.com/ori-platform/ori-specs">ori-specs</a> and must remain independent of <a href="https://github.com/ori-platform/ori-runtime">ori-runtime</a> internals.
</p>

#

> ## Project Features

The current `0.1.x` release intentionally provides a thin and stable bootstrap API.

* Typed models for the [`runtime-health/v1`](https://github.com/ori-platform/ori-specs/blob/main/runtime-health/v1.md) contract.

* Typed models for the [`gateway-api/v1`](https://github.com/ori-platform/ori-specs/blob/main/gateway-api/v1.md) contract.

* Synchronous and asynchronous health clients for communicating with the local Ori runtime socket.

* Immutable skill-package models and validation aligned with the [`skills-package/v1`](https://github.com/ori-platform/ori-specs/blob/main/skills-package/v1.md) contract.

* YAML and JSON skill-package loading.

* Gateway topic and request/response helper utilities.

* Gateway response matching using `request_id`.

* Stable SDK exceptions and error codes.

* Legacy `validate_skill_metadata*` helpers for callers that require the original mapping return type.

The following features are not included in this bootstrap release:

* Decorator-based skill authoring.

* Local skill execution harness.

These features are deferred until post-v1 usage patterns are better established. Consumers should not depend on them yet.

#

> ## Technologies

| **Technology**             | **Usage**                                        |
| :------------------------- | :----------------------------------------------- |
| **`Python 3.11 and 3.12`** | Supported programming language versions          |
| **`PyYAML`**               | YAML and JSON skill-package parsing              |
| **`Dataclasses`**          | Typed runtime, gateway, and skill-package models |
| **`Unix domain sockets`**  | Local Ori runtime health communication           |
| **`asyncio`**              | Asynchronous health requests                     |
| **`pytest`**               | Automated testing                                |
| **`Ruff`**                 | Linting and formatting                           |
| **`mypy`**                 | Static type checking                             |
| **`pre-commit`**           | Local code-quality and policy checks             |
| **`GitHub Actions`**       | Continuous integration                           |

#

> ## Repo Setup

Clone the repository:

```bash
git clone <repository-url>
cd ori-sdk-python
```

Create and switch to a new branch before making changes:

```bash
git switch -c <branch-name>
```

Confirm the current branch:

```bash
git branch --show-current
```

Replace the placeholders with the correct repository URLs.

#

> ## Setting Up the Project

The project requires Python 3.11 or 3.12 and `pip`.

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

Activate it on Windows Command Prompt:

```cmd
.venv\Scripts\activate
```

### Install the Project

Install the SDK and its development dependencies:

```bash
pip install -e ".[dev]"
```

Install the pre-commit hooks:

```bash
pre-commit install
```

### Use the SDK

This repository contains a Python library rather than a standalone application. There is no server-start command.

#### Read Runtime Health

```python
from ori_sdk.health import RuntimeHealthClient

client = RuntimeHealthClient()
response = client.get_health()

if response.ok and response.health is not None:
    print(response.health.device_id, response.health.uptime_s)
else:
    print(response.error)
```

The client connects to the following local Unix socket by default:

```text
/run/ori/health.sock
```

#### Validate a Skill Package

```python
from pathlib import Path

from ori_sdk import SkillYamlNormaliser

package = SkillYamlNormaliser.load_and_validate(
    Path("skills/my-skill/skill.yaml")
)

print(package.name, package.triggers[0].action_tier)
```

The legacy validation helpers remain available:

```python
from pathlib import Path

from ori_sdk import validate_skill_metadata_file

validated = validate_skill_metadata_file(
    Path("skills/my-skill/skill.yaml")
)

print(validated["name"])
```

#### Build Gateway Topics

```python
from ori_sdk import gateway_request_topic, gateway_response_topic

request_topic = gateway_request_topic("device-001")
response_topic = gateway_response_topic("device-001")

print(request_topic)
print(response_topic)
```

Output:

```text
ori/device-001/reasoning/request
ori/device-001/reasoning/response
```

The SDK provides gateway helpers only. It does not create MQTT connections.

### Pre-commit and Lint Checks

Run all pre-commit checks:

```bash
pre-commit run --all-files
```

Lint the project:

```bash
ruff check .
```

Check formatting:

```bash
ruff format --check .
```

Run static type checks:

```bash
mypy ori_sdk
```

Run the workflow security checker:

```bash
python scripts/check_workflows.py
```

### Running Tests

Run the complete test suite:

```bash
pytest -q
```

Run a specific test file:

```bash
pytest -q tests/test_gateway.py
```

Before opening a pull request, run:

```bash
python scripts/check_workflows.py
pre-commit run --all-files
pytest -q
ruff check .
ruff format --check .
mypy ori_sdk
```

#

> ## Compatibility

| **SDK Version** | **Runtime Baseline**                                                | **Specification Baseline** |
| :-------------- | :------------------------------------------------------------------ | :------------------------- |
| **`0.1.x`**     | `ori-runtime` `v2.0.0+` health, gateway, and skill-loader contracts | `ori-specs` `v1`           |

The SDK mirrors contracts from:

* [`runtime-health/v1`](https://github.com/ori-platform/ori-specs/blob/main/runtime-health/v1.md)
* [`gateway-api/v1`](https://github.com/ori-platform/ori-specs/blob/main/gateway-api/v1.md)
* [`skills-package/v1`](https://github.com/ori-platform/ori-specs/blob/main/skills-package/v1.md)

The SDK must not import internal implementations from `ori-runtime`.

### Legacy Skill-Package Migration

Skill-package validation targets `ori-runtime` `v2.0.0+`.

Legacy packages using:

```yaml
escalate_to: cloud
```

must migrate to:

```yaml
escalate_to: gateway
```

Cloud reasoning is gateway-mediated in the current contract.

#

> ## Links to the Project

* Ori runtime: https://github.com/ori-platform/ori-runtime
* Ori specifications: https://github.com/ori-platform/ori-specs
* Runtime-health contract: [runtime-health/v1](https://github.com/ori-platform/ori-specs/blob/main/runtime-health/v1.md)
* Gateway API contract: [gateway-api/v1](https://github.com/ori-platform/ori-specs/blob/main/gateway-api/v1.md)
* Skill-package contract: [skills-package/v1](https://github.com/ori-platform/ori-specs/blob/main/skills-package/v1.md)
#

> ## Status

This project is currently in its `0.1.x` bootstrap stage.

The current release focuses on:

* Runtime-health contract models.

* Gateway contract models and helpers.

* Local runtime health communication.

* Skill-package validation.


#

## Contributing to the Project

Contributions are welcome, but changes must preserve the SDK's contract fidelity, strict typing, runtime independence, and safety requirements.

Before contributing, read:

1. [`README.md`](README.md)
2. [`PRINCIPLES.md`](PRINCIPLES.md)
3. [`AGENTS.md`](AGENTS.md)
4. [`SECURITY.md`](SECURITY.md)

### Contribution Rules

Before opening a pull request, ensure that:

* New contract fields already exist in `ori-specs`.
* The SDK does not import `ori-runtime` internals.
* Public functions and classes have complete type annotations.
* Raw socket and parsing errors do not escape public APIs.
* Gateway request IDs remain unchanged throughout the request lifecycle.
* Skill-package safety rules are preserved.
* New behavior includes appropriate tests.
* Public exports are added to `ori_sdk/__init__.py` where required.
* Workflow changes pass `scripts/check_workflows.py`.
* All local verification commands pass.

### Recommended Contribution Workflow

Create a new branch:

```bash
git switch -c test/health-timeout-coverage
```

Make and verify your changes:

```bash
python scripts/check_workflows.py
pre-commit run --all-files
pytest -q
ruff check .
ruff format --check .
mypy ori_sdk
```

Commit using the required format:

```bash
git commit -m "test(health): cover timeout failures"
```

Commit messages must follow:

```text
type(scope): description
```

Supported commit types include:

```text
feat
fix
docs
test
refactor
perf
build
ci
chore
revert
security
```

A pull request should explain:

* What changed.
* Why the change is required.
* Which contract or repository rule applies.
* How the change was tested.
* Whether public behavior or compatibility changed.
* Whether security-sensitive files were modified.

All well-reasoned and verified suggestions are welcome.

#

> ## License

This project is licensed under the [Apache License 2.0](LICENSE).

Copyright 2026 Ori Nexus Systems LTD.
