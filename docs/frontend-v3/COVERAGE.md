# Coverage check — UI inventory → spec

Дата: 2026-09-13  
Проверка: каждый маршрут старого `frontend/src/App.tsx` и каждый диалог из инвентаря либо описан в `screens/` + `MODALS_REGISTRY.md`, либо явно «убрано».

## Routes

| Old route | Spec file | Notes |
| --- | --- | --- |
| `/login` | 01-login | |
| `/` Index redirect | 14-system | |
| `/dashboard` | 02-dashboard | единый экран; Admin/User widgets **убраны** |
| `/admin`, `/dashboard/admin` | 14-system | redirect → `/dashboard` |
| `/servers` | 03-servers | |
| `/servers/hub`, `/servers/:id/terminal` | 04-terminal | |
| `/agents`, `/agents/run/:runId` | 05-agents | |
| `/automation/*` | 06-automation | |
| `/studio`, drafts, pipeline, runs, agents, skills, mcp, notifications | 07-studio | |
| `/chat` | 08-chat | |
| `/mars`, `/mars/runs/:runId` | 09-mars | |
| `/kubernetes`, admin, clusters, fleet, devtron | 10-kubernetes | |
| `/settings/*` (15 subpages) | 11-settings | |
| `/settings/plugins`, `/plugins/:id/:page`, `/marketplace` | 12-plugins | |
| `/monitoring/insights` | 13-monitoring | |
| `*` NotFound | 14-system | |
| Placeholder P1/P2 (current v3) | 14-system | |

## Modal IDs (MODALS_REGISTRY)

| Prefix | Count (approx) | Screen |
| --- | --- | --- |
| SYS-* | 4 | 00-shell, 14 |
| SRV-* | 8 (01–06 + 05a/b) | 03-servers |
| TERM-* | 8 | 04-terminal |
| AGT-* | 5 | 05-agents |
| AUT-* | 10 | 06-automation |
| STU-* | 14 | 07-studio |
| CHT-* | 2 | 08-chat |
| MRS-* | 1 | 09-mars |
| K8S-* | 3 | 10-kubernetes |
| SET-* | 10 | 11-settings |
| PLG-* | 2 | 12-plugins |

## Explicitly removed (не переносить в v3)

| Item | Where documented |
| --- | --- |
| `window.confirm` / `window.prompt` | UI_SPEC §4, MODALS_REGISTRY «Убрано», screens 03/04 |
| UI style dropdown flow/enterprise/ashita | MODALS_REGISTRY, 00-shell, 11 appearance |
| CustomizableDashboard / decorative KPIs | 02-dashboard anti-slop |
| Greeting / motivational login copy | 01-login |
| AssistantDrawer in global chrome | MODALS_REGISTRY; chat only in 08 |
| NotificationCenter mixed feed | MODALS_REGISTRY |
| Demo-fallback API | PLAN §9 |
| Marketing 404 («Упс!») | 14-system |

## Gaps to close in implementation (не gaps спеки)

0. **Рестайл v2:** `index.css` сейчас v1 (тёмный ч/б) — переписать по UI_SPEC §2 (light default, `--accent`, `--surface`, soft-тона, shadows); `theme.tsx` default `dark` → `light`; `Badge` → RU-подписи по §2.6.
1. CSS tokens `--info`, `--terminal-bg`, `--overlay`, `--z-*`, `--dialog-w-*`, `--drawer-w` — ещё не в `index.css`.
2. Компоненты Dialog/Drawer/Toast — ещё не в `frontend-v3/src/components/ui/`.
3. Servers form в v3 сейчас упрощён (без auth_method/key/sudo) — целевое состояние в `03-servers.md` SRV-01.
4. `API_MATRIX.md` — только P0; P1 REST дописывает Мост.
5. `FeatureGate` в v3 делает silent `Navigate` — по спеке должен рендерить `ForbiddenState` (UI_SPEC §6, screens/14).
6. `LoginPage` в v3 без show-password и Caps Lock warning — по спеке `01-login.md` обязательны.
