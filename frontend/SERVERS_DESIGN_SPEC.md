# WebTerm Servers — desktop product specification

Status: pilot-to-beta reference implementation  
Scope: desktop, `flow` light and `flow-dark` dark  
Mobile layout: deliberately deferred

## 1. Product job

The page answers four operator questions in order:

1. How many servers are in my access scope?
2. Which hosts are confirmed healthy by fresh monitoring data?
3. Which hosts need attention because data is missing, stale, or unhealthy?
4. What can I do next: open monitoring, start SSH, edit access, organize groups, or configure rules?

The screen does not invent sample data and does not use an open terminal session as a proxy for server health.

## 2. Information hierarchy

### Page header

- Kicker: `Инфраструктура` / `Infrastructure`.
- H1: `Серверы` / `Servers`.
- Count badge: total servers in the current user's access scope.
- Description: `Подключения, состояние и правила доступа к вашей серверной инфраструктуре.`
- Primary action: `Добавить сервер` / `Add server`.

### Summary

Four equal cards are shown when at least one server exists:

| Card | Meaning | Source |
| --- | --- | --- |
| `Всего` | All visible servers | bootstrap server list |
| `В норме` | Fresh monitoring record with `status = healthy` | monitoring status |
| `Нужна проверка` | All other visible servers, including missing or stale data | derived from total minus healthy |
| `Группы` | Groups available to manage | manageable group list |

The cards summarize scope and state. They are not navigation controls and therefore do not use hover or button language.

### Workspace tabs

- `Список серверов`: daily operational view.
- `Группы`: ownership and organization.
- `Правила`: shared access restrictions.

Search and group filters appear only on the server list tab.

### Group section

Each group has one collapsible section with:

- group name;
- grammatically correct server count;
- fresh healthy count;
- attention count when non-zero;
- persisted expanded/collapsed state per signed-in user.

`В норме: N` and `Требуют внимания: N` are state labels, not buttons.

### Server row

Desktop columns are:

1. **Server** — fresh health indicator, OS mark, server name, shared-access badge, last connection.
2. **Address** — `host:port`, SSH user, detected OS name.
3. **Load** — CPU, RAM, and disk gauges using the backend monitoring thresholds.
4. **Actions** — primary row action `SSH`; secondary actions live in the overflow menu.

Clicking the server name or health indicator opens monitoring. SSH remains an explicit button so monitoring and connection cannot be confused.

## 3. State semantics

### Fleet health

- `healthy` is green only when the monitoring result is fresh.
- Warning, critical, unreachable, unknown, stale, and missing monitoring data all count as `Нужна проверка`.
- An unreachable stale record is rendered as unknown rather than falsely presenting an old outage as current.
- Bootstrap `server.status` represents terminal/session availability and must not drive the health summary.

### Metrics

- Normal values use the informational accent.
- Warning and critical values use warning and destructive tokens.
- Thresholds mirror `servers/monitor.py`: CPU 80/95, RAM 85/95, disk 80/90.
- Missing individual metrics keep their column slot and show an em dash when a monitoring result exists.
- All percentages use tabular mono numerals so rows do not visually jump while values update.

### Last connection

Relative labels are deliberately compact: `только что`, `N мин назад`, `N ч назад`, `N дн назад`. An invalid date is shown as unknown rather than hidden or guessed.

## 4. Search and filtering

Search matches server name, host, SSH user, group, detected OS code, and readable OS name. The placeholder states the most useful fields: `Имя, адрес, ОС или группа…`.

The group filter contains all groups represented in the visible server list plus `Без группы`. Search and group filters are combined. Resetting filters clears both values. The result count distinguishes the full list from a filtered subset.

## 5. Visual system

### Typography

- `Manrope`: page title and summary values.
- `Inter`: navigation, labels, descriptions, controls, and row text.
- `JetBrains Mono`: addresses, ports, percentages, and numeric counters.
- Minimum visible UI size is 11 px; body copy uses a 20–24 px line-height depending on density.
- Font synthesis is disabled so unavailable weights are not faked.

### Light theme (`flow`)

- warm off-white canvas;
- white panels with thin neutral borders;
- near-black primary CTA;
- green health, amber attention, blue informational accents;
- restrained shadows used only to separate major layers.

### Dark theme (`flow-dark`)

- graphite canvas and panels, never absolute black-on-black;
- white primary CTA with dark text;
- the same semantic health/attention/info colors as light mode;
- border and surface contrast replaces glow-heavy decoration.

Components never branch on theme. They consume semantic tokens, so light and dark stay behaviorally identical.

### Icons and imagery

- Interface actions use Lucide at consistent 14–16 px optical size.
- Server identity uses the existing local OS/vendor SVG set through `ServerOsBadge`.
- Decorative hero art, stock imagery, and generated illustrations are intentionally excluded: they add noise to a high-density operational workspace.
- Unknown OS uses a neutral project-local server glyph rather than a misleading vendor mark.
- Asset provenance and commercial-release checks live in [`ASSET_LICENSES.md`](./ASSET_LICENSES.md).

## 6. Required states

- **Loading:** skeletons preserve the final header, summary, toolbar, and list geometry.
- **Request error:** one clear message with an in-place retry action.
- **No servers:** three next steps — add SSH server, create group, configure rules.
- **No filter results:** explain that search/group filters caused the empty state; offer reset and add-server actions.
- **No monitoring data:** neutral status and `нет данных`; never claim offline or healthy.
- **Shared server:** visible `Общий доступ` badge; edit/delete actions still follow API permissions.

## 7. Desktop layout contract

- Supported beta target: 1024–1920 px desktop viewport.
- The workspace is centered and capped at `max-w-6xl` (1152 px) so inventory rows do not stretch across ultrawide screens.
- Optimized content density: 1280–1600 px viewport with a compact 1152 px working canvas.
- At 1024 px the operational columns remain readable; wider screens keep stable column relationships rather than growing oversized rows.
- No horizontal page overflow is allowed.
- Mobile navigation, stacking, touch density, and mobile-specific actions are outside this iteration.

## 8. Copy rules

- Use concrete admin language: server, address, OS, monitoring, SSH, group, rule.
- Avoid vague labels such as `Insights`, `Manage`, or `AI status` when a precise Russian term exists.
- Use `Общий доступ`, not an unexplained `Shared` badge in Russian UI.
- State badges use nouns or state phrases; buttons use verbs.
- Do not mix Russian sentences with unexplained English except established technical terms such as SSH, CPU, and RAM.

## 9. Beta acceptance gates (deferred test phase)

When visual implementation is complete, validate separately:

- both themes at 1024, 1280, 1440, 1600, and 1920 px;
- real data, no-data, stale-data, mixed-health, ungrouped, shared, and long-name cases;
- keyboard navigation, focus visibility, accessible names, and contrast;
- search/filter/group persistence and all row actions;
- production build, targeted component tests, and a real browser smoke against the pilot backend.

These checks are intentionally deferred until the design pass is finished; this document defines what the later test phase must prove.
