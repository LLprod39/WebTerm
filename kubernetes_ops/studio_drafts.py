from __future__ import annotations

from typing import Any

from django.db.models import Q

from kubernetes_ops.models import K8sAppRef, K8sCluster
from kubernetes_ops.studio_integration import owned_kubernetes_mcp_server
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, PipelineDraftSession
from studio.pilot_capability_packs import enrich_mcp_node_data_with_pilot_spec
from studio.pipeline_validation import validate_pipeline_definition
from studio.views.pipeline_assistant_preview import pipeline_assistant_risk
from studio.views.pipeline_draft_helpers import revision_from_response


def app_for_diagnosis(app_id: str) -> K8sAppRef | None:
    value = str(app_id or "").strip()
    numeric = value.removeprefix("app_")
    query = Q(name=value)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sAppRef.objects.select_related("cluster").filter(query).first()


def create_kubernetes_diagnosis_draft(*, user, app: K8sAppRef) -> PipelineDraftSession:
    title = f"Kubernetes diagnosis: {app.namespace}/{app.name}"
    user_goal = (
        f"Create a read-only Kubernetes diagnosis workflow for {app.cluster.name}/"
        f"{app.namespace}/{app.name} without executing remediation."
    )
    response, preview_nodes, preview_edges = _diagnosis_draft_response(user, app)
    session = PipelineDraftSession.objects.create(
        owner=user,
        status=PipelineDraftSession.STATUS_DRAFTING,
        intent=PipelineDraftSession.INTENT_CREATE,
        title=title,
        user_goal=user_goal,
        current_graph_snapshot={
            "pipeline_id": None,
            "pipeline_name": title,
            "nodes": [],
            "edges": [],
            "selected_node": None,
        },
        selected_node_id="inspect",
    )
    revision_from_response(
        session=session,
        user_message=user_goal,
        response=response,
        preview_nodes=preview_nodes,
        preview_edges=preview_edges,
    )
    return session


def _workload_kind_for_app(app: K8sAppRef) -> str:
    labels = app.labels if isinstance(app.labels, dict) else {}
    raw = (
        str(
            labels.get("workload_kind")
            or labels.get("k8s_kind")
            or labels.get("resource_kind")
            or labels.get("kind")
            or "deployment"
        )
        .strip()
        .lower()
    )
    raw = raw.rsplit("/", 1)[-1]
    aliases = {
        "deploy": "deployment",
        "deployments": "deployment",
        "statefulsets": "statefulset",
        "daemonsets": "daemonset",
        "pods": "pod",
    }
    return aliases.get(raw, raw if raw in {"deployment", "statefulset", "daemonset", "pod"} else "deployment")


def _cluster_context_for_draft(cluster: K8sCluster) -> str:
    labels = cluster.labels if isinstance(cluster.labels, dict) else {}
    return str(
        labels.get("kube_context") or labels.get("context") or labels.get("cluster_context") or cluster.name
    ).strip()


