import json

from django.contrib.auth.models import User

from core_ui.models import UserAppPermission


def json_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def llm_node(node_id: str) -> dict:
    return {
        "id": node_id,
        "type": "agent/llm_query",
        "position": {"x": 0, "y": 0},
        "data": {"prompt": "Summarize output", "provider": "gemini"},
    }


def grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )
