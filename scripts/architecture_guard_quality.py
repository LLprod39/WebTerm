from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from architecture_guard_config import ArchitectureConfig
except ModuleNotFoundError:  # pragma: no cover - package import in tests
    from scripts.architecture_guard_config import ArchitectureConfig


@dataclass(frozen=True)
class QualitySnapshot:
    functions_scanned: int
    modules_scanned: int
    complexity: dict[str, int]
    fan_out: dict[str, int]
    fan_in: dict[str, int]


@dataclass(frozen=True)
class QualityCheckResult:
    snapshot: QualitySnapshot
    errors: tuple[str, ...]
    frozen_violations: int

    @property
    def passed(self) -> bool:
        return not self.errors


class ArchitectureQualityChecker:
    """Measure Python complexity and internal module coupling.

    Existing debt is frozen in a numeric baseline. A new violation or growth
    above the recorded value fails, while line count remains diagnostic only.
    """

    def __init__(self, config: ArchitectureConfig) -> None:
        self._config = config

    def check(self, root_dir: str = ".") -> QualityCheckResult:
        root = Path(root_dir).resolve()
        snapshot = self.scan(root)
        baseline = self._load_baseline(root)
        errors = self._compare(snapshot, baseline)
        frozen = sum(
            len(section)
            for section in (
                baseline.get("complexity", {}),
                baseline.get("fanOut", {}),
                baseline.get("fanIn", {}),
            )
        )
        return QualityCheckResult(snapshot, tuple(errors), frozen)

    def update_baseline(self, root_dir: str = ".") -> Path:
        root = Path(root_dir).resolve()
        snapshot = self.scan(root)
        path = self._baseline_path(root)
        payload = {
            "thresholds": {
                "complexity": self._config.complexity_limit,
                "fanOut": self._config.fan_out_limit,
                "fanIn": self._config.fan_in_limit,
            },
            "complexity": snapshot.complexity,
            "fanOut": snapshot.fan_out,
            "fanIn": snapshot.fan_in,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def scan(self, root: Path) -> QualitySnapshot:
        files = self._python_files(root)
        modules = {self._module_name(path, root): path for path in files}
        modules = {name: path for name, path in modules.items() if name}
        fan_out_targets: dict[str, set[str]] = {name: set() for name in modules}
        complexities: dict[str, int] = {}
        functions_scanned = 0

        for module_name, path in modules.items():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
            except (OSError, SyntaxError):
                continue

            fan_out_targets[module_name] = self._internal_imports(
                tree,
                module_name=module_name,
                is_package=path.name == "__init__.py",
                known_modules=set(modules),
            )
            for node, qualified_name in _function_nodes(tree):
                functions_scanned += 1
                value = _cyclomatic_complexity(node)
                if value > self._config.complexity_limit:
                    rel = path.relative_to(root).as_posix()
                    key = f"{rel}::{qualified_name}"
                    complexities[key] = value

        fan_in_counts = dict.fromkeys(modules, 0)
        for targets in fan_out_targets.values():
            for target in targets:
                fan_in_counts[target] = fan_in_counts.get(target, 0) + 1

        fan_out = {
            modules[name].relative_to(root).as_posix(): len(targets)
            for name, targets in fan_out_targets.items()
            if len(targets) > self._config.fan_out_limit
        }
        fan_in = {
            modules[name].relative_to(root).as_posix(): value
            for name, value in fan_in_counts.items()
            if value > self._config.fan_in_limit
        }
        return QualitySnapshot(
            functions_scanned=functions_scanned,
            modules_scanned=len(modules),
            complexity=dict(sorted(complexities.items())),
            fan_out=dict(sorted(fan_out.items())),
            fan_in=dict(sorted(fan_in.items())),
        )

    def _compare(self, current: QualitySnapshot, baseline: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        sections = (
            ("complexity", current.complexity, "complexity"),
            ("fanOut", current.fan_out, "fan-out"),
            ("fanIn", current.fan_in, "fan-in"),
        )
        for baseline_key, values, label in sections:
            allowed = baseline.get(baseline_key, {})
            if not isinstance(allowed, dict):
                allowed = {}
            for key, value in values.items():
                previous = allowed.get(key)
                if previous is None:
                    errors.append(f"new {label} violation: {key} ({value})")
                elif value > int(previous):
                    errors.append(f"frozen {label} violation grew: {key} {previous} -> {value}")
        return errors

    def _load_baseline(self, root: Path) -> dict[str, Any]:
        path = self._baseline_path(root)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"could not load architecture metrics baseline {path}: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def _baseline_path(self, root: Path) -> Path:
        configured = Path(self._config.metrics_baseline_file)
        return configured if configured.is_absolute() else root / configured

    def _python_files(self, root: Path) -> list[Path]:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            result = None
        if result is not None and result.returncode == 0:
            candidates = [root / line.strip() for line in result.stdout.splitlines() if line.strip()]
        else:
            candidates = list(root.rglob("*.py"))
        return sorted(
            path
            for path in candidates
            if path.exists()
            and not any(part in self._config.exclude_dirs for part in path.relative_to(root).parts)
            and not any(
                fragment in path.relative_to(root).as_posix()
                for fragment in self._config.exclude_path_fragments
            )
        )

    @staticmethod
    def _module_name(path: Path, root: Path) -> str:
        parts = list(path.relative_to(root).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    @staticmethod
    def _internal_imports(
        tree: ast.AST,
        *,
        module_name: str,
        is_package: bool,
        known_modules: set[str],
    ) -> set[str]:
        targets: set[str] = set()
        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = _absolute_import_base(node, module_name, is_package=is_package)
                if base:
                    candidates.append(base)
                    candidates.extend(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
            for candidate in candidates:
                resolved = _resolve_known_module(candidate, known_modules)
                if resolved and resolved != module_name:
                    targets.add(resolved)
        return targets


def _absolute_import_base(node: ast.ImportFrom, module_name: str, *, is_package: bool) -> str:
    if node.level == 0:
        return node.module or ""
    package = module_name.split(".") if is_package else module_name.split(".")[:-1]
    keep = max(0, len(package) - (node.level - 1))
    parts = package[:keep]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _resolve_known_module(candidate: str, known_modules: set[str]) -> str | None:
    parts = candidate.split(".")
    for size in range(len(parts), 0, -1):
        module = ".".join(parts[:size])
        if module in known_modules:
            return module
    return None


def _cyclomatic_complexity(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    value = 1
    for node in ast.walk(function):
        if isinstance(
            node,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.IfExp,
                ast.ExceptHandler,
                ast.comprehension,
            ),
        ):
            value += 1
        elif isinstance(node, ast.BoolOp):
            value += max(0, len(node.values) - 1)
        elif isinstance(node, ast.Match):
            value += len(node.cases)
    return value


def _function_nodes(
    tree: ast.AST,
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]]:
    collected: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]] = []

    class Collector(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function(node)

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qualified_name = ".".join([*self.scope, node.name])
            collected.append((node, qualified_name))
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

    Collector().visit(tree)
    return collected
