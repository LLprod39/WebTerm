# Brand and compatibility contract

The product, UI, documentation, container title and public release name are **WebTerm**. `WebTermAI`, `WEU AI` and the misspelled display name `WebTrerm` are not current brands.

The following legacy values remain temporarily because changing them can break installations or plugin packages:

| Compatibility value | Why it remains | Migration rule |
| --- | --- | --- |
| lowercase `webtrerm.*` plugin IDs, manifest name and message types | Existing package/runtime identity | Do not rename before a versioned manifest migration and dual-read period |
| `WebTrermPluginBundle` browser global | Existing dynamic plugin bundles may export it | Keep as compatibility alias until a new WebTerm global has shipped with fallback |
| `webtrerm-prod`, image names, log/LDAP paths and `WEBTRERM_*` installer variables | Existing Compose and host automation | Treat as deployment identifiers, not display text |
| `C:\WebTrerm` and `/mnt/c/WebTrerm` | Current Windows/WSL checkout path | Preserve in executable local helper paths; prose should label it as an example |

All user-visible publisher names, prompts, notifications, admin titles, metadata and documentation use `WebTerm`. `scripts/verify_release_identity.py` rejects old display brands while allowing only the compatibility cases above.
