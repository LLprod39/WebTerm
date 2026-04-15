"""
Base Tool Interface for WEU Agent System
"""
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Parameter definition for a tool"""
    name: str
    type: str  # "string", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any | None = None


class ToolMetadata(BaseModel):
    """Metadata describing a tool"""
    name: str
    description: str
    parameters: list[ToolParameter] = Field(default_factory=list)
    category: str = "general"  # general, filesystem, network, ssh, web, code


class BaseTool(ABC):
    """Base class for all tools"""

    def __init__(self):
        self._metadata = self.get_metadata()

    @abstractmethod
    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata"""
        raise NotImplementedError("BaseTool.get_metadata must be implemented by subclasses.")

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters"""
        raise NotImplementedError("BaseTool.execute must be implemented by subclasses.")

    def to_dict(self) -> dict:
        """Convert tool to dictionary representation"""
        return {
            "name": self._metadata.name,
            "description": self._metadata.description,
            "category": self._metadata.category,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default
                }
                for p in self._metadata.parameters
            ]
        }
