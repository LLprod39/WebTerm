# Plugin Extensions Operations

Last reviewed: 2026-06-29

This runbook covers production operation for the self-hosted WebTrerm plugin
extension system. It is not a public paid marketplace runbook.

## Deployment Checks

Run Django deploy checks from the deployed environment:

```powershell
python manage.py check --deploy
```

These checks validate the active plugin trust boundary settings: package
signing, security scanning, sandbox configuration, remote package hosts,
federated catalog hosts, frontend bundle hosts, backend sandbox provider,
compatibility isolation mode, dependency allowlist format, and attestation
requirements.

## Compatibility Matrix Gate

Before promoting a private catalog batch or enabling a code-capable plugin
release, run the compatibility matrix gate:

```powershell
python manage.py plugin_compatibility_matrix --update --fail-on-incompatible
```

For CI or release evidence, emit JSON:

```powershell
python manage.py plugin_compatibility_matrix --update --fail-on-incompatible --json
```

The matrix validates manifest shape, supported plugin API version, static
no-code policy, review status, signature status, sandbox compatibility checks
when configured, and required attestation policy.

## Optional External Providers

External providers are optional hardening boundaries for private deployments.
Use them only when the deployment needs stronger isolation or hosted scanning.

Runtime services use these configured HTTPS endpoints:

- External signing: package sign and verify payloads for
  `webtrerm.plugin.package.v1`; package signing rejects responses whose
  `key_id` differs from the requested key.
- External scanner: package manifest, SBOM, dependency scan, provenance,
  signature status, and package hashes. Scanner responses must include an
  explicit verdict through `passed` or a configured passing `status`/`result`.
- External backend sandbox: retained package bytes, executor ref, payload,
  timeout, output limits, and smoke mode.
- External frontend bundle host: reviewed dynamic bundle artifact publication,
  immutable SHA-256-addressable delivery, CORS without credentials, and trusted
  bundle host allowlisting.

## Release Rule

Do not enable risky plugin modes just because passive settings are present. A
production release must pass Django checks and the compatibility matrix from
the same runtime network path, database, retained package storage, and provider
endpoints that package review, scan, signing, sandbox execution, and private
catalog installs will use.
