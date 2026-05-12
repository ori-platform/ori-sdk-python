# Ori Design Principles

This repository is part of the Ori platform. Every design decision must survive
the eight lenses below. Principles 1-7 are inherited from runtime
(`ori-platform/ori`). Principle 8 governs cross-repo integration.

## 1. Actuation Trust

Physical trust is earned, not assumed.

## 2. Constraint

Designed for the world's majority condition.

## 3. Inviolable Safety

The deterministic Tier D layer is absolute.

## 4. Assumed Failure

Hardware lies. Software freezes. Power dies.

## 5. Offline-First

Offline-first is the requirement, not a feature.

## 6. Explicit Capability

The skill is the atomic unit of trust.

## 7. Explicit Authority Boundaries

Learning improves reasoning, never grants permissions.

## 8. Contract Fidelity

Consume runtime contracts. Never reinvent them.

Repo-specific note:
`ori-sdk-python` is the typed contract bridge for CLI, gateway, skills hub,
and cloud adapters. Any schema drift here propagates operational risk
platform-wide.
