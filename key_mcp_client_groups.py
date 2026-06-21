"""Group-related Keycloak admin client operations."""

from __future__ import annotations

from typing import Any

from key_mcp_client_support import DEFAULT_GROUP_PAGE_SIZE, ToolError, _dedupe_by_key
from key_mcp_config import clean_text as _clean_text
from key_mcp_summaries import _group_summary


class KeycloakGroupMixin:
    def list_groups(self, *, search: str = "", max_results: int = DEFAULT_GROUP_PAGE_SIZE) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "briefRepresentation": "false",
            "max": max(1, min(int(max_results), 1000)),
        }
        if _clean_text(search):
            params["search"] = search
        groups = self._get_json(f"{self.config.admin_base_url}/groups", params=params)
        return [item for item in groups if isinstance(item, dict)] if isinstance(groups, list) else []

    def flatten_groups(self, groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []
        stack = list(groups)
        while stack:
            current = stack.pop(0)
            flat.append(current)
            stack.extend(item for item in current.get("subGroups") or [] if isinstance(item, dict))
        return flat

    def resolve_group(self, identifier: str) -> dict[str, Any]:
        value = _clean_text(identifier)
        if not value:
            raise ToolError("Group identifier is required")
        groups = self.flatten_groups(self.list_groups(search=value, max_results=500))
        matches = _dedupe_by_key(
            [
                group
                for group in groups
                if _clean_text(group.get("id")) == value
                or _clean_text(group.get("name")) == value
                or _clean_text(group.get("path")) == value
            ]
        )
        if not matches:
            raise ToolError(f"Group '{value}' not found")
        if len(matches) > 1:
            names = [_clean_text(item.get("path")) or _clean_text(item.get("name")) for item in matches[:5]]
            raise ToolError(f"Ambiguous group match for '{value}': {', '.join(names)}")
        return matches[0]

    def get_user_groups(self, user_id: str) -> list[dict[str, Any]]:
        groups = self._get_json(f"{self.config.admin_base_url}/users/{user_id}/groups")
        return [item for item in groups if isinstance(item, dict)] if isinstance(groups, list) else []

    def add_user_to_group(self, user_id: str, group_id: str) -> None:
        self._put_empty(f"{self.config.admin_base_url}/users/{user_id}/groups/{group_id}")

    def create_group(self, name: str, *, parent_group: str = "") -> dict[str, Any]:
        payload = {"name": name}
        parent_value = _clean_text(parent_group)
        if parent_value:
            parent = self.resolve_group(parent_value)
            response = self._post_json(
                f"{self.config.admin_base_url}/groups/{_clean_text(parent.get('id'))}/children",
                payload,
                allow_statuses=(201, 204),
            )
            location = response.headers.get("Location", "")
            group_id = location.rstrip("/").split("/")[-1] if location else ""
            if group_id:
                created = self.resolve_group(group_id)
            else:
                created = self.resolve_group(f"{_clean_text(parent.get('path'))}/{name}")
            return _group_summary(created)

        response = self._post_json(f"{self.config.admin_base_url}/groups", payload, allow_statuses=(201, 204))
        location = response.headers.get("Location", "")
        group_id = location.rstrip("/").split("/")[-1] if location else ""
        created = self.resolve_group(group_id) if group_id else self.resolve_group(f"/{name}")
        return _group_summary(created)
