from __future__ import annotations

from servers.services.command_history import save_command_history_entry


class DjangoCommandHistoryProvider:
    def save_command_history_entry(
        self,
        *,
        server_id: int,
        user_id: int | None,
        command: str,
        output: str = "",
        exit_code: int | None = None,
        session_id: str = "",
        cwd: str = "",
        actor_kind: str = "human",
        source_kind: str = "terminal",
    ) -> None:
        save_command_history_entry(
            server_id=server_id,
            user_id=user_id,
            command=command,
            output=output,
            exit_code=exit_code,
            session_id=session_id,
            cwd=cwd,
            actor_kind=actor_kind,
            source_kind=source_kind,
        )
