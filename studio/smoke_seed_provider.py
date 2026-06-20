from __future__ import annotations

from app.smoke_seed_provider import SmokeSeedItem
from studio.models import Pipeline


class DjangoSmokePipelineSeedProvider:
    def upsert_pipeline(self, *, user_id: int, index: int, server_id: int) -> SmokeSeedItem:
        pipeline_name = f"Smoke Pipeline {index:02d}"
        nodes = [
            {
                "id": "manual",
                "type": "trigger/manual",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Manual trigger"},
            },
            {
                "id": "ssh",
                "type": "agent/ssh_cmd",
                "position": {"x": 280, "y": 0},
                "data": {
                    "label": "Smoke SSH command",
                    "server_id": server_id,
                    "command": "printf 'PIPELINE_OK {load_user} {run_index}\\n'; whoami",
                },
            },
        ]
        edges = [
            {
                "id": "edge-manual-ssh",
                "source": "manual",
                "target": "ssh",
            }
        ]
        pipeline, _created = Pipeline.objects.get_or_create(
            owner_id=user_id,
            name=pipeline_name,
            defaults={
                "description": "Isolated smoke pipeline for concurrent runtime checks",
                "nodes": nodes,
                "edges": edges,
            },
        )
        pipeline.description = "Isolated smoke pipeline for concurrent runtime checks"
        pipeline.nodes = nodes
        pipeline.edges = edges
        pipeline.save()
        pipeline.sync_triggers_from_nodes()
        return SmokeSeedItem(id=pipeline.id, name=pipeline.name)
