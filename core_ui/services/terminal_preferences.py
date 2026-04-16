"""
Service layer for terminal appearance preferences.
"""

from __future__ import annotations

from core_ui.models import TerminalPreference

_ALLOWED_THEME_NAMES = frozenset(
    {
        "one_dark",
        "dracula",
        "tokyo_night",
        "nord",
        "gruvbox",
        "solarized_dark",
        "monokai",
        "github_dark",
        "custom",
    }
)

_ALLOWED_CURSOR_STYLES = frozenset({"block", "bar", "underline"})

_ALLOWED_FONT_FAMILIES = frozenset(
    {
        "JetBrains Mono",
        "Fira Code",
        "Cascadia Code",
        "Consolas",
        "Source Code Pro",
        "Ubuntu Mono",
        "monospace",
    }
)

_SERIALISABLE_FIELDS = (
    "theme_name",
    "theme_colors",
    "font_size",
    "font_family",
    "line_height",
    "cursor_style",
    "cursor_blink",
    "scrollback",
    "intercept_editors",
)


def _serialise(pref: TerminalPreference) -> dict:
    return {field: getattr(pref, field) for field in _SERIALISABLE_FIELDS}


def get_or_create_prefs(user) -> dict:
    """Return terminal preferences for *user*, creating defaults if absent."""
    pref, _ = TerminalPreference.objects.get_or_create(user=user)
    return _serialise(pref)


def update_prefs(user, data: dict) -> dict:
    """Validate and persist partial update of terminal preferences."""
    pref, _ = TerminalPreference.objects.get_or_create(user=user)

    if "theme_name" in data:
        value = str(data["theme_name"]).strip()
        if value in _ALLOWED_THEME_NAMES:
            pref.theme_name = value

    if "theme_colors" in data and isinstance(data["theme_colors"], dict):
        pref.theme_colors = data["theme_colors"]

    if "font_size" in data:
        try:
            size = int(data["font_size"])
            pref.font_size = max(10, min(24, size))
        except (TypeError, ValueError):
            pass

    if "font_family" in data:
        value = str(data["font_family"]).strip()
        if value in _ALLOWED_FONT_FAMILIES:
            pref.font_family = value

    if "line_height" in data:
        try:
            lh = float(data["line_height"])
            pref.line_height = max(1.0, min(2.0, round(lh, 2)))
        except (TypeError, ValueError):
            pass

    if "cursor_style" in data:
        value = str(data["cursor_style"]).strip()
        if value in _ALLOWED_CURSOR_STYLES:
            pref.cursor_style = value

    if "cursor_blink" in data:
        pref.cursor_blink = bool(data["cursor_blink"])

    if "scrollback" in data:
        try:
            sb = int(data["scrollback"])
            pref.scrollback = max(500, min(50_000, sb))
        except (TypeError, ValueError):
            pass

    if "intercept_editors" in data:
        pref.intercept_editors = bool(data["intercept_editors"])

    pref.save()
    return _serialise(pref)
