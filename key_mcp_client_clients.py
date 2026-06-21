"""Client, role, and protocol-mapper Keycloak admin operations."""

from __future__ import annotations

from typing import Any

from key_mcp_client_support import ToolError, _dedupe_by_key
from key_mcp_config import clean_text as _clean_text


class KeycloakClientMixin:
    def list_clients(self, *, search: str = "", max_results: int = 50) -> list[dict[str, Any]]:
        target = _clean_text(search).lower()
        limit = max(1, min(int(max_results), 500))
        page_size = 200
        scan_limit = 1000 if target else limit
        offset = 0
        collected: list[dict[str, Any]] = []

        while offset < scan_limit:
            batch_size = min(page_size, scan_limit - offset)
            batch = self._get_json(f"{self.config.admin_base_url}/clients", params={"first": offset, "max": batch_size})
            items = [item for item in batch if isinstance(item, dict)] if isinstance(batch, list) else []
            if not items:
                break
            collected.extend(items)
            if len(items) < batch_size:
                break
            offset += batch_size
            if not target and len(collected) >= limit:
                break

        clients = _dedupe_by_key(collected)
        if not target:
            clients.sort(key=lambda item: (_clean_text(item.get("clientId")), _clean_text(item.get("name"))))
            return clients[:limit]

        ranked: list[tuple[int, dict[str, Any]]] = []
        for client in clients:
            client_id = _clean_text(client.get("clientId")).lower()
            name = _clean_text(client.get("name")).lower()
            description = _clean_text(client.get("description")).lower()
            score = 0
            if client_id == target:
                score += 200
            if name == target:
                score += 160
            if target in client_id and client_id != target:
                score += 90
            if target in name and name != target:
                score += 70
            if target in description:
                score += 30
            normalized_target = target.replace("-", "").replace("_", "").replace(" ", "")
            normalized_client_id = client_id.replace("-", "").replace("_", "").replace(" ", "")
            if normalized_target and normalized_client_id == normalized_target:
                score += 120
            if score > 0:
                ranked.append((score, client))

        ranked.sort(key=lambda item: (-item[0], _clean_text(item[1].get("clientId"))))
        return [client for _, client in ranked[:limit]]

    def find_clients_with_role(self, role_name: str, *, search: str = "", max_results: int = 50) -> list[dict[str, Any]]:
        target_role = _clean_text(role_name)
        if not target_role:
            return []
        candidates = self.list_clients(search=search, max_results=max_results)
        matches: list[dict[str, Any]] = []
        for client in candidates:
            client_uuid = _clean_text(client.get("id"))
            client_id = _clean_text(client.get("clientId"))
            if not client_uuid or not client_id:
                continue
            role_map = self.get_client_roles(client_uuid)
            if target_role in role_map:
                matches.append(client)
        return matches

    def get_client_uuid(self, client_id: str | None = None) -> str:
        target_client_id = _clean_text(client_id) or self.config.client_id
        if not target_client_id:
            raise ToolError("client_id is required")
        clients = self._get_json(f"{self.config.admin_base_url}/clients", params={"clientId": target_client_id})
        items = [item for item in clients if isinstance(item, dict)] if isinstance(clients, list) else []
        matches = [item for item in items if _clean_text(item.get("clientId")) == target_client_id]
        if not matches:
            raise ToolError(f"Client '{target_client_id}' not found in realm '{self.config.realm}'")
        if len(matches) > 1:
            raise ToolError(f"Multiple clients matched client_id '{target_client_id}'")
        return _clean_text(matches[0].get("id"))

    def get_client_roles(self, client_uuid: str) -> dict[str, dict[str, Any]]:
        roles = self._get_json(f"{self.config.admin_base_url}/clients/{client_uuid}/roles")
        if not isinstance(roles, list):
            return {}
        return {
            _clean_text(role.get("name")): role
            for role in roles
            if isinstance(role, dict) and _clean_text(role.get("name"))
        }

    def get_user_client_roles(self, user_id: str, client_uuid: str) -> list[dict[str, Any]]:
        roles = self._get_json(f"{self.config.admin_base_url}/users/{user_id}/role-mappings/clients/{client_uuid}")
        return [item for item in roles if isinstance(item, dict)] if isinstance(roles, list) else []

    def assign_client_roles(self, user_id: str, client_uuid: str, roles: list[dict[str, Any]]) -> None:
        self._post_json(
            f"{self.config.admin_base_url}/users/{user_id}/role-mappings/clients/{client_uuid}",
            roles,
            allow_statuses=(204,),
        )

    def get_realm_roles(self) -> dict[str, dict[str, Any]]:
        roles = self._get_json(f"{self.config.admin_base_url}/roles")
        if not isinstance(roles, list):
            return {}
        return {
            _clean_text(role.get("name")): role
            for role in roles
            if isinstance(role, dict) and _clean_text(role.get("name"))
        }

    def create_realm_role(self, role_name: str, description: str = "") -> dict[str, Any]:
        role = {
            "name": role_name,
            "description": description,
            "composite": False,
            "clientRole": False,
        }
        self._post_json(f"{self.config.admin_base_url}/roles", role, allow_statuses=(201,))
        return role

    def assign_realm_roles(self, user_id: str, roles: list[dict[str, Any]]) -> None:
        self._post_json(
            f"{self.config.admin_base_url}/users/{user_id}/role-mappings/realm",
            roles,
            allow_statuses=(204,),
        )

    def get_user_realm_roles(self, user_id: str) -> list[dict[str, Any]]:
        roles = self._get_json(f"{self.config.admin_base_url}/users/{user_id}/role-mappings/realm")
        return [item for item in roles if isinstance(item, dict)] if isinstance(roles, list) else []

    def create_client_role(self, client_uuid: str, role_name: str, description: str = "") -> dict[str, Any]:
        role = {
            "name": role_name,
            "description": description,
            "composite": False,
            "clientRole": True,
        }
        self._post_json(f"{self.config.admin_base_url}/clients/{client_uuid}/roles", role, allow_statuses=(201,))
        return role

    def create_client(
        self,
        *,
        client_id: str,
        name: str,
        description: str,
        service_accounts_enabled: bool = True,
        direct_access_grants_enabled: bool = True,
        standard_flow_enabled: bool = True,
        public_client: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "clientId": client_id,
            "name": name or client_id,
            "description": description,
            "enabled": True,
            "serviceAccountsEnabled": service_accounts_enabled,
            "directAccessGrantsEnabled": direct_access_grants_enabled,
            "standardFlowEnabled": standard_flow_enabled,
            "implicitFlowEnabled": False,
            "publicClient": public_client,
            "protocol": "openid-connect",
        }
        response = self._post_json(f"{self.config.admin_base_url}/clients", payload, allow_statuses=(201,))
        location = response.headers.get("Location", "")
        client_uuid = location.rstrip("/").split("/")[-1] if location else self.get_client_uuid(client_id)
        return {"id": client_uuid, "clientId": client_id, "name": name or client_id}

    def add_protocol_mapper(
        self,
        *,
        client_uuid: str,
        mapper_name: str,
        user_attribute: str,
        token_claim: str,
        add_to_id_token: bool = True,
        add_to_access_token: bool = True,
    ) -> dict[str, Any]:
        mapper = {
            "name": mapper_name,
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "consentRequired": False,
            "config": {
                "userinfo.token.claim": "true",
                "user.attribute": user_attribute,
                "id.token.claim": str(add_to_id_token).lower(),
                "access.token.claim": str(add_to_access_token).lower(),
                "claim.name": token_claim,
                "jsonType.label": "String",
            },
        }
        self._post_json(
            f"{self.config.admin_base_url}/clients/{client_uuid}/protocol-mappers/models",
            mapper,
            allow_statuses=(201,),
        )
        return {"name": mapper_name, "userAttribute": user_attribute, "tokenClaim": token_claim}

    def list_protocol_mappers(self, client_uuid: str) -> list[dict[str, Any]]:
        mappers = self._get_json(f"{self.config.admin_base_url}/clients/{client_uuid}/protocol-mappers/models")
        return [item for item in mappers if isinstance(item, dict)] if isinstance(mappers, list) else []

    def get_client_service_account_user(self, client_uuid: str) -> dict[str, Any]:
        user = self._get_json(f"{self.config.admin_base_url}/clients/{client_uuid}/service-account-user")
        if not isinstance(user, dict):
            raise ToolError(f"Service account user for client '{client_uuid}' was not found")
        return user
