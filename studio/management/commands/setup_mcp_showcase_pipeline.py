from __future__ import annotations

import asyncio
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from studio.mcp.mcp_client import MCPClientError, inspect_mcp_server
from studio.mcp.mcp_showcase import (
    DEMO_ARTIFACT_MANIFEST,
    DEMO_ARTIFACT_PLAN,
    create_showcase_run,
    ensure_demo_mcp_server,
    ensure_showcase_pipeline,
    execute_showcase_run,
)


class Command(BaseCommand):
    help = "Create a large local MCP showcase pipeline and optionally run it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="User to own the MCP showcase pipeline (default: first superuser or first user).",
        )
        parser.add_argument(
            "--run-now",
            action="store_true",
            help="Create the pipeline and execute it immediately.",
        )

    def handle(self, *args, **options):
        if sys.platform == "win32" and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        user = self._resolve_user(options.get("username"))
        mcp_server = ensure_demo_mcp_server(user)
        pipeline = ensure_showcase_pipeline(user, mcp_server)

        try:
            inspection = asyncio.run(inspect_mcp_server(mcp_server))
        except MCPClientError as exc:
            raise CommandError(
                "MCP demo service is not reachable. Start it with "
                "`docker compose up -d mcp-demo` and retry. "
                f"Configured URL: {mcp_server.url}. Error: {exc}"
            ) from exc
        tool_names = ", ".join(tool["name"] for tool in inspection.get("tools", []))

        self.stdout.write(self.style.SUCCESS(f"MCP server ready: {mcp_server.name} (ID={mcp_server.id})"))
        self.stdout.write(f"Tools: {tool_names}")
        self.stdout.write(
            self.style.SUCCESS(f'Pipeline "{pipeline.name}" ready (ID={pipeline.id}) for user {user.username}.')
        )
        self.stdout.write(f"Plan artifact: {DEMO_ARTIFACT_PLAN}")
        self.stdout.write(f"Manifest artifact: {DEMO_ARTIFACT_MANIFEST}")
        self.stdout.write(f"Studio path: /studio/pipelines/{pipeline.id}")

        if not options["run_now"]:
            return

        run = create_showcase_run(pipeline, user)
        run = asyncio.run(execute_showcase_run(run, user.username))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Run finished with status: {run.status} (run #{run.id})"))
        if run.error:
            self.stdout.write(self.style.WARNING(f"Run error: {run.error}"))

        for node_id in ("ai_brief", "check_plan", "check_manifest"):
            state = run.node_states.get(node_id) or {}
            status = state.get("status", "unknown")
            output = (state.get("output") or state.get("error") or "").strip()
            preview = output[:300].replace("\n", " ")
            self.stdout.write(f"- {node_id}: {status} :: {preview}")

    def _resolve_user(self, username: str | None):
        user_model = get_user_model()
        if username:
            user = user_model.objects.filter(username=username).first()
            if not user:
                raise CommandError(f"User '{username}' not found.")
            return user

        user = user_model.objects.filter(is_superuser=True).order_by("id").first()
        if user:
            return user

        user = user_model.objects.order_by("id").first()
        if user:
            return user

        raise CommandError("No users found in the database.")
