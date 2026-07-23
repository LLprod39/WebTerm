"""Shared base for agent-tool implementations (F-08a split of agent_tools)."""

from __future__ import annotations


class ToolResult:
    __slots__ = ("success", "result", "data")

    def __init__(self, success: bool, result: str, data: dict | None = None):
        self.success = success
        self.result = result
        self.data = data or {}

    def to_dict(self) -> dict:
        d = {"success": self.success, "result": self.result}
        if self.data:
            d["data"] = self.data
        return d