def _diagnosis_node_graph(
    app: K8sAppRef, mcp_server
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    cluster = app.cluster
    workload_kind = _workload_kind_for_app(app)
    target = {
        "cluster": _cluster_context_for_draft(cluster),
        "cluster_name": cluster.name,
        "namespace": app.namespace,
        "kind": workload_kind,
        "name": app.name,
        "team": app.team,
        "environment": app.environment or cluster.environment,
        "health": app.health,
        "version": app.version,
        "owner": app.owner,
    }
    inspect_data = enrich_mcp_node_data_with_pilot_spec(
        {
            "label": "Inspect Kubernetes workload",
            "mcp_server_id": mcp_server.id if mcp_server else "",
            "mcp_server_name": "Kubernetes MCP",
            "tool_name": "kubernetes_describe_workload",
            "arguments": {
                "cluster": target["cluster"],
                "namespace": target["namespace"],
                "kind": target["kind"],
                "name": target["name"],
            },
            "permission_mode": "READ_ONLY",
            "on_failure": "abort",
        }
    )
    prompt = (
        "Review read-only Kubernetes evidence for this workload and prepare an operator diagnosis.\n\n"
        f"Target: cluster={target['cluster_name']} namespace={target['namespace']} kind={target['kind']} "
        f"name={target['name']} team={target['team'] or 'unknown'} health={target['health']} "
        f"version={target['version'] or 'unknown'}.\n\n"
        "Workload evidence:\n{inspect_output}\n\n"
        "Return: current status, likely causes with confidence, blast radius, safe next checks, and escalation notes. "
        "Do not execute or automate rollout/restart/scale/delete. If remediation is needed, describe it as a separate action that requires approval."
    )
    nodes = [
        {
            "id": "manual",
            "type": "trigger/manual",
            "position": {"x": 120, "y": 80},
            "data": {"label": "Start Kubernetes diagnosis", "is_active": True},
        },
        {
            "id": "inspect",
            "type": "agent/mcp_call",
            "position": {"x": 120, "y": 230},
            "data": inspect_data,
        },
        {
            "id": "assess",
            "type": "agent/llm_query",
            "position": {"x": 120, "y": 390},
            "data": {
                "label": "Summarize diagnosis",
                "provider": "openai",
                "model": "gpt-5-mini",
                "system_prompt": (
                    "You are a Kubernetes SRE reviewer. Use evidence first, keep conclusions bounded, "
                    "and keep remediation as approved follow-up work."
                ),
                "prompt": prompt,
                "include_all_outputs": False,
                "on_failure": "abort",
            },
        },
        {
            "id": "report",
            "type": "output/report",
            "position": {"x": 120, "y": 550},
            "data": {
                "label": "Kubernetes diagnosis report",
                "template": (
                    "# Kubernetes diagnosis report\n\n"
                    f"## Target\nCluster: {target['cluster_name']}\nNamespace: {target['namespace']}\n"
                    f"Workload: {target['kind']}/{target['name']}\nTeam: {target['team'] or 'unknown'}\n"
                    f"Health: {target['health']}\n\n"
                    "## Workload evidence\n{inspect_output}\n\n"
                    "## Diagnosis\n{assess_output}"
                ),
            },
        },
    ]
    edges = [
        {"id": "e-manual-inspect", "source": "manual", "target": "inspect", "sourceHandle": "out", "animated": True},
        {
            "id": "e-inspect-assess",
            "source": "inspect",
            "target": "assess",
            "sourceHandle": "success",
            "animated": True,
        },
        {"id": "e-assess-report", "source": "assess", "target": "report", "sourceHandle": "success", "animated": True},
    ]
    return nodes, edges, target


def _diagnosis_draft_response(
    user, app: K8sAppRef
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    mcp_server = owned_kubernetes_mcp_server(user)
    nodes, edges, target = _diagnosis_node_graph(app, mcp_server)
    validation_errors = validate_pipeline_definition(
        nodes=nodes,
        edges=edges,
        owner=user,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )
    questions = []
    resource_plan_missing = []
    mcp_servers = []
    if mcp_server:
        mcp_servers.append(
            {
                "id": mcp_server.id,
                "name": mcp_server.name,
                "kind": "mcp_server",
                "status": "selected",
                "last_test_ok": mcp_server.last_test_ok,
            }
        )
    else:
        resource_plan_missing.append("Owned Kubernetes MCP server")
        questions.append("Bind an owned Kubernetes MCP server before validating or applying this draft.")
    if not getattr(user, "is_staff", False):
        questions.append(
            "MCP execution is admin-only in this Studio installation; ask a staff operator to bind and run the draft."
        )

    response = {
        "reply": (
            "Created a read-only Kubernetes diagnosis draft. It collects workload evidence through "
            "`kubernetes_describe_workload`, summarizes risk, and writes a report. No rollout, restart, scale, "
            "delete, or other mutating action is included."
        ),
        "selected_template": {
            "slug": "kubernetes-readonly-diagnosis",
            "name": "Kubernetes read-only diagnosis",
            "source": "kubernetes_ops",
        },
        "requirements": [
            f"Diagnose Kubernetes workload {target['namespace']}/{target['name']} in cluster {target['cluster_name']}.",
            "Use read-only MCP evidence only.",
            "Produce an operator report without executing remediation.",
        ],
        "assumptions": [
            "The Kubernetes MCP server has a context that can read the target namespace.",
            "Any remediation must be created as a separate approved draft or manual action.",
        ],
        "questions": questions,
        "resource_plan": {
            "mcp_servers": mcp_servers,
            "skills": [{"slug": "kubernetes-safety", "name": "Kubernetes Safety Workflow", "status": "attached"}],
            "missing": resource_plan_missing,
            "notes": ["No Kubernetes write operation is present in the draft graph."],
        },
        "target_node_id": "inspect",
        "node_patch": {},
        "graph_patch": {},
        "node_explanations": {
            "inspect": "Read-only workload inspection via Kubernetes MCP.",
            "assess": "LLM diagnosis over read-only evidence.",
            "report": "Operator report with target, evidence, and diagnosis.",
        },
        "warnings": ["This draft does not execute until reviewed and applied in Studio."],
        "patch_summary": "Create Kubernetes read-only diagnosis draft",
        "suggested_next_actions": [
            "Review the selected Kubernetes MCP binding.",
            "Run Studio validation/dry-run before applying the draft.",
            "Create a separate approval-gated remediation draft only if diagnosis requires action.",
        ],
        "validation": {"ok": not validation_errors, "errors": validation_errors, "warnings": []},
        "risk": pipeline_assistant_risk(nodes, edges),
        "confidence": 0.82 if mcp_server else 0.64,
    }
    return response, nodes, edges
