# Config

Versioned runtime-adjacent configuration lives here when the tool does not require it at the repository root.

- `keycloak_profiles.json` - named Keycloak profiles used by `key_mcp.py` and the Keycloak MCP container.

Root-level config files stay at the root only when external tools expect that exact location, for example `.github/`, `.pre-commit-config.yaml`, `.importlinter`, `docker-compose*.yml`, and `render.yaml`.
