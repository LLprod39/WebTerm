"""Tests for servers.services.terminal_ai.history (F2-9)."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from servers.models import Server, TerminalAiChatMessage
from servers.services.terminal_ai.history import (
    MAX_TEXT_LEN,
    append_message_sync,
    clear_history_sync,
    load_recent_sync,
)


def _make_user_and_server(username: str = "hist-user") -> tuple[User, Server]:
    user = User.objects.create_user(username=username, password="x")
    server = Server.objects.create(
        user=user,
        name="hist-srv",
        host="10.0.0.100",
        username="root",
        auth_method="password",
    )
    return user, server


@pytest.mark.django_db
class TestAppendMessage:
    def test_persists_user_turn(self):
        user, server = _make_user_and_server()
        result = append_message_sync(
            user_id=user.id,
            server_id=server.id,
            role="user",
            text="проверь nginx",
        )
        assert result == {"stored": True, "pruned": 0}
        msg = TerminalAiChatMessage.objects.get(user=user, server=server)
        assert msg.role == "user"
        assert msg.text == "проверь nginx"

    def test_persists_assistant_turn(self):
        user, server = _make_user_and_server()
        result = append_message_sync(
            user_id=user.id,
            server_id=server.id,
            role="assistant",
            text="nginx работает",
        )
        assert result["stored"] is True
        assert TerminalAiChatMessage.objects.filter(user=user).count() == 1

    def test_invalid_role_rejected(self):
        user, server = _make_user_and_server()
        result = append_message_sync(
            user_id=user.id,
            server_id=server.id,
            role="system",
            text="secret",
        )
        assert result == {"stored": False, "pruned": 0}
        assert TerminalAiChatMessage.objects.count() == 0

    def test_empty_text_rejected(self):
        user, server = _make_user_and_server()
        result = append_message_sync(
            user_id=user.id,
            server_id=server.id,
            role="user",
            text="   ",
        )
        assert result == {"stored": False, "pruned": 0}

    def test_text_truncated_to_max(self):
        user, server = _make_user_and_server()
        long_text = "x" * (MAX_TEXT_LEN + 200)
        append_message_sync(
            user_id=user.id,
            server_id=server.id,
            role="user",
            text=long_text,
        )
        row = TerminalAiChatMessage.objects.get(user=user)
        assert len(row.text) == MAX_TEXT_LEN

    def test_pruning_keeps_newest_entries(self):
        user, server = _make_user_and_server()
        # Insert 10 messages with max_entries=5 → 5 oldest should be deleted.
        for i in range(10):
            append_message_sync(
                user_id=user.id,
                server_id=server.id,
                role="user",
                text=f"msg-{i}",
                max_entries=5,
            )
        rows = list(
            TerminalAiChatMessage.objects.filter(user=user, server=server).order_by("created_at").values_list("text", flat=True)
        )
        assert len(rows) == 5
        # Newest 5 are preserved
        assert rows == [f"msg-{i}" for i in range(5, 10)]

    def test_pruning_isolated_by_user_and_server(self):
        user_a, server_a = _make_user_and_server("user-a")
        user_b, server_b = _make_user_and_server("user-b")
        # Both users write 3 messages. max_entries=2 → each keeps 2 independently.
        for i in range(3):
            append_message_sync(
                user_id=user_a.id, server_id=server_a.id, role="user", text=f"a-{i}", max_entries=2
            )
            append_message_sync(
                user_id=user_b.id, server_id=server_b.id, role="user", text=f"b-{i}", max_entries=2
            )
        assert TerminalAiChatMessage.objects.filter(user=user_a).count() == 2
        assert TerminalAiChatMessage.objects.filter(user=user_b).count() == 2


@pytest.mark.django_db
class TestLoadRecent:
    def test_returns_oldest_to_newest(self):
        user, server = _make_user_and_server()
        for i in range(5):
            append_message_sync(
                user_id=user.id, server_id=server.id, role="user", text=f"m-{i}"
            )
        rows = load_recent_sync(user_id=user.id, server_id=server.id, limit=10)
        assert [r["text"] for r in rows] == [f"m-{i}" for i in range(5)]
        # All entries have the expected shape
        assert all(set(r.keys()) == {"role", "text"} for r in rows)

    def test_limit_respected(self):
        user, server = _make_user_and_server()
        for i in range(20):
            append_message_sync(
                user_id=user.id, server_id=server.id, role="user", text=f"m-{i}"
            )
        rows = load_recent_sync(user_id=user.id, server_id=server.id, limit=5)
        # Last 5 in chronological order (oldest first within the window)
        assert [r["text"] for r in rows] == [f"m-{i}" for i in range(15, 20)]

    def test_zero_limit_returns_empty(self):
        user, server = _make_user_and_server()
        append_message_sync(user_id=user.id, server_id=server.id, role="user", text="x")
        assert load_recent_sync(user_id=user.id, server_id=server.id, limit=0) == []

    def test_scoped_to_user_and_server(self):
        user_a, server_a = _make_user_and_server("scope-a")
        user_b, server_b = _make_user_and_server("scope-b")
        append_message_sync(user_id=user_a.id, server_id=server_a.id, role="user", text="from-a")
        append_message_sync(user_id=user_b.id, server_id=server_b.id, role="user", text="from-b")

        rows_a = load_recent_sync(user_id=user_a.id, server_id=server_a.id, limit=10)
        rows_b = load_recent_sync(user_id=user_b.id, server_id=server_b.id, limit=10)

        assert [r["text"] for r in rows_a] == ["from-a"]
        assert [r["text"] for r in rows_b] == ["from-b"]


@pytest.mark.django_db
class TestClearHistory:
    def test_wipes_all_messages_for_user_server(self):
        user, server = _make_user_and_server()
        for i in range(5):
            append_message_sync(user_id=user.id, server_id=server.id, role="user", text=f"m-{i}")

        deleted = clear_history_sync(user_id=user.id, server_id=server.id)

        assert deleted == 5
        assert TerminalAiChatMessage.objects.filter(user=user, server=server).count() == 0

    def test_does_not_touch_other_users_history(self):
        user_a, server_a = _make_user_and_server("clear-a")
        user_b, server_b = _make_user_and_server("clear-b")
        append_message_sync(user_id=user_a.id, server_id=server_a.id, role="user", text="keep-a")
        append_message_sync(user_id=user_b.id, server_id=server_b.id, role="user", text="keep-b")

        clear_history_sync(user_id=user_a.id, server_id=server_a.id)

        assert TerminalAiChatMessage.objects.filter(user=user_a).count() == 0
        assert TerminalAiChatMessage.objects.filter(user=user_b).count() == 1


@pytest.mark.django_db
class TestFullRoundtrip:
    def test_append_then_load_yields_chronological_conversation(self):
        user, server = _make_user_and_server()
        turns = [
            ("user", "установи nginx"),
            ("assistant", "устанавливаю..."),
            ("user", "готово?"),
            ("assistant", "да"),
        ]
        for role, text in turns:
            append_message_sync(user_id=user.id, server_id=server.id, role=role, text=text)

        loaded = load_recent_sync(user_id=user.id, server_id=server.id, limit=10)
        assert [(r["role"], r["text"]) for r in loaded] == turns
