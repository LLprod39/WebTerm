from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from plugin_marketplace.services.package_analysis_service import analyze_wtp_archive


def analyze_plugin_source_dependencies(
    files: list[tuple[Path, str]],
    *,
    allow_sandboxed_code: bool,
) -> dict:
    handle = tempfile.NamedTemporaryFile(suffix=".wtp", delete=False)
    package_path = Path(handle.name)
    handle.close()
    try:
        with zipfile.ZipFile(package_path, "w") as archive:
            for file_path, relative in files:
                archive.writestr(relative, file_path.read_bytes())
        return analyze_wtp_archive(package_path, allow_sandboxed_code=allow_sandboxed_code)
    finally:
        package_path.unlink(missing_ok=True)
