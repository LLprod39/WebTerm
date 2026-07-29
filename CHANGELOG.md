# Changelog

All notable WebTerm changes are recorded here. The format follows Keep a Changelog and releases use semantic versioning.

## [Unreleased]

### Changed

- Pinned production runtime and registry images to immutable digests.
- Tightened the frontend dependency-audit gate to an exact, reviewed React Router RSC-only exception for the SPA build.

### Security

- Centralized outbound HTTP validation, DNS pinning and redirect revalidation for Studio, MCP, catalog sync and Operator web research.
- Removed terminal authentication tokens from WebSocket URLs and constrained post-login redirects to local application routes.
- Enforced explicit SSH host-key trust, exact server capabilities, compound-command validation and separated Kubernetes requester/approver identities.
- Added fail-closed plugin archive extraction and package-trust checks, isolated MARS verification and required immutable MARS images.
- Removed a leaked example credential, protected production environment files and kept installer passwords off process arguments.

## [0.1.0] - 2026-07-24

### Added

- Frozen Python, Django, Node.js and npm runtime contract.
- Independent backend, frontend, architecture, security and Playwright CI gates.
- Versioned v0.1 capability scope, support matrix and release checklist.
- Canonical WebTerm brand and machine-checked release identity.
- Declared v0.1 public HTTP surface with route contract tests.

### Changed

- Internal historical version `2.0.0` is reset to the first public version `0.1.0`; see ADR-0002.

### Security

- Production deploy checks and supply-chain policy are required release evidence.

[0.1.0]: https://github.com/LLprod39/WebTerm/releases/tag/v0.1.0
[Unreleased]: https://github.com/LLprod39/WebTerm/compare/v0.1.0...HEAD
