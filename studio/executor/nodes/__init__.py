"""
studio/executor/nodes — One file per pipeline node type.

Naming convention: <category>_<name>.py
  output_report.py, output_webhook.py, output_email.py, output_telegram.py
  logic_condition.py, logic_parallel.py, logic_wait.py, logic_human_approval.py
  logic_telegram_input.py, agent_react.py, agent_multi.py, agent_ssh_cmd.py
  agent_llm_query.py, agent_mcp_call.py, ops.py

Each module must register its node class:
    from studio.executor.registry import registry
    @registry.register
    class MyNode(BaseNode):
        node_type = "category/name"
        async def execute(self, ctx): ...

Import this package to auto-register all nodes:
    import studio.executor.nodes
"""

from . import (  # noqa: F401
    agent_llm_query,
    agent_mcp_call,
    agent_multi,
    agent_react,
    agent_ssh_cmd,
    logic_condition,
    logic_human_approval,
    logic_merge,
    logic_parallel,
    logic_telegram_input,
    logic_wait,
    ops,
    output_email,
    output_report,
    output_telegram,
    output_webhook,
)
