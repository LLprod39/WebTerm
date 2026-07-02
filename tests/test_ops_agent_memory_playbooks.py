import pytest
from django.contrib.auth.models import User

from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import Server, ServerKnowledge


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_surfaces_operational_playbooks_in_server_card():
    owner = User.objects.create_user(username="ops-memory-playbook-user", password="x")
    server = Server.objects.create(user=owner, name="playbook-node", host="10.0.0.63", port=22, username="root")
    knowledge = ServerKnowledge.objects.create(
        server=server,
        category="solutions",
        title="Operational Skill: nginx recovery",
        content=(
            "- Связанный skill: nginx-recovery\n"
            "- Когда использовать: после неудачного reload или деплоя.\n"
            "- Workflow: systemctl restart nginx -> systemctl is-active nginx\n"
            "- Сигналы успеха: active (running)\n"
            "- Открыть/редактировать skill в Studio при следующем изменении operational playbook."
        ),
        source="manual",
        confidence=0.95,
        created_by=owner,
    )

    store = DjangoServerMemoryStore()
    store._sync_manual_knowledge_snapshot_sync(knowledge.id)

    card = store._get_server_card_sync(server.id)
    prompt_text = card.as_prompt_block()

    assert card.operational_playbooks
    assert any("nginx recovery" in item.lower() for item in card.operational_playbooks)
    assert "Operational playbooks:" in prompt_text
    assert "nginx-recovery" in prompt_text
    assert "Открыть/редактировать skill" not in prompt_text


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_builds_operational_recipes_prompt_from_manual_skill_notes():
    owner = User.objects.create_user(username="ops-memory-recipes-user", password="x")
    server = Server.objects.create(user=owner, name="recipes-node", host="10.0.0.66", port=22, username="root")
    knowledge = ServerKnowledge.objects.create(
        server=server,
        category="solutions",
        title="Operational Skill: docker rollout",
        content=(
            "- Связанный skill: docker-rollout\n"
            "- Когда использовать: controlled rollout docker compose сервиса.\n"
            "- Workflow: docker compose pull -> docker compose up -d -> docker compose ps\n"
            "- Сигналы успеха: healthy | Up\n"
        ),
        source="manual",
        confidence=0.92,
        created_by=owner,
    )

    store = DjangoServerMemoryStore()
    store._sync_manual_knowledge_snapshot_sync(knowledge.id)
    prompt = store._build_operational_recipes_prompt_sync(
        "Нужен deploy docker compose rollout с проверкой health",
        server_ids=[server.id],
        limit=4,
    )

    assert "docker rollout" in prompt.lower()
    assert "docker compose" in prompt.lower()
    assert "[server/solutions]" in prompt
