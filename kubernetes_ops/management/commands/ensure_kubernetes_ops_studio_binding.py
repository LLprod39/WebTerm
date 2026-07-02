from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.studio_bootstrap import (
    DEFAULT_KUBERNETES_MCP_NAME,
    ensure_kubernetes_studio_mcp_binding,
    resolve_kubernetes_mcp_url,
    resolve_kubernetes_mcp_user,
)


class Command(BaseCommand):
    help = "Create or update the owned Kubernetes MCP binding used by Kubernetes Ops Studio diagnosis drafts."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Staff username that should own the Kubernetes MCP binding.")
        parser.add_argument("--url", help="MCP JSON-RPC endpoint. Defaults to KUBERNETES_OPS_MCP_URL or mcp-demo.")
        parser.add_argument("--name", default=DEFAULT_KUBERNETES_MCP_NAME, help="MCP server name.")
        parser.add_argument("--skip-test", action="store_true", help="Create/update the binding without testing tools/list.")

    def handle(self, *args, **options):
        user = resolve_kubernetes_mcp_user(options.get("username"))
        if user is None:
            raise CommandError("No staff user found. Pass --username or create a staff user first.")
        if not getattr(user, "is_staff", False):
            raise CommandError(f"User `{user.username}` is not staff; Kubernetes MCP execution is staff-only.")

        url = resolve_kubernetes_mcp_url(options.get("url"))
        result = ensure_kubernetes_studio_mcp_binding(
            user=user,
            url=url,
            name=options["name"],
            test_connection=not options["skip_test"],
        )
        mcp = result["mcp"]
        status = "ready" if result["ok"] else ("untested" if options["skip_test"] else "failed")
        self.stdout.write(
            self.style.SUCCESS(
                f"Kubernetes MCP binding {status}: id={mcp.id} owner={user.username} url={result['url']}"
            )
        )
        if result["granted_features"]:
            self.stdout.write("Granted features: " + ", ".join(result["granted_features"]))
        if result["tool_names"]:
            self.stdout.write("MCP tools: " + ", ".join(result["tool_names"]))
        if result["error"]:
            raise CommandError(result["error"])
