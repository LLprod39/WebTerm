"""LDAP / Active Directory password login helpers for production."""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.db import transaction
from loguru import logger

PILOT_GROUP_NAME = "pilot"
PILOT_GROUP_FEATURES = frozenset(
    {
        "dashboard",
        "servers",
        "agents",
        "chat",
        "automation",
        "studio",
        "studio_pipelines",
        "studio_runs",
        "studio_agents",
        "studio_skills",
        "studio_mcp",
        "studio_notifications",
    }
)

_AD_DATA_MESSAGES = {
    "525": "Неверный логин или пароль домена",
    "52e": "Неверный логин или пароль домена",
    "530": "Вход в это время запрещён политикой AD",
    "531": "Вход с этой рабочей станции запрещён",
    "532": "Срок действия пароля AD истёк",
    "533": "Учётная запись AD отключена",
    "701": "Срок действия учётной записи AD истёк",
    "773": "Требуется смена пароля AD при следующем входе",
    "775": "Учётная запись AD заблокирована (lockout). Разблокируйте в Active Directory",
}


def _ad_data_code(exc: Exception) -> str:
    info = ""
    try:
        info = str(exc.args[0].get("info", "") if exc.args else "")
    except Exception:
        info = str(exc)
    match = re.search(r"data ([0-9a-fA-F]+)", info or "")
    return match.group(1).lower() if match else ""


def _ldap_connect():
    import ldap

    uri = str(getattr(settings, "AUTH_LDAP_SERVER_URI", "") or getattr(settings, "LDAP_SERVER", "") or "")
    if not uri:
        raise RuntimeError("LDAP server is not configured")

    conn = ldap.initialize(uri)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    timeout = int(getattr(settings, "LDAP_NETWORK_TIMEOUT_SECONDS", 5) or 5)
    conn.set_option(ldap.OPT_NETWORK_TIMEOUT, timeout)
    conn.set_option(ldap.OPT_TIMEOUT, timeout)

    ca_file = str(getattr(settings, "LDAP_CA_CERT_FILE", "") or "")
    ca_dir = str(getattr(settings, "LDAP_CA_CERT_DIR", "") or "")
    ignore_cert = bool(getattr(settings, "LDAP_IGNORE_CERT", False))
    if ca_file:
        conn.set_option(ldap.OPT_X_TLS_CACERTFILE, ca_file)
    if ca_dir:
        conn.set_option(ldap.OPT_X_TLS_CACERTDIR, ca_dir)
    if ignore_cert:
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
    else:
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
    try:
        conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
    except Exception as exc:
        logger.debug("LDAP TLS context reset is unsupported: {}", exc)
    if bool(getattr(settings, "LDAP_START_TLS", False)):
        conn.start_tls_s()
    return conn


def _normalize_username(raw: str) -> str:
    value = (raw or "").strip()
    if "\\" in value:
        value = value.split("\\")[-1].strip()
    return value


def ensure_pilot_group_permissions(group: Group | None = None) -> Group:
    """Reconcile the managed pilot group to its exact feature policy."""
    from core_ui.models.access import FEATURE_CHOICES, GroupAppPermission

    with transaction.atomic():
        if group is None:
            group, _ = Group.objects.get_or_create(name=PILOT_GROUP_NAME)
        GroupAppPermission.objects.bulk_create(
            [
                GroupAppPermission(
                    group=group,
                    feature=feature,
                    allowed=feature in PILOT_GROUP_FEATURES,
                )
                for feature, _label in FEATURE_CHOICES
            ],
            update_conflicts=True,
            update_fields=["allowed"],
            unique_fields=["group", "feature"],
        )
    return group


def _ensure_pilot_group(user: User) -> None:
    if not user or not user.pk:
        return
    if user.username.strip().lower() == "admin" or user.is_superuser:
        return
    group = ensure_pilot_group_permissions()
    user.groups.add(group)


def _search_user(conn, username: str) -> tuple[str, dict[str, Any]] | None:
    import ldap
    from ldap.filter import escape_filter_chars

    base = str(getattr(settings, "LDAP_SEARCH_BASE", "") or "")
    obj_filter = str(getattr(settings, "LDAP_FILTER", "(objectClass=user)") or "(objectClass=user)")
    sam_attr = str(getattr(settings, "LDAP_USERNAME_ATTRIBUTE", "sAMAccountName") or "sAMAccountName")
    mail_attr = str(getattr(settings, "LDAP_EMAIL_ATTRIBUTE", "mail") or "mail")
    safe = escape_filter_chars(_normalize_username(username))
    # Also try raw username as typed (for UPN).
    safe_raw = escape_filter_chars((username or "").strip())
    filt = (
        f"(&{obj_filter}"
        f"(|({sam_attr}={safe})(userPrincipalName={safe_raw})(userPrincipalName={safe})"
        f"({mail_attr}={safe_raw})({mail_attr}={safe})))"
    )
    result = conn.search_s(
        base,
        ldap.SCOPE_SUBTREE,
        filt,
        [sam_attr, "userPrincipalName", mail_attr, "cn", "userAccountControl", "lockoutTime"],
    )
    for dn, attrs in result:
        if dn and isinstance(attrs, dict):
            return dn, attrs
    return None


