"""operator.todo_write live checklist."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext, AssistantActionError, get_action_spec
from servers.operator.tools_actions import todo_write


@pytest.mark.django_db
def test_todo_write_registered():
    assert get_action_spec("operator.todo_write") is not None


@pytest.mark.django_db
def test_todo_write_builds_plan_for_ui():
    user = User.objects.create_user("todo-user", password="x")
    result = todo_write(
        AssistantActionContext(
            user=user,
            input_payload={
                "title": "Создание",
                "todos": [
                    {"id": "1", "content": "Создать плейбук", "status": "completed"},
                    {"id": "2", "content": "Создать агента", "status": "in_progress"},
                    {"id": "3", "content": "Поставить расписание", "status": "pending"},
                    {"id": "4", "content": "Лишнее in_progress", "status": "in_progress"},
                ],
            },
        )
    )
    assert result["ok"] is True
    assert result["in_progress"] == 1
    assert result["completed"] == 1
    assert result["plan"]["title"] == "Создание"
    assert result["plan"]["steps"][0]["status"] == "done"
    assert result["plan"]["steps"][1]["status"] == "running"
    assert result["plan"]["steps"][3]["status"] == "pending"  # second in_progress demoted
    assert result["todos"][3]["status"] == "pending"


@pytest.mark.django_db
def test_todo_write_requires_items():
    user = User.objects.create_user("todo-empty", password="x")
    with pytest.raises(AssistantActionError):
        todo_write(AssistantActionContext(user=user, input_payload={"todos": []}))
