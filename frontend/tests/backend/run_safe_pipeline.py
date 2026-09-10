"""Execute exactly one local-condition QA run through the real durable dispatcher."""

from __future__ import annotations

import asyncio
import json
import os
import sys

if os.environ.get("DJANGO_SETTINGS_MODULE") != "qa_settings":
    raise SystemExit("Only qa_settings is allowed")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection, transaction  # noqa: E402

from studio.dispatch import claim_next_pipeline_dispatch, execute_pipeline_dispatch  # noqa: E402
from studio.dispatch_models import PipelineDispatchControl, PipelineRunDispatch  # noqa: E402
from studio.models import PipelineRun  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_graph(nodes: list, edges: list) -> None:
    require(len(nodes) == 2 and len(edges) == 1, "Only the two-node condition fixture is allowed")
    by_id = {node.get("id"): node for node in nodes}
    require(set(by_id) == {"qa_manual", "qa_condition"}, "Unexpected node IDs")
    manual, condition = by_id["qa_manual"], by_id["qa_condition"]
    require(manual.get("type") == "trigger/manual", "Unexpected trigger type")
    require(set(manual.get("data", {})) <= {"label", "is_active"}, "Unexpected trigger configuration")
    require(manual["data"].get("is_active") is True, "QA trigger must be active")
    require(condition.get("type") == "logic/condition", "Only local conditions are allowed")
    require(set(condition.get("data", {})) <= {"label", "check_type"}, "Unexpected condition configuration")
    require(condition["data"].get("check_type") == "always_true", "Only constant conditions are allowed")
    edge = edges[0]
    require(edge.get("source") == "qa_manual" and edge.get("target") == "qa_condition", "Unexpected edge")
    require(edge.get("sourceHandle") == "out", "Unexpected source handle")


def claim_fixture(run_id: int):
    expected_database = "webterm_frontend_qa_20260902"
    require(settings.DATABASES["default"]["NAME"] == expected_database, "Refusing a non-QA database")
    require(connection.vendor == "postgresql", "QA worker requires the isolated PostgreSQL database")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        require(cursor.fetchone()[0] == expected_database, "Connected database does not match QA")
    worker = f"frontend-qa-condition-{run_id}"
    with transaction.atomic():
        control, _ = PipelineDispatchControl.objects.get_or_create(name="global")
        PipelineDispatchControl.objects.select_for_update().get(pk=control.pk)
        run = PipelineRun.objects.select_related("pipeline", "pipeline__owner").get(pk=run_id)
        require(run.pipeline.name.startswith("qa_auto_pure_run_"), "Run was not created by this fixture")
        require(run.pipeline.owner.username == "frontend-qa-admin", "Unexpected QA owner")
        require(run.triggered_by_id == run.pipeline.owner_id, "Unexpected actor")
        require(run.status == PipelineRun.STATUS_PENDING and not run.node_states, "Run must be fresh")
        require(run.context == {} and run.entry_node_id == "qa_manual", "Unexpected runtime context")
        verify_graph(run.nodes_snapshot, run.edges_snapshot)
        verify_graph(run.pipeline.nodes, run.pipeline.edges)
        # The production claim function considers the global queue. Refuse to call it if
        # any other live dispatch exists, so no unrelated run can be claimed or exhausted.
        others = PipelineRunDispatch.objects.exclude(run_id=run_id).filter(
            status__in=[PipelineRunDispatch.STATUS_QUEUED, PipelineRunDispatch.STATUS_CLAIMED],
            run__status__in=[PipelineRun.STATUS_PENDING, PipelineRun.STATUS_RUNNING, PipelineRun.STATUS_HIBERNATING],
        )
        require(not others.exists(), "Another QA dispatch is active; refusing to consume the shared queue")
        dispatch = claim_next_pipeline_dispatch(worker_name=worker, lease_seconds=60)
        require(dispatch is not None and dispatch.run_id == run_id, "Scoped QA claim did not match")
    return dispatch.pk, worker


if __name__ == "__main__":
    run_id = int(sys.argv[1])
    dispatch_id, worker_name = claim_fixture(run_id)
    result = asyncio.run(execute_pipeline_dispatch(dispatch_id, worker_name=worker_name, lease_seconds=60))
    require(result.status == PipelineRun.STATUS_COMPLETED, f"QA pipeline ended with {result.status}")
    print(json.dumps({"run_id": run_id, "dispatch_id": dispatch_id, "status": result.status}))
