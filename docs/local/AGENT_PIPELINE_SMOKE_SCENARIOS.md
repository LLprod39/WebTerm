# Operator smoke scenarios (Phase 0)

Run these on a lab stack before Stage B/C. Expect **honest outcomes** (partial/failed when evidence is weak).

## 1. agent/react read-only diagnose

- Node: `agent/react`, SAFE, goal: “Check disk usage and list top processes”, one SSH server.
- Expect: `outcome=success` or `partial` with tool calls; not empty report.
- Fail if: empty goal accepted, or success with zero tools when tools available.

## 2. agent/multi two-server inventory

- Node: `agent/multi`, two servers, `require_all_servers=true`.
- Expect: plan_summary in node state; failed connect → failed if require_all_servers.
- Fail if: mixed failed tasks still open only `success` without `outcome=partial`.

## 3. agent/llm_query chain

- Trigger → llm_query summarizing a fixed prompt → output/report.
- Expect: completed with text; upstream context optional.

## 4. agent/mcp_call read tool

- Configured MCP server + read-only tool.
- Expect: completed output or clear MCP error.

## 5. agent/ssh_cmd fixed command

- `uptime` or `df -h` on one server.
- Expect: exit_code 0 path opens success.

## 6. Unattended ask_user denial

- Schedule or `interaction_mode=unattended` on react with goal that would ask user.
- Expect: tool observation denies ask_user; no 5-minute hang.

## 7. Empty allowlist

- `tools_mode=allowlist`, `allowed_tools=[]`.
- Expect: node fails before LLM with clear error.

## 8. Kill switch

```bash
python manage.py ops_kill_switch --pause --reason smoke
# run agent node → failed pause message
python manage.py ops_kill_switch --resume
```
