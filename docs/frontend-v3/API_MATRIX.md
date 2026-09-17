# frontend-v3 — API matrix (P0)

Источник: текущий `frontend/` + `servers/urls.py` / auth views.  
Demo-fallback **не** переносится.

## Auth / session

| Client | Method | Path | Notes |
| --- | --- | --- | --- |
| `fetchAuthSession` | GET | `/api/auth/session/` | cookie session |
| `authLogin` | POST | `/api/auth/login/` | `{username,password,auth_mode}` + CSRF |
| `authLogout` | POST | `/api/auth/logout/` | CSRF |
| CSRF bootstrap | GET | `/api/auth/csrf/` | sets `csrftoken` cookie |

## First-run readiness

| Client | Method | Path |
| --- | --- | --- |
| `fetchSettingsReadiness` | GET | `/api/settings/readiness/` |

Gate: staff + `settings` feature + localStorage not seen → redirect `/settings/readiness?firstRun=1`.

## Servers (P0)

| Client | Method | Path |
| --- | --- | --- |
| `fetchFrontendBootstrap` | GET | `/servers/api/frontend/bootstrap/` |
| `createServer` | POST | `/servers/api/create/` |
| `deleteServer` | POST | `/servers/api/{id}/delete/` |
| `testServer` | POST | `/servers/api/{id}/test/` |

## Files (P0)

| Client | Method | Path |
| --- | --- | --- |
| `listServerFiles` | GET | `/servers/api/{id}/files/?path=` |
| `readServerTextFile` | GET | `/servers/api/{id}/files/read/?path=` |
| `writeServerTextFile` | POST | `/servers/api/{id}/files/write/` |
| `createServerFolder` | POST | `/servers/api/{id}/files/mkdir/` |
| `deleteServerFile` | POST | `/servers/api/{id}/files/delete/` |

## WebSocket (P0)

| Client | URL |
| --- | --- |
| `getWsUrl(serverId)` | `/ws/servers/{id}/terminal/` |

Протокол: `connect` → `input` / `resize` / `disconnect`; ответы `output`, `status`, `error`, `exit`, `terminal_session`.  
Auth: session cookie через Vite `proxyReqWs` (`copyProxyHeaders`).

## Routes implemented in v3

P0 working: `/login`, `/`, `/dashboard`, `/servers`, `/servers/hub`, `/servers/:id/terminal`, `/settings`, `/settings/readiness`, `/settings/appearance`.

P1/P2 placeholders (nav + FeatureGate only): agents, automation, chat, studio, mars, kubernetes, monitoring/insights, settings/plugins.
