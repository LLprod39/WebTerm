"""Guard against `select_for_update()` over the nullable side of an outer join.

PostgreSQL rejects such queries at execution time with

    NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an
    outer join

while SQLite silently ignores row locking altogether (``has_select_for_update``
is False), so the whole class of defect passes a local SQLite run and only
surfaces in production. This test resolves the pattern statically, which means
it fails on every backend, including the SQLite developer loop.

The rule: when a queryset chains ``select_for_update()`` with
``select_related()``, every related path must traverse non-nullable foreign
keys, or the lock must be narrowed with ``of=(...)``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.apps import apps

ROOT = Path(__file__).resolve().parents[1]
SCANNED_PACKAGES = (
    "app",
    "core_ui",
    "kubernetes_ops",
    "mars",
    "plugin_marketplace",
    "servers",
    "studio",
    "web_ui",
)


def _models_by_name() -> dict[str, object]:
    resolved: dict[str, object] = {}
    for model in apps.get_models():
        resolved.setdefault(model.__name__, model)
    return resolved


def _chain_calls(node: ast.AST) -> list[ast.Call]:
    """Collect every Call in a single attribute chain, outermost first."""
    calls: list[ast.Call] = []
    current = node
    while True:
        if isinstance(current, ast.Call):
            calls.append(current)
            current = current.func
        elif isinstance(current, (ast.Attribute, ast.Subscript)):
            current = current.value
        else:
            return calls


def _call_name(call: ast.Call) -> str:
    return call.func.attr if isinstance(call.func, ast.Attribute) else ""


def _chain_root_model(node: ast.AST) -> str:
    """Return the leftmost `Name` of the chain, e.g. `PipelineRunDispatch`."""
    current = node
    while True:
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, (ast.Attribute, ast.Subscript)):
            current = current.value
        elif isinstance(current, ast.Name):
            return current.id
        else:
            return ""


def _string_args(call: ast.Call) -> list[str]:
    return [arg.value for arg in call.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]


def _has_of_keyword(call: ast.Call) -> bool:
    return any(keyword.arg == "of" for keyword in call.keywords)


def _nullable_hop(model, path: str) -> str:
    """Return "Model.field" for the first nullable FK on the path, else ""."""
    current = model
    for part in path.split("__"):
        try:
            field = current._meta.get_field(part)
        except Exception:
            return ""  # unresolvable path: not this test's concern
        if getattr(field, "null", False):
            return f"{current.__name__}.{part}"
        related = getattr(field, "related_model", None)
        if related is None:
            return ""
        current = related
    return ""


def _source_files() -> list[Path]:
    files: list[Path] = []
    for package in SCANNED_PACKAGES:
        for path in (ROOT / package).rglob("*.py"):
            if "migrations" in path.parts:
                continue
            files.append(path)
    return files


def _violations() -> list[str]:
    models = _models_by_name()
    problems: list[str] = []
    for path in _source_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            calls = _chain_calls(node)
            names = {_call_name(call) for call in calls}
            if "select_for_update" not in names or "select_related" not in names:
                continue
            lock_call = next(call for call in calls if _call_name(call) == "select_for_update")
            if _has_of_keyword(lock_call):
                continue
            model_name = _chain_root_model(node)
            model = models.get(model_name)
            if model is None:
                continue
            related_paths: list[str] = []
            for call in calls:
                if _call_name(call) == "select_related":
                    related_paths.extend(_string_args(call))
            for related_path in related_paths:
                nullable_at = _nullable_hop(model, related_path)
                if nullable_at:
                    location = f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"
                    problems.append(
                        f"{location}: {model_name}.select_for_update() joins nullable "
                        f"{nullable_at!r} via select_related({related_path!r}); "
                        f"pass of=(...) to narrow the lock"
                    )
    return sorted(set(problems))


def test_select_for_update_never_locks_a_nullable_outer_join():
    problems = _violations()
    assert not problems, "PostgreSQL will reject these queries:\n" + "\n".join(problems)


@pytest.mark.parametrize(
    ("app_label", "model_name", "related_path"),
    [
        ("studio", "PipelineRunDispatch", "run__triggered_by"),
        ("core_ui", "OperatorTurnDispatch", "action"),
        ("servers", "Server", "group"),
        ("studio", "PipelineRun", "triggered_by"),
    ],
)
def test_known_nullable_hops_are_still_nullable(app_label, model_name, related_path):
    """If these become non-nullable the guard above silently stops covering them."""
    model = apps.get_model(app_label, model_name)
    assert _nullable_hop(model, related_path), (
        f"{app_label}.{model_name}.{related_path} is no longer nullable — "
        "re-check that the claim queries still need of=(...)"
    )
