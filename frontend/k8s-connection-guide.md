# Kubernetes — подключение vs настройки

Источник данных в коде: `src/pages/kubernetes-cockpit/connectionGuide.ts`.

## Роли

| Кто | `/kubernetes` → Подключение | Настройки `/settings/kubernetes` | Fleet / Devtron |
|-----|-----------------------------|----------------------------------|-----------------|
| Любой с feature `kubernetes` | Добавить свой кластер через **kubeconfig** + Sync | Нет | Нет |
| Админ (`is_staff`) | То же + блок про админские настройки | Да — провайдеры, Devtron, Fleet, **выдача доступа**, release gate | Да, из настроек |

## Для каждого пользователя

1. `/kubernetes` → вкладка **Подключение**.
2. Загрузить / вставить kubeconfig → выбрать context → **Подключить и синхронизировать**.
3. Дальше: область → под → логи → «Объяснить логи».
4. Кластеры «От администратора» появляются после grant.

## Для администратора

1. `/settings/kubernetes` — платформенные Rancher/Devtron, Fleet, readiness, sync worker.
2. Блок **Доступ пользователей** — выдать cluster (± namespaces).
3. Ссылки на `/kubernetes/devtron` и `/kubernetes/fleet` только отсюда (`staffOnly`).

## API

- `POST /api/kubernetes/connections/kubeconfig/` — personal (или platform для staff) kubeconfig.
- `GET /api/kubernetes/connections/` — мои подключения + granted.
- `GET/POST /api/kubernetes/clusters/<id>/access/` — staff grants.
- Список clusters / namespaces / pods фильтруется по visibility (own + granted; staff — всё).
- Raw kubeconfig в ответах API не возвращается.
