from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from jules_tg_orchestrator.coordinator import DelegationDraft


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.migrate()

    def close(self) -> None:
        self.connection.close()

    def migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                task_id INTEGER,
                chat_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                branch TEXT NOT NULL,
                state TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                last_activity_id TEXT NOT NULL DEFAULT '',
                is_watched INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS activity_events (
                session_id TEXT NOT NULL,
                activity_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, activity_id)
            );

            CREATE TABLE IF NOT EXISTS drafts (
                chat_id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                project_root TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                branch TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'NEW',
                priority TEXT NOT NULL DEFAULT 'normal',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS task_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                agent_kind TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                output TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._ensure_column("sessions", "task_id", "INTEGER")
        self.connection.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        rows = self.connection.execute(f"PRAGMA table_info({table})").fetchall()
        if any(row["name"] == column for row in rows):
            return
        self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def upsert_session(
        self,
        *,
        session_id: str,
        chat_id: int,
        title: str,
        source: str,
        branch: str,
        state: str,
        url: str = "",
        is_watched: bool = True,
        task_id: int | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO sessions (session_id, task_id, chat_id, title, source, branch, state, url, is_watched)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                task_id=COALESCE(excluded.task_id, sessions.task_id),
                chat_id=excluded.chat_id,
                title=excluded.title,
                source=excluded.source,
                branch=excluded.branch,
                state=excluded.state,
                url=excluded.url,
                is_watched=excluded.is_watched,
                updated_at=CURRENT_TIMESTAMP
            """,
            (session_id, task_id, chat_id, title, source, branch, state, url, int(is_watched)),
        )
        self.connection.commit()

    def update_session_state(self, session_id: str, *, state: str, url: str = "") -> None:
        self.connection.execute(
            """
            UPDATE sessions
            SET state = ?, url = COALESCE(NULLIF(?, ''), url), updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
            """,
            (state, url, session_id),
        )
        self.connection.commit()

    def set_watched(self, session_id: str, watched: bool) -> None:
        self.connection.execute(
            "UPDATE sessions SET is_watched = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (int(watched), session_id),
        )
        self.connection.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def list_sessions(self, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_watched_sessions(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM sessions
            WHERE is_watched = 1 AND state NOT IN ('COMPLETED', 'FAILED')
            ORDER BY updated_at ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_activity_seen(self, session_id: str, activity_id: str) -> bool:
        try:
            self.connection.execute(
                "INSERT INTO activity_events (session_id, activity_id) VALUES (?, ?)",
                (session_id, activity_id),
            )
        except sqlite3.IntegrityError:
            return False
        self.connection.commit()
        return True

    def save_draft(self, chat_id: int, draft: DelegationDraft) -> None:
        self.connection.execute(
            """
            INSERT INTO drafts (chat_id, payload)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                payload=excluded.payload,
                updated_at=CURRENT_TIMESTAMP
            """,
            (chat_id, json.dumps(asdict(draft), ensure_ascii=False)),
        )
        self.connection.commit()

    def get_draft(self, chat_id: int) -> DelegationDraft | None:
        row = self.connection.execute("SELECT payload FROM drafts WHERE chat_id = ?", (chat_id,)).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload"])
        return DelegationDraft(**payload)

    def clear_draft(self, chat_id: int) -> None:
        self.connection.execute("DELETE FROM drafts WHERE chat_id = ?", (chat_id,))
        self.connection.commit()

    def create_task(
        self,
        *,
        chat_id: int,
        title: str,
        description: str,
        project_root: str = "",
        source: str = "",
        branch: str = "",
        status: str = "NEW",
        priority: str = "normal",
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO tasks (chat_id, title, description, project_root, source, branch, status, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, title, description, project_root, source, branch, status, priority),
        )
        task_id = int(cursor.lastrowid)
        self.add_task_event(task_id, kind="created", message="Task created")
        self.connection.commit()
        return task_id

    def update_task(self, task_id: int, **fields: str) -> None:
        allowed = {"title", "description", "project_root", "source", "branch", "status", "priority"}
        updates = [(key, value) for key, value in fields.items() if key in allowed]
        if not updates:
            return
        set_clause = ", ".join(f"{key} = ?" for key, _ in updates)
        values = [value for _, value in updates]
        values.append(task_id)
        self.connection.execute(
            f"UPDATE tasks SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?",
            values,
        )
        self.connection.commit()

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_task_event(
        self,
        task_id: int,
        *,
        kind: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO task_events (task_id, kind, message, payload)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, kind, message, json.dumps(payload or {}, ensure_ascii=False)),
        )
        self.connection.commit()

    def list_task_events(self, task_id: int, *, limit: int = 15) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM task_events
            WHERE task_id = ?
            ORDER BY event_id DESC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def create_agent_run(self, *, task_id: int, agent_kind: str, status: str = "RUNNING") -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO agent_runs (task_id, agent_kind, status)
            VALUES (?, ?, ?)
            """,
            (task_id, agent_kind, status),
        )
        run_id = int(cursor.lastrowid)
        self.connection.commit()
        return run_id

    def update_agent_run(self, run_id: int, *, status: str, summary: str = "", output: str = "") -> None:
        self.connection.execute(
            """
            UPDATE agent_runs
            SET status = ?, summary = ?, output = ?, updated_at = CURRENT_TIMESTAMP
            WHERE run_id = ?
            """,
            (status, summary, output, run_id),
        )
        self.connection.commit()

    def list_task_agent_runs(self, task_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM agent_runs
            WHERE task_id = ?
            ORDER BY run_id DESC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_state(self, key: str, *, default: str = "") -> str:
        row = self.connection.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_state(self, key: str, value: str) -> None:
        self.connection.execute(
            """
            INSERT INTO app_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        self.connection.commit()

    def delete_state(self, key: str) -> None:
        self.connection.execute("DELETE FROM app_state WHERE key = ?", (key,))
        self.connection.commit()
