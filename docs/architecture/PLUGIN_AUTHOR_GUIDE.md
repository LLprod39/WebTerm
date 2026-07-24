# WebTerm Plugin Author Guide

Last reviewed: 2026-06-28

This guide is for teams building self-hosted WebTerm plugins for their own
instance. The normal flow is internal: create a plugin with Mars, Codex, or by
hand, validate it, package it, install it disabled, review permissions, then
enable it.

This is not a public paid marketplace workflow.

## Quick Start

Create a metadata-only dashboard/page extension:

```powershell
python manage.py plugin_scaffold acme.ops-panel --template dashboard
cd webtrerm-plugin-acme-ops-panel
python manage.py plugin_validate .
python manage.py plugin_pack . --overwrite
python manage.py plugin_install_local .\dist\webtrerm-plugin-acme-ops-panel.wtp
```

The install command stages the plugin disabled. Enable it only after reviewing
permissions, secrets, settings, egress, and surfaces in `/settings/plugins`.

Alternatively, upload the generated `.wtp` in `/settings/plugins` under
`Create and install extension`. The upload path performs the same validation
and creates a disabled installation.

## Templates

`plugin_scaffold` supports these templates:

```powershell
python manage.py plugin_scaffold acme.empty --template empty
python manage.py plugin_scaffold acme.dashboard --template dashboard
python manage.py plugin_scaffold acme.page --template page
python manage.py plugin_scaffold acme.studio-node --template studio-node
python manage.py plugin_scaffold acme.agent-tool --template agent-tool
python manage.py plugin_scaffold acme.connector --template connector
python manage.py plugin_scaffold acme.hook --template hook
python manage.py plugin_scaffold acme.full --template full
```

Template behavior:

- `empty` creates a clean manifest skeleton.
- `dashboard` creates a page plus dashboard widget metadata.
- `page` creates a platform page metadata entry.
- `connector` creates required secret, egress, permission, and connector metadata.
- `studio-node`, `agent-tool`, `hook`, and `full` create sandbox executor refs and `backend/plugin.py`.

Sandbox templates require sandbox settings before `plugin_validate` and
`plugin_pack` pass. That is intentional: code execution must be explicit.

For local development of code templates:

```powershell
$env:PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES="true"
$env:PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED="true"
$env:PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED="true"
python manage.py plugin_validate .
python manage.py plugin_pack . --overwrite
```

## Mars Or Codex Workflow

When asking Mars or Codex to build a plugin, give it this contract:

```text
Build a WebTerm self-hosted plugin.
Do not edit WebTerm core files.
Use webtrerm.plugin.json as the source of truth.
Declare every permission, secret, egress host, setting, and surface.
Do not add install scripts, automatic dependency installation, migrations, or direct imports from WebTerm feature internals.
Package must validate with python manage.py plugin_validate .
Package must install disabled with python manage.py plugin_install_local <package.wtp>.
```

For code plugins, add:

```text
Use sandbox:backend/plugin.py:handle executor refs only.
Keep backend/plugin.py deterministic and small.
Do not read raw secrets directly; use declared secret bindings.
Network egress must match manifest egress declarations.
```

## Package Layout

The scaffold creates:

```text
webtrerm.plugin.json
README.md
CHANGELOG.md
LICENSE
backend/README.md
backend/tests/README.md
frontend/manifest.json
assets/icon.svg
docs/usage.md
migrations/README.md
signatures/README.md
```

Sandbox templates also create:

```text
backend/plugin.py
```

## Manifest Requirements

Every plugin must declare:

- stable lowercase plugin id such as `acme.ops-panel`;
- semantic `version`;
- author/team metadata under `publisher`;
- `summary`, `description`, `risk_tier`, and categories;
- requested permissions with human-readable reasons;
- required secrets;
- external egress hosts;
- settings schema;
- surfaces: pages, dashboard widgets, connectors, Studio nodes, agent tools, terminal actions, or hooks;
- support/docs metadata.

High-risk permissions require explicit admin grants before runtime use.

## Safe Lifecycle

Use this lifecycle for internal plugins:

1. Scaffold the plugin.
2. Edit `webtrerm.plugin.json`.
3. Validate source with `plugin_validate`.
4. Pack with `plugin_pack`.
5. Install locally with `plugin_install_local`.
6. Review in `/settings/plugins`.
7. Grant permissions and bind required secrets.
8. Enable.
9. Watch health, audit events, and active surfaces.
10. Roll back or disable if behavior is wrong.

Install never executes plugin code. Enablement is separate from installation.

## Package Rules

Validation rejects:

- unsafe archive paths;
- install scripts;
- shell/batch executables;
- dependency manifests unless sandboxed code packages are enabled;
- dynamic frontend renderers unless frontend sandbox and bundle review gates are enabled;
- executor refs outside trusted demo refs or `sandbox:` refs;
- raw unsupported manifest capabilities.

## Dynamic UI

Default plugins should use metadata-driven pages/widgets.

Dynamic frontend bundles are advanced. They require explicit platform settings,
frontend sandboxing, HTTPS `bundle_url`, `bundle_sha256`, reviewed/signed package
state, and `frontend_bundle_review` attestation. Do not use dynamic bundles for
ordinary internal plugins unless the team intentionally enables that trust path.

## Compatibility Tests

Sandboxed backend packages can declare optional `compatibility_tests`:

```json
{
  "compatibility_tests": [
    {
      "id": "echo-value",
      "executor_ref": "sandbox:backend/plugin.py:handle",
      "payload": { "surface": "compatibility_job", "arguments": { "value": "expected" } },
      "expect": { "result.echo": "expected" }
    }
  ]
}
```

These tests run inside the configured sandbox provider.

## Internal Rollout Checklist

Before enabling a plugin for users:

- README explains setup and usage;
- changelog and license are present;
- permissions have clear reasons;
- secrets are declared and bound by ref;
- egress hosts are declared;
- settings schema rejects unknown keys when appropriate;
- package validates;
- package installs disabled;
- compatibility checks pass;
- rollback package is retained;
- plugin can be disabled without breaking saved layouts or workflows.

That is enough for the self-hosted extension platform.
