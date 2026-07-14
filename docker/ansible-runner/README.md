# WebTerm Ansible Runner

Лёгкий Docker-образ с **настоящим** `ansible-playbook` для UI Playbooks.

## Нужен ли отдельный always-on сервис?

**Нет.** Лучше **ad-hoc контейнер** на каждый run (как job), а не демон 24/7:

| | Ad-hoc `docker run` (рекомендуем) | Always-on runner service |
|--|-----------------------------------|---------------------------|
| Сложность | низкая | выше (health, queue, сеть) |
| Изоляция | чистое окружение каждый раз | общее состояние |
| Ресурсы | 0, когда никто не гоняет playbook | постоянно занимает RAM |
| Как агенты | похоже на «job agent» | похоже на worker pool |

Always-on имеет смысл позже (очередь Celery, rate limit, multi-tenant). Сейчас — **образ + `docker run --rm`**.

## Сборка

```bash
docker build -t webterm-ansible:latest -f docker/ansible-runner/Dockerfile .
```

Compose:

```bash
docker compose --profile ansible build ansible-runner
```

## Переменные

| Env | Default | Meaning |
|-----|---------|---------|
| `WEBTERM_ANSIBLE_IMAGE` | `webterm-ansible:latest` | Какой образ запускать |
| `WEBTERM_ANSIBLE_TIMEOUT` | `1800` | Таймаут run (сек) |

## Почему не `stdout_callback=json`?

В ansible-core **нет** встроенного callback `json` (часто нужен `ansible.posix`).  
WebTerm использует **default callback + PLAY RECAP** — работает везде без плагинов.
