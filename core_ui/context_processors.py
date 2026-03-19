"""
Context processors for core_ui: inject user_can_* flags for menu and guards.
Also provides user_can_feature(user, feature) for use in views/decorators.
"""
from core_ui.access import (
    access_feature_slugs,
    build_user_access_payload,
    feature_allowed_for_user,
    load_group_permission_sources,
    load_user_explicit_permissions,
)

FEATURE_SLUGS = access_feature_slugs()


def user_can_feature(user, feature):
    """Return True if user is allowed to access `feature`. Anonymous => False. Use in views/decorators."""
    return _user_can_feature(user, feature)


def _user_can_feature(user, feature, permissions_map=None, group_permissions_map=None):
    """Return True if user is allowed to access `feature`. Anonymous => False."""
    if not user or not user.is_authenticated:
        return False
    perms = permissions_map if permissions_map is not None else load_user_explicit_permissions(user)
    group_perms = (
        group_permissions_map
        if group_permissions_map is not None
        else build_user_access_payload(
            user,
            explicit_permissions=perms,
            group_permission_sources=load_group_permission_sources(user),
        )["group_permissions"]
    )
    return feature_allowed_for_user(user, feature, perms, group_perms)


def _is_server_only_user(user, permissions_map=None, group_permissions_map=None):
    """True when user can access only servers section (and nothing else)."""
    if not user or not user.is_authenticated or user.is_staff:
        return False
    perms = permissions_map if permissions_map is not None else load_user_explicit_permissions(user)
    group_perms = (
        group_permissions_map
        if group_permissions_map is not None
        else build_user_access_payload(
            user,
            explicit_permissions=perms,
            group_permission_sources=load_group_permission_sources(user),
        )["group_permissions"]
    )
    if not _user_can_feature(user, 'servers', perms, group_perms):
        return False
    for feature in FEATURE_SLUGS:
        if feature == 'servers':
            continue
        if _user_can_feature(user, feature, perms, group_perms):
            return False
    return True


def is_server_only_user(user):
    """Public helper for views/decorators."""
    return _is_server_only_user(user)


def default_home_url_name(user):
    """Default landing route name for current user."""
    return 'servers:server_list'


def app_permissions(request):
    """Add user_can_* flags and shell mode flags to template context."""
    user = getattr(request, 'user', None)
    perms = load_user_explicit_permissions(user)
    group_perms = build_user_access_payload(
        user,
        explicit_permissions=perms,
        group_permission_sources=load_group_permission_sources(user),
    )["group_permissions"] if user and getattr(user, "is_authenticated", False) else {}
    out = {}
    for f in FEATURE_SLUGS:
        out[f'user_can_{f}'] = _user_can_feature(user, f, perms, group_perms)
    out['is_app_admin'] = bool(user and user.is_authenticated and user.is_staff)
    out['is_server_only_mode'] = _is_server_only_user(user, perms, group_perms)
    out['default_home_url_name'] = default_home_url_name(user)
    return out
