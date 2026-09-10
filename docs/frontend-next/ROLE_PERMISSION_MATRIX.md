# Roles and permission matrix

Источник: core_ui/views/auth_views.py, core_ui/access.py, decorators, scoped research/GOVERNANCE_CONTRACTS.md.

| Область | Требование |
|---|---|
| Shell / проекты | authenticated session |
| Servers / monitoring / terminal | features.servers + server capabilities для действия |
| Playbooks / agents | backend automation permissions и ownership |
| Studio / pipeline | features.studio + active project + owner/staff; websocket owner-only |
| Kubernetes | features.kubernetes; admin sessions имеют отдельные grants/expiry |
| Access / audit | features.settings + is_staff |
| AI routing | can_manage_ai_routing; staff_default недостаточен |
| Plugins | features.plugins (содержит staff + release flag) |
| Server memory | owner; lifecycle admin endpoints дополнительно is_staff |

Нельзя считать скрытие кнопок защитой backend. Ошибка 403 видна пользователю, 401 завершает локальную сессию и очищает query cache. Tri-state override null означает наследовать, false — запретить, true — разрешить. Tenant switch отменяет и очищает предыдущие запросы.

