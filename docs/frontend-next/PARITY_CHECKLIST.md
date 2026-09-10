# Parity checklist

Статусы: PASS = реализовано и проверено указанным evidence; PARTIAL = остаются конкретные workflows/runtime gates; FAIL = воспроизводимая ошибка; NOT APPLICABLE = backend не предоставляет возможность в данном release profile.

Сверяем каждую строку FEATURE_INVENTORY.md с:
- точным API/payload и permissions;
- route/UI/actions;
- loading/empty/error/realtime;
- смысловой contract проверкой и browser workflow;
- реальным backend evidence отдельно от fixtures.

Сверка выполнена для 39/39 групп. Подробные результаты и границы evidence — [FINAL_PARITY_REPORT](FINAL_PARITY_REPORT.md).

- [x] Новая реализация без старых frontend-компонентов, истории, стилей и скриншотов.
- [x] Product model, API inventory, IA, routes, roles, realtime и UI state matrix.
- [x] Одна дизайн-система Light/Dark и общий shell.
- [x] Все применимые разделы backend имеют UI, typed API и guards.
- [x] Loading/empty/error/disabled, конфликт сохранения, несохранённый draft, disconnect/reconnect обработаны.
- [x] SSH/SFTP, access CRUD, playbooks и pipeline execution проверены на изолированном реальном backend.
- [x] Canvas показывает immutable run snapshot и реальные node statuses.
- [x] Клавиатура, WCAG automation, laptop/mobile overflow и Light/Dark browser review.
- [x] Typecheck, ESLint, unit, build budget, Storybook, Host allowlist и audit gates.
- [x] CI/runtime инструкции, QA isolation и rollback задокументированы.
- [x] Предшествующие пользовательские изменения сохранены; credentials и QA artifacts исключены из Git/Docker context.

Внешняя интеграционная приёмка остаётся отдельной: корпоративный IdP, реальные AI/CLI/MCP/MARS/Ansible/GitLab/Kubernetes и рабочие фоновые executors требуют настроенного окружения заказчика. Fixtures не считаются результатом этих интеграций. Публичное развёртывание не выполнялось.
