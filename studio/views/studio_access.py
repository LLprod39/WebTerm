"""Studio-specific access decorator boundary."""

from core_ui.decorators import require_feature


def require_studio_access(feature: str):
    return require_feature(feature)
