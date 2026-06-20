from __future__ import annotations

import pytest

from studio.executor.context import ExecutionContext
from studio.executor.engine import PipelineEngine


@pytest.mark.asyncio
async def test_pipeline_engine_fails_unknown_node_type_instead_of_skipping():
    engine = PipelineEngine(
        {
            "nodes": [
                {"id": "unknown", "type": "agent/does_not_exist", "data": {}},
            ],
            "edges": [],
        },
        run_id=77,
        user=object(),
    )

    result = await engine.run(ExecutionContext(run_id=77, user=object(), pipeline=None))

    assert result == {
        "ok": False,
        "error": "Node type is not registered: agent/does_not_exist",
        "node_results": {
            "unknown": {
                "ok": False,
                "output": {},
                "error": "Node type is not registered: agent/does_not_exist",
            }
        },
    }
