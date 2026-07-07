from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.release_evidence import build_kubernetes_release_evidence
from kubernetes_ops.studio_bootstrap import resolve_kubernetes_mcp_user


class Command(BaseCommand):
    help = "Collect Kubernetes Ops release evidence before enabling the production sidebar."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Staff username used for readiness and Studio MCP checks.")
        parser.add_argument("--output", help="Optional JSON file path for the release evidence artifact.")
        parser.add_argument("--skip-provider-probe", action="store_true", help="Skip live provider probes.")
        parser.add_argument("--skip-sync-dry-run", action="store_true", help="Skip provider sync dry-run.")
        parser.add_argument("--skip-mcp-call", action="store_true", help="Skip Studio Kubernetes MCP smoke call.")
        parser.add_argument("--skip-action-controls", action="store_true", help="Skip controlled action request safety proof.")
        parser.add_argument("--skip-post-review-retention", action="store_true", help="Skip Admin action post-review and recording retention proof.")
        parser.add_argument("--skip-external-evidence-bundle", action="store_true", help="Skip external production evidence bundle artifact check.")
        parser.add_argument("--skip-interactive-transport-evidence", action="store_true", help="Skip interactive transport prerequisite artifact check.")
        parser.add_argument("--skip-interactive-live-smoke", action="store_true", help="Skip interactive provider opener live-smoke artifact check.")
        parser.add_argument("--skip-interactive-shell-streams", action="store_true", help="Skip cluster terminal/node debug provider-stream safety proof.")
        parser.add_argument("--skip-readonly-rbac-live", action="store_true", help="Skip live kubectl auth can-i proof for read-only RBAC.")
        parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when evidence has blockers.")

    def handle(self, *args, **options):
        user = resolve_kubernetes_mcp_user(options.get("username"))
        if user is None:
            raise CommandError("No staff user found. Pass --username or create a staff user first.")

        evidence = build_kubernetes_release_evidence(
            user=user,
            run_provider_probe=not options["skip_provider_probe"],
            run_sync_dry_run=not options["skip_sync_dry_run"],
            run_mcp_call=not options["skip_mcp_call"],
            run_action_controls=not options["skip_action_controls"],
            run_post_review_retention=not options["skip_post_review_retention"],
            run_external_evidence_bundle=not options["skip_external_evidence_bundle"],
            run_interactive_transport_evidence=not options["skip_interactive_transport_evidence"],
            run_interactive_live_smoke=not options["skip_interactive_live_smoke"],
            run_interactive_shell_streams=not options["skip_interactive_shell_streams"],
            run_readonly_rbac_live=not options["skip_readonly_rbac_live"],
        )
        payload = json.dumps(evidence, ensure_ascii=False, indent=2)
        output_path = options.get("output")
        if output_path:
            path = Path(output_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(f"Wrote Kubernetes Ops release evidence: {path}")
        else:
            self.stdout.write(payload)

        blockers = evidence.get("blockers") or []
        release_summary = evidence.get("release_summary") if isinstance(evidence.get("release_summary"), dict) else {}
        release_scope = evidence.get("release_scope") or {}
        backend_workstream = evidence.get("backend_workstream") if isinstance(evidence.get("backend_workstream"), dict) else {}
        self.stdout.write(
            f"Kubernetes Ops release evidence: production_ready={evidence.get('production_ready')} "
            f"ready_for_sidebar={evidence.get('ready_for_sidebar')} "
            f"release_scope={release_scope.get('status') or 'unknown'} blockers={len(blockers)}"
        )
        if backend_workstream:
            next_step = backend_workstream.get("next_backend_step") if isinstance(backend_workstream.get("next_backend_step"), dict) else {}
            blocker_summary = (
                backend_workstream.get("external_production_blocker_summary")
                if isinstance(backend_workstream.get("external_production_blocker_summary"), dict)
                else {}
            )
            self.stdout.write(
                "Backend workstream: "
                f"status={backend_workstream.get('status') or 'unknown'} "
                f"backend_complete={backend_workstream.get('backend_complete')} "
                f"core_backend_percent={backend_workstream.get('core_backend_percent')} "
                f"remaining_backend_gaps={backend_workstream.get('remaining_backend_gap_count') or 0} "
                f"external_production_blockers={backend_workstream.get('external_production_blocker_count') or 0} "
                f"external_primary={blocker_summary.get('primary_category') or 'none'} "
                f"next={next_step.get('id') or 'unknown'}"
            )
        if release_summary:
            self.stdout.write(
                "Release summary: "
                f"artifact_safety={release_summary.get('artifact_safety_status') or 'unknown'} "
                f"preflight={release_summary.get('preflight_status') or 'unknown'} "
                f"top_blockers={release_summary.get('top_blockers') or []}"
            )
            for index, step in enumerate(release_summary.get("next_steps") or [], start=1):
                self.stdout.write(f"Next step {index}: {step}")
        if blockers and not options["no_fail"]:
            raise CommandError("; ".join(str(item) for item in blockers[:8]))
