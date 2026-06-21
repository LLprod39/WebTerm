"""User-focused Keycloak admin client operations."""

from __future__ import annotations

from typing import Any

from key_mcp_client_support import (
    EMAIL_DOMAIN_CANDIDATES,
    MAX_SEARCH_RESULTS,
    ToolError,
    _dedupe_by_key,
    _looks_like_uuid,
)
from key_mcp_config import clean_text as _clean_text


class KeycloakUserMixin:
    def search_users(self, query: str, *, exact: bool = False, max_results: int = MAX_SEARCH_RESULTS) -> list[dict[str, Any]]:
        if exact:
            query_clean = _clean_text(query).lower()
            exact_matches: list[dict[str, Any]] = []
            exact_matches.extend(
                user
                for user in self._get_json(
                    f"{self.config.admin_base_url}/users",
                    params={"username": query, "exact": "true", "max": max(1, min(int(max_results), MAX_SEARCH_RESULTS))},
                )
                or []
                if isinstance(user, dict) and _clean_text(user.get("username")).lower() == query_clean
            )
            if "@" in query_clean:
                exact_matches.extend(
                    user
                    for user in self.search_users_by_email(query_clean)
                    if _clean_text(user.get("email")).lower() == query_clean
                )
            return _dedupe_by_key(exact_matches)

        params: dict[str, Any] = {
            "search": query,
            "max": max(1, min(int(max_results), MAX_SEARCH_RESULTS)),
        }
        if exact:
            params["exact"] = "true"
        users = self._get_json(f"{self.config.admin_base_url}/users", params=params)
        return [item for item in users if isinstance(item, dict)] if isinstance(users, list) else []

    def search_users_by_email(self, email: str) -> list[dict[str, Any]]:
        users = self._get_json(
            f"{self.config.admin_base_url}/users",
            params={"email": email, "exact": "true", "max": MAX_SEARCH_RESULTS},
        )
        return [item for item in users if isinstance(item, dict)] if isinstance(users, list) else []

    def get_user_by_id(self, user_id: str) -> dict[str, Any]:
        if not _looks_like_uuid(user_id):
            raise ToolError(f"Invalid Keycloak user_id: {user_id}")
        user = self._get_json(f"{self.config.admin_base_url}/users/{user_id}")
        if not isinstance(user, dict):
            raise ToolError(f"Keycloak user '{user_id}' was not found")
        return user

    def _email_variants(self, login: str) -> list[str]:
        login_clean = login.strip().lower()
        if "@" in login_clean:
            return [login_clean]
        return [f"{login_clean}@{domain}" for domain in EMAIL_DOMAIN_CANDIDATES]

    def _score_user_match(self, original_login: str, user: dict[str, Any]) -> tuple[int, list[str]]:
        original = original_login.lower()
        username = _clean_text(user.get("username")).lower()
        email = _clean_text(user.get("email")).lower()
        first_name = _clean_text(user.get("firstName")).lower()
        last_name = _clean_text(user.get("lastName")).lower()
        local_email = email.split("@", 1)[0] if email else ""
        score = 0
        reasons: list[str] = []

        if username == original:
            score += 140
            reasons.append("exact_username")
        if email == original:
            score += 130
            reasons.append("exact_email")
        if local_email == original:
            score += 110
            reasons.append("exact_email_local_part")
        if original in username and username != original:
            score += 55
            reasons.append("username_contains_query")
        if username and username in original and username != original:
            score += 30
            reasons.append("query_contains_username")

        parts = [item for item in original.replace(".", " ").replace("_", " ").split() if len(item) >= 3]
        for part in parts:
            if part in username:
                score += 25
                reasons.append(f"username_part:{part}")
            if part in first_name:
                score += 20
                reasons.append(f"first_name_part:{part}")
            if part in last_name:
                score += 20
                reasons.append(f"last_name_part:{part}")
            if part in email:
                score += 10
                reasons.append(f"email_part:{part}")

        return score, reasons

    def search_user_candidates(self, login: str, *, max_candidates: int = 5) -> list[dict[str, Any]]:
        login_clean = login.strip().lower()
        if not login_clean:
            return []

        raw_candidates: list[dict[str, Any]] = []
        raw_candidates.extend(self.search_users(login_clean, exact=True))
        for email in self._email_variants(login_clean):
            raw_candidates.extend(self.search_users_by_email(email))

        search_terms = {login_clean}
        search_terms.update(part for part in login_clean.replace(".", " ").replace("_", " ").split() if len(part) >= 3)
        for term in sorted(search_terms):
            raw_candidates.extend(self.search_users(term, exact=False))

        ranked: list[dict[str, Any]] = []
        for user in _dedupe_by_key(raw_candidates):
            score, reasons = self._score_user_match(login_clean, user)
            if score <= 0:
                continue
            ranked.append({"user": user, "score": score, "reasons": reasons})

        ranked.sort(key=lambda item: (-int(item["score"]), _clean_text(item["user"].get("username"))))
        return ranked[: max(1, max_candidates)]

    def find_user_advanced(self, login: str) -> dict[str, Any] | None:
        candidates = self.search_user_candidates(login, max_candidates=1)
        if not candidates:
            return None
        top = candidates[0]
        if int(top["score"]) < 40:
            return None
        return top["user"]

    def resolve_user(self, *, login: str | None = None, user_id: str | None = None, allow_fuzzy: bool = False) -> dict[str, Any]:
        if user_id:
            return self.get_user_by_id(user_id)

        login_clean = _clean_text(login)
        if not login_clean:
            raise ToolError("Either user_id or login is required")

        exact_matches: list[dict[str, Any]] = []
        exact_matches.extend(
            user
            for user in self.search_users(login_clean, exact=True)
            if _clean_text(user.get("username")).lower() == login_clean.lower()
        )
        for email in self._email_variants(login_clean):
            exact_matches.extend(
                user for user in self.search_users_by_email(email) if _clean_text(user.get("email")).lower() == email.lower()
            )

        exact_matches = _dedupe_by_key(exact_matches)
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            usernames = [_clean_text(item.get("username")) for item in exact_matches[:5]]
            raise ToolError(f"Ambiguous exact user match for '{login_clean}': {', '.join(usernames)}")

        if not allow_fuzzy:
            raise ToolError(
                f"Exact user match not found for '{login_clean}'. Use user_id or allow_fuzzy_user_match=true after verification."
            )

        candidates = self.search_user_candidates(login_clean, max_candidates=3)
        if not candidates:
            raise ToolError(f"User '{login_clean}' not found")

        top = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        if int(top["score"]) < 90:
            raise ToolError(f"Fuzzy match for '{login_clean}' is too weak. Verify the user first.")
        if second and int(second["score"]) >= int(top["score"]) - 5:
            raise ToolError(f"Fuzzy match for '{login_clean}' is ambiguous. Verify the user first.")
        return top["user"]

    def create_user(
        self,
        *,
        username: str,
        email: str,
        first_name: str = "",
        last_name: str = "",
        enabled: bool = True,
        temporary_password: str | None = None,
        attributes: dict[str, Any] | None = None,
        required_actions: list[str] | None = None,
    ) -> str:
        user_data: dict[str, Any] = {
            "username": username,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": enabled,
            "emailVerified": False,
        }
        if attributes:
            user_data["attributes"] = attributes
        if required_actions:
            user_data["requiredActions"] = required_actions

        response = self._post_json(f"{self.config.admin_base_url}/users", user_data, allow_statuses=(201,))
        location = response.headers.get("Location", "")
        user_id = location.rstrip("/").split("/")[-1] if location else ""
        if not user_id:
            created_user = self.resolve_user(login=username, allow_fuzzy=False)
            user_id = _clean_text(created_user.get("id"))
        if temporary_password:
            self.set_user_password(user_id, temporary_password, temporary=True)
        return user_id

    def set_user_password(self, user_id: str, password: str, *, temporary: bool = True) -> None:
        self._put_json(
            f"{self.config.admin_base_url}/users/{user_id}/reset-password",
            {"type": "password", "value": password, "temporary": temporary},
        )
