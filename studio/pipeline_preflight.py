from __future__ import annotations

from typing import Any

from studio.pipeline_branch_scope import entry_branch_node_ids
from studio.readiness_issues import integration_issue
from studio.readiness_requirements import integration_requirements


def pipeline_integration_diagnostics(pipeline, *, entry_node_id: str | None = None) -> dict[str, Any]:
    requirements = integration_requirements(pipeline, node_ids=entry_branch_node_ids(pipeline, entry_node_id))
    issues = []
    for item in requirements:
        issue = integration_issue(item)
        if issue:
            item["issue"] = issue
            issues.append(issue)
    return {
        "requirements": requirements,
        "issues": issues,
        "errors": [issue["message"] for issue in issues if issue["severity"] == "error"],
        "warnings": [issue["message"] for issue in issues if issue["severity"] == "warning"],
    }
