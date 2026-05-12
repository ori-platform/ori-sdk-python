# AGENTS.md — ori-sdk-python

This repository ships shared SDK contracts for Ori companion repos.

## Purpose

`ori-sdk-python` exists to prevent cross-repo protocol drift by providing:

- typed contract models,
- [runtime](https://github.com/ori-platform/ori-runtime) health socket clients,
- skill metadata validation helpers.

It is not [`ori-runtime`](https://github.com/ori-platform/ori-runtime), does not execute hooks, and does not control hardware.

## Invariants

1. `SDK-1` Contract fidelity is absolute.
If a field exists in [`ori-specs`](https://github.com/ori-platform/ori-specs), it exists in SDK models. If it does not exist
in [`ori-specs`](https://github.com/ori-platform/ori-specs), it must not be introduced in models.

2. `SDK-2` Health client errors are typed and graceful.
Connection failures (including connection refused / missing socket / timeout)
must raise `HealthClientError`, never leak raw transport exceptions.

3. `SDK-3` Validation mirrors [`ori-runtime`](https://github.com/ori-platform/ori-runtime) semantics.
Skill metadata validation must enforce the same invariant set as [`ori-runtime`](https://github.com/ori-platform/ori-runtime)
`SkillLoader` for supported bootstrap rules.

4. `SDK-4` No hidden network behavior.
The SDK must not initiate HTTP/MQTT calls unless explicitly documented.
Health client is local AF_UNIX transport only.

5. `SDK-5` Strict typing.
Public APIs require type hints; `mypy` strict mode must pass. No public `Any`
types and no unexplained `type: ignore`.

6. `SDK-6` Request correlation integrity.
Gateway utilities must preserve `request_id` end-to-end. Builders and parsers
must not regenerate IDs during response handling.

7. `SDK-7` Runtime decoupling.
SDK must not import from [`ori-runtime`](https://github.com/ori-platform/ori-runtime) directly. Contracts come from
[`ori-specs`](https://github.com/ori-platform/ori-specs) and explicit mirrored types.

## Layout

```text
ori_sdk/
  __init__.py
  models.py
  health.py
  validation.py
  gateway.py
tests/
  fixtures/
```

## Verification

```bash
pre-commit run --all-files
pytest -q
mypy ori_sdk
```
