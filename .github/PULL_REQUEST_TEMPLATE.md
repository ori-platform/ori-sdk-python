## What does this PR do?

<!-- Describe the change. Focus on WHY, not just what. -->

## Type of change

- [ ] `feat` - new SDK API, model, client, or helper
- [ ] `fix` - bug fix or contract correction
- [ ] `docs` - documentation only
- [ ] `test` - tests only
- [ ] `refactor` - no behavior change
- [ ] `security` - touches signing, validation, install safety, or trust boundaries
- [ ] `contract-change` - changes a cross-repo contract mirrored from ori-specs/runtime

## Required checklist

- [ ] Linked issue is included below and acceptance criteria are addressed
- [ ] `pytest -q` passes
- [ ] `mypy ori_sdk tests` passes
- [ ] `ruff check ori_sdk tests` passes
- [ ] `ruff format --check ori_sdk tests` passes
- [ ] Pre-commit passes for changed files
- [ ] Every new `.py` file has the Apache-2.0 license header
- [ ] Public exports in `ori_sdk/__init__.py` are updated if a public API was added
- [ ] Fixtures were added/updated for schema-facing contract changes

## Contract and compatibility checklist

- [ ] This PR mirrors `ori-specs` or runtime behavior; it does not redefine runtime authority
- [ ] If gateway, hub, health, signing, or skill-package contracts changed, the matching repo/spec PR is linked
- [ ] Backward compatibility impact is explained, or the issue explicitly allows a breaking change

## Security-sensitive checklist

Complete if this PR touches signing, Hub install, tarball extraction, or skill validation.

- [ ] Ed25519 behavior uses `cryptography`, not PyNaCl, where runtime interoperability matters
- [ ] Invalid signatures, malformed payloads, and tampered bytes have negative tests
- [ ] Install/extraction paths reject traversal and do not execute skill hook code
- [ ] Secrets, tokens, private keys, and raw credentials are never logged or committed

## If you used AI assistance

- [ ] I can explain every line of AI-generated code in this PR
- [ ] I have read and understood every file I modified
- [ ] I am not submitting code I cannot defend in review

## Related issue

<!-- Closes #<issue-number> -->

## Testing notes

<!-- Include commands run and any intentionally skipped checks. -->
