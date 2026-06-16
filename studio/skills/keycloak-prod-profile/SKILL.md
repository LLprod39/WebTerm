---
name: Keycloak PROD Profile
description: Environment skill for Keycloak PROD operations. Pins work to the prod profile and requires extra caution before mutations.
service: keycloak
category: Identity and Access
safety_level: critical
ui_hint: Use this for PROD-only bots. The runtime pins profile=prod and prevents environment drift during Keycloak runs.
guardrail_summary: ["Pins profile=prod on Keycloak MCP calls","Blocks profile switching","Combines with Keycloak Safety Workflow for mandatory preflight before mutations"]
recommended_tools: ["report","ask_user","analyze_output"]
runtime_policy: {"applicable_tool_patterns":["^keycloak_"],"blocked_tool_patterns":["^keycloak_use_profile$"],"pinned_arguments":{"profile":"prod"},"auto_inject_pinned_arguments":true}
tags: ["keycloak","iam","prod","environment"]
---
# Keycloak PROD Profile

Use this skill when the agent is allowed to work only in the Keycloak PROD environment.

## Environment contract

- Fixed profile: `prod`
- Do not switch to any other profile.
- If `keycloak_current_environment` does not confirm `prod`, stop immediately and ask the user.

## Execution rules

1. Your first Keycloak step must confirm the active environment.
2. Every mutating Keycloak MCP call must explicitly pass `profile="prod"` when supported by the tool.
3. If the request mentions `test`, `sandbox`, or another environment, stop and ask the user before doing anything.
4. Use read-only discovery before every production mutation.
5. Use read-only verification after every production mutation.

## Safety bar for PROD

- Prefer doing fewer mutations over making a risky guess.
- If a user, client, group, or role cannot be matched exactly, stop and ask the user.
- If the request implies bulk changes, spell out the exact resolved targets in the report.

## Final report

Include a line that clearly states:

`Environment used: PROD (profile=prod)`
