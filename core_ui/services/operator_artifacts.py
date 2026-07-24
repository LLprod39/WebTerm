"""Chat artifacts for Operator workbench (ansible/scripts/reports).

F-08a.10: storage / inventory compression / render metadata live in cohesive
submodules. This module re-exports the stable public API.
"""

from __future__ import annotations

from core_ui.services.operator_artifacts_inventory import (
    compress_inventory_assistant_content,
    looks_like_inventory_prose_dump,
    short_inventory_line,
)
from core_ui.services.operator_artifacts_render import (
    maybe_attach_chart_metadata,
    maybe_attach_table_metadata,
)
from core_ui.services.operator_artifacts_storage import (
    create_artifact,
    extract_artifacts_from_tool_result,
    get_artifact_for_user,
    list_artifacts,
    serialize_artifact,
    update_artifact_content,
)

__all__ = [
    "compress_inventory_assistant_content",
    "create_artifact",
    "extract_artifacts_from_tool_result",
    "get_artifact_for_user",
    "list_artifacts",
    "looks_like_inventory_prose_dump",
    "maybe_attach_chart_metadata",
    "maybe_attach_table_metadata",
    "serialize_artifact",
    "short_inventory_line",
    "update_artifact_content",
]
