---
name: Kubernetes Safety Workflow
description: "Safe operating workflow for Kubernetes MCP tasks: read-only evidence first, no direct production mutation without approval, and verification after any approved change."
service: kubernetes
category: Infrastructure and Operations
safety_level: high
ui_hint: Attach this to Kubernetes MCP nodes so runtime blocks dangerous raw actions and enforces read-only preflight before mutations.
guardrail_summary: ["Requires kubernetes_describe_workload before mutating workload calls", "Blocks raw kubectl/apply/delete/exec/port-forward style tools", "Keeps diagnosis drafts read-only by default"]
recommended_tools: ["report", "ask_user", "analyze_output"]
runtime_policy: {"applicable_tool_patterns":["^kubernetes_","^kubectl_","^k8s_"],"blocked_tool_patterns":[".*exec.*",".*port_forward.*",".*delete.*",".*apply.*",".*raw.*",".*node_debug.*"],"mutating_tool_patterns":[".*restart.*",".*rollout_restart.*",".*scale.*",".*patch.*",".*annotate.*",".*label.*",".*cordon.*",".*drain.*"],"required_preflight_tools":["kubernetes_describe_workload"],"auto_inject_pinned_arguments":true}
tags: [kubernetes, k8s, mcp, safety, read-only-first]
---
# Kubernetes Safety Workflow

Use this skill for any Kubernetes work done through MCP tools.

## When to use

- The user asks to diagnose, inspect, restart, scale, patch, roll back, or verify Kubernetes workloads.
- A Studio pipeline uses Kubernetes MCP tools.
- The target cluster, namespace, workload, or environment matters.

## Mandatory workflow

1. Start with read-only inventory or workload inspection.
2. Resolve the exact cluster/context, namespace, workload kind, and workload name before any action.
3. Treat diagnosis as read-only unless the user explicitly asks for remediation.
4. For any mutation, require a separate approval-gated workflow with target, reason, blast radius, rollback plan, and verification.
5. Verify after approved mutations using read-only tools.
6. Report uncertainty instead of guessing a namespace, context, or workload.

## Hard rules

- Never run raw `kubectl apply`, delete, exec, port-forward, or node debug through a generic MCP tool.
- Never mutate production workloads from a diagnosis draft.
- Never restart, scale, patch, label, annotate, cordon, or drain without approval and prior read-only evidence.
- Never use a cluster-admin kubeconfig as the default execution credential.
- Prefer GitOps or provider-native workflows for planned production changes.

## Diagnosis Draft Shape

1. Manual trigger.
2. Read-only MCP call such as `kubernetes_describe_workload`.
3. Analysis step over the read-only output.
4. Report output with target, findings, confidence, and next safe checks.

## Reporting

The final report should state:

- cluster/context, namespace, workload kind, and workload name
- evidence used for the diagnosis
- likely causes and confidence
- blast radius and affected owner/team when known
- safe next checks
- whether any remediation requires a separate approved workflow
