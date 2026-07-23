from __future__ import annotations

import re

from architecture_guard_config import ArchitectureConfig, FileMetric, PathNormalizer


class BaselineWriter:
    """Writes current over-limit file sizes into ``legacy_baselines``."""

    def __init__(self, config_path: str, config: ArchitectureConfig) -> None:
        self._config_path = config_path
        self._config = config

    def write(self, metrics: list[FileMetric]) -> int:
        over_limit = [m for m in metrics if not m.is_legacy and m.lines > self._config.standard_limit]
        grown_legacy = [m for m in metrics if m.is_legacy and not m.passed]
        candidates = over_limit + grown_legacy

        if not candidates:
            print("No files exceed the standard limit — baseline unchanged.")
            return 0

        try:
            with open(self._config_path, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            print(f"ERROR: Cannot read {self._config_path}: {exc}")
            return 0

        updated = 0
        for metric in candidates:
            raw = self._upsert_entry(raw, metric)
            updated += 1

        try:
            with open(self._config_path, "w", encoding="utf-8") as fh:
                fh.write(raw)
        except OSError as exc:
            print(f"ERROR: Cannot write {self._config_path}: {exc}")
            return 0

        print(f"Pinned {updated} file(s) into {self._config_path} legacy_baselines.")
        for metric in candidates:
            key = PathNormalizer.normalize(metric.path).lstrip("./")
            print(f"  {key} = {metric.lines}")
        return updated

    @staticmethod
    def _upsert_entry(raw: str, metric: FileMetric) -> str:
        key = PathNormalizer.normalize(metric.path).lstrip("./")
        quoted_key = f'"{key}"'
        pattern = re.compile(
            rf"^({re.escape(quoted_key)}\s*=\s*)\d+",
            re.MULTILINE,
        )
        if pattern.search(raw):
            return pattern.sub(rf"\g<1>{metric.lines}", raw)

        section_pattern = re.compile(
            r"(\[tool\.architecture\.legacy_baselines\][^\[]*)",
            re.DOTALL,
        )
        section_match = section_pattern.search(raw)
        new_entry = f"{quoted_key} = {metric.lines}\n"
        if not section_match:
            return raw + f"\n[tool.architecture.legacy_baselines]\n{new_entry}"
        insert_pos = section_match.end()
        return raw[:insert_pos] + new_entry + raw[insert_pos:]
