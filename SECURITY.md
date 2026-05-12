# Security Policy

`ori-sdk-python` is a contract and tooling library for the Ori platform. It does
not control hardware directly, but security issues here can still affect skill
verification, CLI installs, Gateway integration, and [runtime](https://github.com/ori-platform/ori-runtime) diagnostics.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| `0.1.x` | Yes |

## Reporting a Vulnerability

Use GitHub's private vulnerability reporting for this repository:

1. Go to the repository `Security` tab.
2. Click `Report a vulnerability`.
3. Submit details privately.

If private reporting is unavailable, contact the repository owner directly via GitHub.

Do not open public issues for undisclosed vulnerabilities.

## What to Include

Please include:

- Affected component and file paths
- Reproduction steps
- Impact on contract fidelity, signing, validation, or [runtime](https://github.com/ori-platform/ori-runtime) integration
- Whether a malicious skill package could be accepted or installed
- Suggested remediation, if available

## Response Targets

For valid reports:

- Initial acknowledgment: within 72 hours
- Triage and severity decision: within 7 days
- Patch target:
  - Critical/high: as soon as possible, usually within 14 days
  - Medium/low: scheduled in normal release cadence

## Disclosure Policy

- Coordinate disclosure until a fix is available.
- Public disclosure is expected only after fix release or explicit maintainer approval.
- Security advisories and release notes will describe impact and mitigation.

## Scope and Priorities

Highest-priority findings include:

- Signature verification bypasses
- Accepting malformed or unsigned community skill packages
- Extracting or writing skill artifacts before verification
- Gateway request/response correlation failures
- Health client behavior that hides [`ori-runtime`](https://github.com/ori-platform/ori-runtime) failures from CLI/operator tooling
- Schema drift that weakens [runtime](https://github.com/ori-platform/ori-runtime) action-tier or skill validation invariants
- Secrets exposure in tests, fixtures, config, or logs

## Safe Harbor

Good-faith security research is welcome. We will not pursue action for:

- Testing within this repository and your own infrastructure
- Non-destructive proof-of-concept demonstrations
- Responsible private disclosure under this policy

Do not access or modify data/systems that you do not own or have permission to test.
