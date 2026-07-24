# ADR-0002: First public version is 0.1.0

- Status: Accepted
- Date: 2026-07-24
- Owners: WebTerm maintainers

## Context

The repository used the internal package version `2.0.0` before WebTerm had a published, evidence-backed public release contract. Keeping that number would imply compatibility and release history that do not exist.

## Decision

The canonical release identity is `0.1.0` in the root `VERSION`, Python project metadata, frontend package and lockfile, and backend/frontend container labels. The declared v0.1 HTTP surface is the compatibility boundary. Until the release checklist is approved, `0.1.0` remains unreleased.

Historical lowercase `webtrerm` identifiers and the local `C:\WebTrerm` checkout path remain compatibility values. They are not the product name and are inventoried in the release brand contract.

## Consequences

- New public behavior follows semantic versioning from `0.1.0`.
- Version drift fails CI through `scripts/verify_release_identity.py`.
- The old `2.0.0` value has no public support meaning.
- Renaming compatibility identifiers requires a separate migration with rollback evidence.

## Verification

```bash
python scripts/verify_release_identity.py
python -m pytest tests/test_release_identity.py tests/test_public_api_v0_1_contract.py
```
