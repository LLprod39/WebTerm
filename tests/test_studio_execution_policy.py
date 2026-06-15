from studio.execution_policy import build_execution_policy_decisions, summarize_execution_policy_decisions


def _node(node_id: str, node_type: str, data: dict | None = None) -> dict:
    return {"id": node_id, "type": node_type, "position": {"x": 0, "y": 0}, "data": data or {}}


def _edge(source: str, target: str, handle: str = "out") -> dict:
    return {"id": f"{source}-{target}-{handle}", "source": source, "target": target, "sourceHandle": handle}


def test_execution_policy_decision_marks_mutating_mcp_as_allowed_after_approval():
    decisions = build_execution_policy_decisions(
        nodes=[
            _node("manual", "trigger/manual"),
            _node("approval", "logic/human_approval"),
            _node(
                "change",
                "agent/mcp_call",
                {
                    "label": "Apply Keycloak change",
                    "tool_name": "keycloak_apply_access_change",
                    "mutates_state": True,
                    "requires_approval": True,
                    "operation_kind": "identity_access_change",
                },
            ),
        ],
        edges=[_edge("manual", "approval"), _edge("approval", "change", "approved")],
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.node_id == "change"
    assert decision.action_class == "mutating"
    assert decision.level == "review"
    assert decision.requires_approval is True
    assert decision.has_approved_approval_path is True
    assert decision.allowed is True
    assert decision.validation_error() is None
    assert "mcp_mutation" in decision.categories


def test_execution_policy_decision_rejects_merge_path_that_skips_approval():
    decisions = build_execution_policy_decisions(
        nodes=[
            _node("manual_a", "trigger/manual"),
            _node("manual_b", "trigger/manual"),
            _node("approval", "logic/human_approval"),
            _node("merge", "logic/merge"),
            _node("restart", "ops/service_action", {"action": "restart", "service": "nginx"}),
        ],
        edges=[
            _edge("manual_a", "approval"),
            _edge("approval", "merge", "approved"),
            _edge("manual_b", "merge"),
            _edge("merge", "restart"),
        ],
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.node_id == "restart"
    assert decision.allowed is False
    assert decision.has_approved_approval_path is False
    assert decision.validation_error() == (
        "Policy guard: mutating node 'restart' (restart) requires an approved human approval path."
    )


def test_execution_policy_decision_flags_dangerous_ssh_command():
    decisions = build_execution_policy_decisions(
        nodes=[
            _node("manual", "trigger/manual"),
            _node("ssh", "agent/ssh_cmd", {"label": "Clear temp", "command": "rm -rf /tmp/app-cache"}),
        ],
        edges=[_edge("manual", "ssh")],
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.node_id == "ssh"
    assert decision.action_class == "dangerous"
    assert decision.level == "dangerous"
    assert decision.allowed is False
    assert decision.to_risk_item()["level"] == "dangerous"


def test_execution_policy_marks_external_output_without_blocking_validation():
    decisions = build_execution_policy_decisions(
        nodes=[
            _node("manual", "trigger/manual"),
            _node(
                "webhook",
                "output/webhook",
                {"label": "Notify ITSM", "url": "https://ops.example.test/hook?token=secret-token"},
            ),
            _node("telegram", "output/telegram", {"label": "Telegram", "chat_id": "12345", "bot_token": "secret"}),
        ],
        edges=[_edge("manual", "webhook"), _edge("webhook", "telegram", "success")],
    )

    assert [decision.action_class for decision in decisions] == ["external", "external"]
    assert all(decision.level == "review" for decision in decisions)
    assert all(decision.requires_approval is False for decision in decisions)
    assert all(decision.allowed is True for decision in decisions)
    assert decisions[0].command == "https://ops.example.test/hook?token=%5Bredacted%5D"


def test_execution_policy_summary_is_runtime_audit_friendly():
    decisions = build_execution_policy_decisions(
        nodes=[
            _node("manual", "trigger/manual"),
            _node("email", "output/email", {"to_email": "ops@example.test,sre@example.test"}),
            _node("ssh", "agent/ssh_cmd", {"command": "systemctl restart nginx"}),
        ],
        edges=[_edge("manual", "email"), _edge("email", "ssh", "success")],
    )

    summary = summarize_execution_policy_decisions(decisions)

    assert summary["version"] == 1
    assert summary["level"] == "review"
    assert summary["total"] == 2
    assert summary["requires_approval"] == 1
    assert summary["blocked"] == 1
    assert summary["by_action_class"] == {"external": 1, "mutating": 1, "dangerous": 0}