def _attr(attrs: dict[str, Any], name: str, default: str = "") -> str:
    values = attrs.get(name) or []
    if not values:
        return default
    value = values[0]
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value or default)


def _bind_ldap_identities(username: str, password: str, identities: list[str]) -> tuple[bool, set[str], str]:
    import ldap

    seen_codes: set[str] = set()
    last_error = "Неверный логин или пароль домена"
    for identity in identities:
        user_conn = None
        try:
            user_conn = _ldap_connect()
            user_conn.simple_bind_s(identity, password)
            return True, seen_codes, ""
        except ldap.INVALID_CREDENTIALS as exc:
            code = _ad_data_code(exc)
            if code:
                seen_codes.add(code)
            last_error = _AD_DATA_MESSAGES.get(code, "Неверный логин или пароль домена")
            logger.info("LDAP bind failed for {} as {}: data={}", username, identity, code or "?")
        except Exception as exc:
            last_error = f"Ошибка LDAP: {type(exc).__name__}"
            logger.warning("LDAP bind error for {} as {}: {}", username, identity, exc)
        finally:
            if user_conn is not None:
                try:
                    user_conn.unbind_s()
                except Exception as exc:
                    logger.debug("LDAP connection cleanup failed: {}", exc)
    return False, seen_codes, last_error


def _preferred_bind_error(seen_codes: set[str], lockout: str, fallback: str) -> str:
    try:
        lockout_active = int(lockout or "0") > 0
    except ValueError:
        lockout_active = lockout not in {"", "0"}
    if lockout_active or "775" in seen_codes:
        return _AD_DATA_MESSAGES["775"]
    for code in ("533", "532", "773", "701", "530", "531", "525", "52e"):
        if code in seen_codes:
            return _AD_DATA_MESSAGES[code]
    return fallback


def _sync_local_ldap_user(username: str, sam: str, mail: str) -> tuple[User | None, str, bool]:
    local_username = (sam or _normalize_username(username)).strip()
    user = (
        User.objects.filter(username__iexact=local_username).first()
        or User.objects.filter(username__iexact=_normalize_username(username)).first()
    )
    if user is None:
        user = User(username=local_username.lower())
        user.set_unusable_password()
        if mail:
            user.email = mail[:254]
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.save()
        return user, "", True

    if not user.is_active:
        return None, "Учётная запись отключена в WebTerm", False

    changed = False
    if mail and not user.email:
        user.email = mail[:254]
        changed = True
    if user.has_usable_password():
        user.set_unusable_password()
        changed = True
    if changed:
        user.save()
    return user, "", False


def authenticate_ldap_user(username: str, password: str) -> tuple[User | None, str]:
    """
    Authenticate against AD and return (user, error_message).
    On success error_message is empty.
    """
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        return None, "Укажите логин и пароль"

    try:
        service = _ldap_connect()
        service.simple_bind_s(
            str(getattr(settings, "LDAP_BIND_DN", "") or ""),
            str(getattr(settings, "LDAP_BIND_PASSWORD", "") or ""),
        )
    except Exception as exc:
        logger.error("LDAP service bind failed: {}", exc)
        return None, "Нет связи с Active Directory (service bind failed)"

    try:
        found = _search_user(service, username)
        if not found:
            return None, "Неверный логин или пароль домена"
        dn, attrs = found
        sam = _attr(attrs, str(getattr(settings, "LDAP_USERNAME_ATTRIBUTE", "sAMAccountName") or "sAMAccountName"))
        upn = _attr(attrs, "userPrincipalName")
        mail = _attr(attrs, str(getattr(settings, "LDAP_EMAIL_ATTRIBUTE", "mail") or "mail"))
        uac_raw = _attr(attrs, "userAccountControl", "0")
        lockout = _attr(attrs, "lockoutTime", "0")
        try:
            uac = int(uac_raw or "0")
        except ValueError:
            uac = 0
        if uac & 0x2:
            return None, "Учётная запись AD отключена"
        if lockout not in {"", "0"}:
            # Non-zero lockoutTime usually means currently/previously locked.
            # Confirm with a probe bind for clearer messaging below if needed.
            logger.debug("LDAP reports non-zero lockoutTime for {}", username)

        bind_identities = []
        for item in (upn, dn, sam):
            value = (item or "").strip()
            if value and value not in bind_identities:
                bind_identities.append(value)

        authenticated, seen_codes, last_error = _bind_ldap_identities(username, password, bind_identities)
        if not authenticated:
            return None, _preferred_bind_error(seen_codes, lockout, last_error)

        user, local_error, created = _sync_local_ldap_user(username, sam, mail)
        if user is None:
            return None, local_error

        # Every LDAP user (except local admin) joins the pilot group.
        try:
            _ensure_pilot_group(user)
        except Exception as exc:
            logger.warning("Failed to ensure pilot group for {}: {}", user.username, exc)

        # Attach backend path for auth_login compatibility.
        user.backend = "django_auth_ldap.backend.LDAPBackend"
        if created:
            logger.info("Created LDAP user '{}' and assigned pilot group", user.username)
        return user, ""
    finally:
        try:
            service.unbind_s()
        except Exception as exc:
            logger.debug("LDAP service connection cleanup failed: {}", exc)
