# WebTerm Ansible Runner

Единый Docker-образ с **настоящим** `ansible-playbook` для проверки и выполнения Playbooks.

## Нужен ли отдельный always-on сервис?

Для выполнения — **нет**: каждый claim запускается в отдельном ad-hoc контейнере. Отдельный
networkless `playbook-validator` постоянно обслуживает только syntax-check через Unix socket и
никогда не получает inventory, SSH credentials или Docker socket.

| | Ad-hoc `docker run` (рекомендуем) | Always-on runner service |
|--|-----------------------------------|---------------------------|
| Сложность | низкая | выше (health, queue, сеть) |
| Изоляция | чистое окружение каждый раз | общее состояние |
| Ресурсы | 0, когда никто не гоняет playbook | постоянно занимает RAM |
| Как агенты | похоже на «job agent» | похоже на worker pool |

Очередь выполняет `playbook-execution-worker`. Контейнер выполнения получает детерминированное
имя `webterm-pb-r<run>-d<dispatch>-a<attempt>` и такие же labels. Это позволяет безопасно удалить
точную старую попытку через Docker daemon при cancel, потере lease или восстановлении worker.

## Сборка

```bash
docker build -t webterm-ansible:latest -f docker/ansible-runner/Dockerfile .
```

Compose:

```bash
docker compose --profile ansible build ansible-runner
```

После пересборки пересоздайте validator, чтобы проверка и выполнение использовали один образ:

```bash
docker compose build playbook-validator
docker compose up -d --no-deps --force-recreate playbook-validator
docker compose exec playbook-validator python /opt/webterm/validator.py --healthcheck
```

Образ запуска закрепляется по Docker image ID (`sha256:...`) с `--pull=never`. Внутри образа
лежит `/opt/webterm/runtime-manifest.json`: версии Python/Ansible/collections/OS packages и hash
runtime-файлов сведены в `runtime_digest`. Validator возвращает digest через `GET /health`, а
worker сравнивает его с сохранённым preflight/validation fingerprint до первого изменения хоста.
Смена mutable tag после проверки поэтому закрывает запуск и требует повторной validation.

## Переменные

| Env | Default | Meaning |
|-----|---------|---------|
| `WEBTERM_ANSIBLE_IMAGE` | `webterm-ansible:latest` | Какой образ запускать |
| `WEBTERM_ANSIBLE_TIMEOUT` | `1800` | Таймаут run (сек) |
| `WEBTERM_ANSIBLE_RUNTIME_ROOT` | — | Корень точечных runtime-каталогов; обязателен в isolated mode |
| `WEBTERM_ANSIBLE_RUNTIME_TTL_SECONDS` | `7200` (минимум `600`) | TTL orphan-каталогов после crash |
| `PLAYBOOK_RUNTIME_VOLUME_NAME` | `mini_prod_playbook_runtime` | Named volume для runtime-каталогов |
| `ANSIBLE_VALIDATOR_MAX_CONCURRENCY` | `4` | Жёсткий лимит одновременных validator requests |
| `ANSIBLE_VALIDATOR_READ_TIMEOUT_SECONDS` | `10` | Таймаут чтения одного validator request |

Scavenger запускается при старте execution worker. Он рассматривает только каталоги точного вида
`pb-r<run>-d<dispatch>-a<attempt>`, старше TTL, не следует symlink и сначала проверяет/удаляет
контейнер с совпадающими labels. Произвольные каталоги и runtime с неподтверждённой identity
остаются нетронутыми для ручного расследования.

## Почему не `stdout_callback=json`?

В ansible-core **нет** встроенного callback `json` (часто нужен `ansible.posix`).  
WebTerm использует **default callback + PLAY RECAP** — работает везде без плагинов.
