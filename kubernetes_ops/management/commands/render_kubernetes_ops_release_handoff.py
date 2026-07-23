from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from kubernetes_ops.services.release_handoff import (
    build_kubernetes_release_handoff,
    render_kubernetes_release_handoff_markdown,
)


class Command(BaseCommand):
    help = "Render a Kubernetes Ops production handoff checklist from the current release evidence artifact."

    def add_arguments(self, parser):
        parser.add_argument("--evidence", help="Optional release evidence JSON artifact path.")
        parser.add_argument("--output", help="Optional output file path.")
        parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")

    def handle(self, *args, **options):
        evidence_path = Path(options["evidence"]).resolve() if options.get("evidence") else None
        handoff = build_kubernetes_release_handoff(evidence_path=evidence_path)
        if options["format"] == "json":
            payload = json.dumps(handoff, ensure_ascii=False, indent=2) + "\n"
        else:
            payload = render_kubernetes_release_handoff_markdown(handoff)

        output_path = options.get("output")
        if output_path:
            path = Path(output_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            self.stdout.write(f"Wrote Kubernetes Ops release handoff: {path}")
        else:
            self.stdout.write(payload.rstrip())

        backend_workstream = (
            handoff.get("backend_workstream") if isinstance(handoff.get("backend_workstream"), dict) else {}
        )
        blocker_summary = (
            backend_workstream.get("external_production_blocker_summary")
            if isinstance(backend_workstream.get("external_production_blocker_summary"), dict)
            else {}
        )
        self.stdout.write(
            f"Kubernetes Ops release handoff: status={handoff.get('status')} "
            f"can_enable_sidebar={handoff.get('can_enable_sidebar')} "
            f"blockers={len(handoff.get('blockers') or [])} "
            f"backend_workstream={backend_workstream.get('status') or 'unknown'} "
            f"external_primary={blocker_summary.get('primary_category') or 'none'}"
        )
