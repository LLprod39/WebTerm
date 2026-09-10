# WebTerm Frontend Next — модель продукта

Источник: текущий backend C:/WebTrerm, 2026-09-02. Старый frontend и Git-история не используются.

WebTerm — control plane для операторов инфраструктуры. Пользователь входит в сессию, выбирает проект, работает с доступными серверами, запускает проверяемую автоматизацию и AI, а администратор управляет доступом, интеграциями и аудитом.

| Сущность | Связи и назначение |
|---|---|
| User / AccessProfile / Permission | Effective features определяют видимость разделов; explicit deny имеет приоритет |
| Project / Membership | Активный project ограничивает Studio/AI данные; tenant switch сбрасывает кэш |
| Server / ServerGroup / ServerShare | SSH identity, владелец, capabilities, SSH host trust, monitoring, files, knowledge |
| Playbook / Revision / Binding / Run | Редактирование, проверка runtime compatibility, привязка targets, запуск и отчёт |
| Pipeline / Draft / Run / Node | Граф автоматизации, review, запуски и события узлов |
| Agent / AgentRun / Artifact | Цель, выбранные серверы, tool execution, approval, пользовательский ответ и результат |
| AssistantChat / OperatorTurn | Сохранённая история + realtime снимок текущего выполнения |
| Kubernetes Provider / Cluster / Resource | Поддерживаемые операции через Rancher/Devtron и gated administrative sessions |
| MCP / Skill / Memory | Инструменты и знания с владельцами и отдельными правами |
| Audit / Notification / Readiness | Расследование действий, обратная связь, готовность зависимостей |

Backend ACL всегда окончательный. Интерфейс не превращает staff в универсального владельца. Неподключённая интеграция показывает причину и настройку; отсутствие данных не интерпретируется как здоровье системы.

