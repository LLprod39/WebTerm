"""
studio/executor/nodes — One file per pipeline node type.

Naming convention: <category>_<name>.py
  output_report.py, output_webhook.py, output_email.py, output_telegram.py
  logic_condition.py, logic_parallel.py, logic_wait.py, logic_approval.py
  agent_react.py, agent_multi.py, agent_ssh.py, agent_llm.py, agent_mcp.py

Each module must register its node class:
    from studio.executor.registry import registry
    @registry.register
    class MyNode(BaseNode):
        node_type = "category/name"
        async def execute(self, ctx): ...

Import this package to auto-register all nodes:
    import studio.executor.nodes
"""
