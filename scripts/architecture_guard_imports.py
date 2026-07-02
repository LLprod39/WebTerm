from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

from architecture_guard_config import ArchitectureConfig


class ImportBoundaryChecker:
    """Delegates import-boundary enforcement to the ``lint-imports`` CLI."""

    _TOOL: Final[str] = "lint-imports"

    def __init__(self, config: ArchitectureConfig) -> None:
        self._config = config

    def check(self) -> bool:
        if not self._config.enforce_import_boundaries:
            return True

        print("\n=== Checking Import Boundaries (import-linter) ===")
        tool = self._resolve_tool()

        try:
            result = subprocess.run(
                [tool, "--no-cache"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                return False

            print("SUCCESS: Import boundaries respected.")
            return True

        except FileNotFoundError:
            print(
                f"ERROR: '{tool}' not found — import boundary enforcement is enabled\n"
                "but the tool is not installed.  Run:  pip install import-linter\n"
                "Refusing to pass: import boundaries are NOT verified."
            )
            return False

        except Exception as exc:  # noqa: BLE001
            print(f"Error running {self._TOOL}: {exc}")
            return False

    def _resolve_tool(self) -> str:
        tool = self._TOOL
        resolved = shutil.which(tool)
        if resolved:
            return resolved
        script_dirs = [Path(sys.executable).parent, Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")]
        for directory in script_dirs:
            for candidate in (directory / tool, directory / f"{tool}.exe"):
                if candidate.exists():
                    return str(candidate)
        if os.name != "nt":
            return tool
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return tool
        candidates = glob.glob(os.path.join(appdata, "Python", "Python*", "Scripts", "lint-imports.exe"))
        if not candidates:
            return tool
        candidates.sort(reverse=True)
        return candidates[0]
