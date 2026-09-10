# Realtime contracts

| WebSocket | Назначение |
|---|---|
| /ws/servers/{server_id}/terminal/ | ready -> connect; input/resize/disconnect; output/status/error/exit, AI events |
| /ws/monitoring/live/ | live samples доступных серверов |
| /ws/agents/{run_id}/live/ | ход агента; REST cursor events дополняют восстановление |
| /ws/operator/{chat_id}/ | Operator turn_snapshot и события, сообщения/confirmations |
| Studio run WS | pipeline.node.event / pipeline.node.state / pipeline.status; path см. research |
| MARS WS | ход run; path см. research |
| Kubernetes WS | scoped admin/watch/log sessions по backend-issued routes |

Общий transport frontend/src/realtime/socket.ts: connecting / connected / reconnecting / disconnected / failed, ограниченный exponential backoff, явное отключение, без повторной отправки mutating messages. WS transport connected не равен SSH connected. Последнее событие, stale состояние и retry видимы. Cleanup закрывает соединение при уходе с маршрута/смене проекта.

