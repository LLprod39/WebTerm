from __future__ import annotations

import ast
from pathlib import Path


def test_production_llm_calls_declare_execution_context() -> None:
    root = Path(__file__).resolve().parents[1]
    missing: list[str] = []
    for top_level in ("app", "core_ui", "servers", "studio"):
        for path in (root / top_level).rglob("*.py"):
            if path.name.startswith("test_") or "tests" in path.parts or "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in {"stream_chat", "stream_chat_tools"}:
                    continue
                keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
                if "execution_context" not in keywords:
                    missing.append(f"{path.relative_to(root)}:{node.lineno}")
    assert missing == [], "LLM calls without execution_context:\n" + "\n".join(missing)
