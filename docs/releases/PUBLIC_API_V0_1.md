# WebTerm v0.1 public HTTP surface

WebTerm has many internal endpoints. Only the routes in `config/public-api-v0.1.json` are declared stable for the v0.1 lifecycle. Route names and resolved paths are guarded by `tests/test_public_api_v0_1_contract.py`.

The declared surface covers health, browser authentication/session, first-run readiness, server inventory/bootstrap and the monitoring summary. Authentication and authorization remain server-side requirements; a documented route is not an access grant.

Compatibility policy:

- removing or changing a declared path or method requires a versioned API decision and changelog entry;
- adding an internal endpoint does not make it public;
- response-schema guarantees must be added explicitly before external clients depend on them;
- denied requests must not disclose protected resource state.

This is a route contract, not a complete OpenAPI claim. OpenAPI publication is deferred until schemas, error envelopes and authentication flows are machine-declared for every public operation.
