from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .node_manifest_schema import (
    array_schema as _array,
)
from .node_manifest_schema import (
    bool_schema as _bool,
)
from .node_manifest_schema import (
    empty_object_schema as _empty_object_schema,
)
from .node_manifest_schema import (
    int_schema as _int,
)
from .node_manifest_schema import (
    object_schema as _obj,
)
from .node_manifest_schema import (
    schema as _schema,
)
from .node_manifest_schema import (
    str_schema as _str,
)

__all__ = [
    "COMMON_SUCCESS_OUTPUT",
    "ON_FAILURE_SCHEMA",
    "PERMISSION_MODE_SCHEMA",
    "SERVER_ID_FIELDS",
    "NodeManifest",
    "_array",
    "_bool",
    "_int",
    "_manifest",
    "_obj",
    "_schema",
    "_str",
]

ON_FAILURE_SCHEMA = _str(
    enum=("abort", "continue"),
    default="abort",
    description="Execution behavior when this node returns an error.",
)
PERMISSION_MODE_SCHEMA = _str(
    enum=("SAFE", "ASK", "AUTO"),
    default="SAFE",
    description="Policy mode for tool or command execution.",
)
SERVER_ID_FIELDS = {
    "server_id": _int(description="Explicit WebTerm server id owned by the pipeline owner."),
    "server_id_context_key": _str(default="server_id", description="Context key to resolve server_id from."),
}
COMMON_SUCCESS_OUTPUT = _schema({"output": _str(description="Human-readable node result.")})
NODE_RETRY_INPUTS = {
    "retry_max_attempts": _int(minimum=1, maximum=10, default=1),
    "retry_initial_delay_seconds": _int(minimum=0, maximum=300, default=1),
    "retry_backoff_multiplier": _int(minimum=1, maximum=10, default=2),
    "retry_max_delay_seconds": _int(minimum=1, maximum=3600, default=60),
    "retry_non_idempotent": _bool(
        default=False,
        description="Explicitly permit retry of a node that can repeat external side effects.",
    ),
}


@dataclass(frozen=True, slots=True)
class NodeManifest:
    node_type: str
    category: str
    purpose: str
    source_handles: tuple[str, ...]
    risk_level: str = "read_only"
    idempotency: str = "idempotent"
    mutates_state: bool = False
    supports_dry_run: bool = False
    requires_approval_by_default: bool = False
    recommended_verification: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    input_schema: dict[str, Any] = field(default_factory=_empty_object_schema)
    output_schema: dict[str, Any] = field(default_factory=_empty_object_schema)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_assistant_catalog_item(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "purpose": self.purpose,
            "source_handles": list(self.source_handles),
            "risk_level": self.risk_level,
            "idempotency": self.idempotency,
            "mutates_state": self.mutates_state,
            "supports_dry_run": self.supports_dry_run,
            "requires_approval_by_default": self.requires_approval_by_default,
            "recommended_verification": list(self.recommended_verification),
            "tags": list(self.tags),
            "input_schema": deepcopy(self.input_schema),
            "output_schema": deepcopy(self.output_schema),
        }

    def to_api_payload(self) -> dict[str, Any]:
        item = self.to_assistant_catalog_item()
        item["type"] = self.node_type
        item["metadata"] = deepcopy(self.metadata)
        return item


def _manifest(
    node_type: str,
    category: str,
    purpose: str,
    source_handles: tuple[str, ...],
    **kwargs: Any,
) -> NodeManifest:
    if "idempotency" not in kwargs and bool(kwargs.get("mutates_state")):
        kwargs["idempotency"] = "non_idempotent"
    if category != "Triggers" and isinstance(kwargs.get("input_schema"), dict):
        input_schema = deepcopy(kwargs["input_schema"])
        properties = input_schema.setdefault("properties", {})
        if isinstance(properties, dict):
            for key, value in NODE_RETRY_INPUTS.items():
                properties.setdefault(key, deepcopy(value))
        kwargs["input_schema"] = input_schema
    return NodeManifest(
        node_type=node_type,
        category=category,
        purpose=purpose,
        source_handles=source_handles,
        **kwargs,
    )
