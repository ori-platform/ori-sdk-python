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

---

## Supply Chain Security Invariants

These rules apply to every AI coding agent modifying this repository. Violating
these rules can compromise the SDK that is embedded in systems controlling physical hardware.

1. Never add `pull_request_target` workflows that checkout or execute untrusted
   PR code. Use `pull_request` for fork PR workflows.

2. Every GitHub Actions workflow must declare explicit least-privilege
   permissions. Normal CI uses `contents: read` and `id-token: none`.

3. `id-token: write` is allowed only in a dedicated release job in `release.yml`.
   It must never appear in `ci.yml`.

4. Release jobs must never restore dependency caches (`actions/cache`, package
   manager caches, or setup action cache flags). Cache poisoning was a key part
   of the TanStack May 2026 supply-chain attack.

5. GitHub Actions must be pinned to full commit SHAs. Mutable tags such as
   `@v4`, `@v5`, `@main`, and `@master` are forbidden. Add a human-readable
   version comment next to each SHA.

6. Never download and execute remote scripts in CI without hash or signature
   verification. `curl URL | bash` and equivalent patterns are forbidden.

7. Python installs in CI must use hash-locked requirements files with
   `--require-hashes`. Do not use `pip install -e '.[dev]'` to resolve
   dependencies in CI.

8. Device deployment must install from signed artifacts or a signed wheelhouse.
   Production deployment must not resolve dependencies live from public registries.

9. Valid provenance does not imply safe code. The TanStack May 2026 incident
   produced malicious packages through legitimate CI/OIDC pathways. For Ori,
   Tier C/D skill review gates and runtime sandboxing remain mandatory
   regardless of provenance or author reputation.

10. Run `scripts/check_workflows.py` before merging workflow or pre-commit
    configuration changes. The script fails on `pull_request_target`, mutable
    action refs, unauthorized `id-token: write`, remote script execution
    patterns, and remote pre-commit hooks not pinned to full commit SHAs.

11. Ed25519 signing implementations that must interoperate with the runtime use
    `cryptography`, not PyNaCl. Alignment with ori-skills-hub and ori-runtime is
    required — all three repos use `cryptography` for Ed25519 operations.
