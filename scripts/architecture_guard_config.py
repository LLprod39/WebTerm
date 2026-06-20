from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


class PathNormalizer:
    """Converts raw filesystem paths into canonical ``./forward/slash`` form."""

    @staticmethod
    def normalize(path: str) -> str:
        p = path.replace("\\", "/").lstrip("/")
        return p if p.startswith("./") else "./" + p


@dataclass(frozen=True)
class FileMetric:
    """Immutable snapshot of a single file's size-check outcome."""

    path: str
    lines: int
    is_legacy: bool
    limit: int
    passed: bool
    error_message: str = ""


_DEFAULT_EXCLUDE_DIRS: Final[frozenset[str]] = frozenset(
    {
        "node_modules",
        "venv",
        ".venv",
        "migrations",
        "dist",
        "build",
        ".git",
        ".pytest_cache",
        ".playwright-mcp",
        ".ruff_cache",
        "__pycache__",
        "agent_projects",
        "media",
        "outputs",
        "staticfiles",
    }
)

_DEFAULT_EXCLUDE_FRAGMENTS: Final[frozenset[str]] = frozenset(
    {"production-upload-bundle", "frontend/playwright-report", "frontend/test-results"}
)

_DEFAULT_EXTENSIONS: Final[frozenset[str]] = frozenset({".py", ".ts", ".tsx"})


@dataclass(frozen=True)
class ArchitectureConfig:
    """Immutable configuration loaded from ``pyproject.toml``."""

    standard_limit: int = 500
    strict_limit: int = 1000
    enforce_import_boundaries: bool = False
    strict_new_files: bool = False
    contract_file: str = "docs/local/ARCHITECTURE_CONTRACT.md"
    legacy_baselines: dict[str, int] = field(default_factory=dict)
    exclude_dirs: frozenset[str] = field(default_factory=lambda: _DEFAULT_EXCLUDE_DIRS)
    exclude_path_fragments: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_EXCLUDE_FRAGMENTS
    )
    extensions: frozenset[str] = field(default_factory=lambda: _DEFAULT_EXTENSIONS)

    @classmethod
    def from_toml(cls, config_path: str = "pyproject.toml") -> ArchitectureConfig:
        if not os.path.exists(config_path):
            return cls()

        try:
            with open(config_path, "rb") as fh:
                data = tomllib.load(fh)

            arch: dict = data.get("tool", {}).get("architecture", {})
            return cls(
                standard_limit=arch.get("standard_limit", 500),
                strict_limit=arch.get("strict_limit", 1000),
                enforce_import_boundaries=arch.get("enforce_import_boundaries", False),
                strict_new_files=arch.get("strict_new_files", False),
                contract_file=arch.get("contract_file", "docs/local/ARCHITECTURE_CONTRACT.md"),
                legacy_baselines={
                    PathNormalizer.normalize(k): v
                    for k, v in arch.get("legacy_baselines", {}).items()
                },
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: could not load architecture config from {config_path}: {exc}")
            return cls()
