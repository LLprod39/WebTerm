import json
from hashlib import sha256
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import Client

from app.agent_kernel.memory.types import SnapshotCandidate
from app.ai_runtime import ExecutionMode, ProviderTarget
from core_ui.models.ai_providers import AIProviderInvocation
from servers.adapters.django_memory_dreams import dream_server_memory
from servers.adapters.django_memory_llm import distill_with_llm
from servers.adapters.django_memory_snapshot_actions import record_revalidation_decision
from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import (
    Server,
    ServerMemoryGenerationLog,
    ServerMemoryRevalidation,
    ServerMemorySnapshot,
)
from tests.servers_api_smoke_harness import grant_feature


def _server(owner: User, *, name: str) -> Server:
    return Server.objects.create(
        user=owner,
        name=name,
        host="10.20.30.40",
        port=22,
        username="root",
    )


def _execution_context(owner: User, server: Server, *, idempotency_key: str):
    return SimpleNamespace(
        actor_user_id=owner.id,
        project_id=server.project_id,
        source_kind="server_memory",
        source_id=str(server.id),
        purpose="opssummary",
        idempotency_key=idempotency_key,
    )


@pytest.mark.django_db(transaction=True)
def test_distillation_logs_hashes_and_links_provider_invocation_without_raw_payload(monkeypatch):
    owner = User.objects.create_user(username="memory-provenance-owner", password="x")
    server = _server(owner, name="provenance-node")
    raw_output = json.dumps(
        {
            "profile": "- Ubuntu is measured",
            "runbook": "- SECRET_OUTPUT must never be stored in the provenance row",
        }
    )
    prompt_probe = "server-memory:test:distill"
    context = _execution_context(owner, server, idempotency_key=prompt_probe)
    invocation = AIProviderInvocation.objects.create(
        user=owner,
        project_id=server.project_id,
        target_id=ProviderTarget.OLLAMA_LOCAL.value,
        purpose=context.purpose,
        source_kind=context.source_kind,
        source_id=context.source_id,
        mode=ExecutionMode.UNATTENDED.value,
        binding_snapshot={},
        idempotency_key=context.idempotency_key,
        status=AIProviderInvocation.STATUS_SUCCEEDED,
    )

    class FakeProvider:
        async def stream_chat(self, *args, **kwargs):
            yield raw_output

    monkeypatch.setattr("app.core.llm.LLMProvider", FakeProvider)
    monkeypatch.setattr(
        "core_ui.services.ai_execution_context.build_execution_context",
        lambda **kwargs: context,
    )

    logs: list[ServerMemoryGenerationLog] = []
    result = distill_with_llm(
        server=server,
        candidates=[
            SnapshotCandidate(
                memory_key="profile",
                title="Profile",
                content="- heuristic profile",
                importance_score=0.5,
                stability_score=0.5,
                confidence=0.7,
                source_kind="dream",
            ),
            SnapshotCandidate(
                memory_key="runbook",
                title="Runbook",
                content="- heuristic runbook",
                importance_score=0.5,
                stability_score=0.5,
                confidence=0.7,
                source_kind="dream",
            ),
        ],
        model_alias="opssummary",
        generation_log_out=logs,
    )

    assert result["profile"] == "- Ubuntu is measured"
    assert len(logs) == 1
    log = ServerMemoryGenerationLog.objects.get(pk=logs[0].pk)
    assert log.status == ServerMemoryGenerationLog.STATUS_SUCCEEDED
    assert log.invocation_id == invocation.id
    assert log.prompt_template_key == "server_memory_distillation"
    assert log.prompt_template_version == "v1"
    assert log.output_sha256 == sha256(raw_output.encode("utf-8")).hexdigest()
    persisted = " ".join(
        [
            log.prompt_redacted_ref,
            log.output_redacted_ref,
            log.error_redacted_ref,
            log.error_code,
        ]
    )
    assert "SECRET_OUTPUT" not in persisted
    assert len(log.prompt_redacted_ref) <= 255
    assert len(log.output_redacted_ref) <= 255
    assert not log.prompt_redacted_ref.startswith("memory://")


@pytest.mark.django_db(transaction=True)
def test_distillation_failure_records_redacted_fallback_and_returns_heuristic_signal(monkeypatch):
    owner = User.objects.create_user(username="memory-fallback-owner", password="x")
    server = _server(owner, name="fallback-node")
    context = _execution_context(owner, server, idempotency_key="server-memory:test:fallback")

    class FailingProvider:
        async def stream_chat(self, *args, **kwargs):
            if False:
                yield ""
            raise RuntimeError("SECRET_EXCEPTION_DETAIL")

    monkeypatch.setattr("app.core.llm.LLMProvider", FailingProvider)
    monkeypatch.setattr(
        "core_ui.services.ai_execution_context.build_execution_context",
        lambda **kwargs: context,
    )

    logs: list[ServerMemoryGenerationLog] = []
    result = distill_with_llm(
        server=server,
        candidates=[
            SnapshotCandidate(
                memory_key="runbook",
                title="Runbook",
                content="- keep heuristic fallback",
                importance_score=0.5,
                stability_score=0.5,
                confidence=0.7,
                source_kind="dream",
            )
        ],
        model_alias="opssummary",
        generation_log_out=logs,
    )

    log = ServerMemoryGenerationLog.objects.get(pk=logs[0].pk)
    assert result == {}
    assert log.status == ServerMemoryGenerationLog.STATUS_FALLBACK
    assert log.error_code == "generation_failed"
    assert "RuntimeError" in log.error_redacted_ref
    assert "SECRET_EXCEPTION_DETAIL" not in log.error_redacted_ref


@pytest.mark.django_db(transaction=True)
def test_dream_keeps_heuristic_runbook_canonical_and_routes_llm_runbook_to_review_candidate(monkeypatch):
    owner = User.objects.create_user(username="memory-review-owner", password="x")
    server = _server(owner, name="review-node")
    generation_log = ServerMemoryGenerationLog.objects.create(
        server=server,
        generation_kind=ServerMemoryGenerationLog.KIND_DISTILLATION,
        status=ServerMemoryGenerationLog.STATUS_SUCCEEDED,
        model_alias="opssummary",
        prompt_sha256="a" * 64,
        output_sha256="b" * 64,
    )
    candidate = SnapshotCandidate(
        memory_key="runbook",
        title="Canonical Runbook",
        content="- heuristic safe runbook",
        importance_score=0.7,
        stability_score=0.6,
        confidence=0.8,
        source_kind="dream",
        metadata={"trust_level": "system_measured", "verification_status": "measured"},
    )
    profile_candidate = SnapshotCandidate(
        memory_key="profile",
        title="Canonical Profile",
        content="- heuristic profile",
        importance_score=0.6,
        stability_score=0.7,
        confidence=0.8,
        source_kind="dream",
        metadata={"trust_level": "system_measured", "verification_status": "measured"},
    )
    store = DjangoServerMemoryStore()
    monkeypatch.setattr(store, "_compact_open_groups_sync", lambda *args, **kwargs: 0)
    monkeypatch.setattr(store, "_derive_operational_patterns", lambda *args, **kwargs: [])
    monkeypatch.setattr(store, "_build_snapshot_candidates", lambda **kwargs: [candidate, profile_candidate])
    monkeypatch.setattr(store, "_should_distill_with_llm", lambda *args, **kwargs: True)

    def fake_distill(**kwargs):
        kwargs["generation_log_out"].append(generation_log)
        return {
            "runbook": "- LLM suggested operational decision",
            "profile": "- LLM summarized measured profile",
        }

    monkeypatch.setattr(store, "_distill_with_llm_sync", fake_distill)
    monkeypatch.setattr(store, "_llm_enhance_patterns_sync", lambda **kwargs: {})
    monkeypatch.setattr(
        store,
        "_promote_pattern_candidates_sync",
        lambda **kwargs: {"pattern_candidates": 0, "automation_candidates": 0, "skill_drafts": 0},
    )
    monkeypatch.setattr(store, "_archive_old_events_sync", lambda *args, **kwargs: 0)

    result = dream_server_memory(store, server.id, job_kind="nightly")

    canonical = ServerMemorySnapshot.objects.get(server=server, memory_key="runbook", is_active=True)
    profile = ServerMemorySnapshot.objects.get(server=server, memory_key="profile", is_active=True)
    review = ServerMemorySnapshot.objects.get(server=server, memory_key="llm_candidate:runbook", is_active=True)
    assert canonical.layer == ServerMemorySnapshot.LAYER_CANONICAL
    assert canonical.content == "- heuristic safe runbook"
    assert canonical.generation_log_id is None
    assert profile.content == "- LLM summarized measured profile"
    assert profile.generation_log_id == generation_log.id
    assert profile.metadata["trust_level"] == "system_measured"
    assert profile.metadata["derivation_kind"] == "llm_distilled"
    assert profile.metadata["derived_from_trust_level"] == "system_measured"
    assert review.layer == ServerMemorySnapshot.LAYER_CANDIDATE
    assert review.content == "- LLM suggested operational decision"
    assert review.generation_log_id == generation_log.id
    assert review.content_hash == sha256(review.content.encode("utf-8")).hexdigest()
    assert review.metadata["candidate_requires_review"] is True
    assert ServerMemoryRevalidation.objects.filter(
        server=server,
        source_snapshot=review,
        status=ServerMemoryRevalidation.STATUS_OPEN,
    ).exists()
    assert result["llm_review_candidates"] == 1


@pytest.mark.django_db(transaction=True)
def test_revalidation_decision_is_scoped_to_the_linked_snapshot():
    owner = User.objects.create_user(username="memory-decision-scope-owner", password="x")
    server = _server(owner, name="decision-scope-node")
    older = ServerMemorySnapshot.objects.create(
        server=server,
        memory_key="llm_candidate:runbook",
        layer=ServerMemorySnapshot.LAYER_ARCHIVE,
        title="Older Candidate",
        content="- old",
        source_kind="dream",
        version_group_id="older-scope",
        is_active=False,
    )
    current = ServerMemorySnapshot.objects.create(
        server=server,
        memory_key="llm_candidate:runbook",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
        title="Current Candidate",
        content="- current",
        source_kind="dream",
        version_group_id="current-scope",
    )
    older_review = ServerMemoryRevalidation.objects.create(
        server=server,
        source_snapshot=older,
        memory_key=older.memory_key,
        title=older.title,
        reason="Older review",
    )
    current_review = ServerMemoryRevalidation.objects.create(
        server=server,
        source_snapshot=current,
        memory_key=current.memory_key,
        title=current.title,
        reason="Current review",
    )

    updated = record_revalidation_decision(
        current,
        actor_user_id=owner.id,
        status=ServerMemoryRevalidation.STATUS_VERIFIED_TRUE,
        reason="approved current snapshot",
    )

    assert updated == 1
    older_review.refresh_from_db()
    current_review.refresh_from_db()
    assert older_review.status == ServerMemoryRevalidation.STATUS_OPEN
    assert older_review.decided_by_id is None
    assert current_review.status == ServerMemoryRevalidation.STATUS_VERIFIED_TRUE
    assert current_review.decided_by_id == owner.id


@pytest.mark.django_db(transaction=True)
def test_candidate_promotion_requires_staff_and_records_human_revalidation_decision():
    owner = User.objects.create_user(username="memory-approval-owner", password="x")
    grant_feature(owner, "servers")
    server = _server(owner, name="approval-node")
    candidate = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="llm_candidate:runbook",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
        title="LLM Review Candidate",
        content="- proposed runbook",
        source_kind="dream",
        version_group_id="approval-test",
        metadata={"candidate_requires_review": True},
    )
    revalidation = ServerMemoryRevalidation.objects.create(
        server=server,
        source_snapshot=candidate,
        memory_key=candidate.memory_key,
        title=candidate.title,
        reason="Human approval required",
    )
    older_snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key=candidate.memory_key,
        layer=ServerMemorySnapshot.LAYER_ARCHIVE,
        title="Older LLM Candidate",
        content="- older proposal",
        source_kind="dream",
        version_group_id="older-approval-test",
        is_active=False,
    )
    older_revalidation = ServerMemoryRevalidation.objects.create(
        server=server,
        source_snapshot=older_snapshot,
        memory_key=candidate.memory_key,
        title=older_snapshot.title,
        reason="Independent older review",
    )
    client = Client()
    client.force_login(owner)
    endpoint = f"/servers/api/{server.id}/memory/snapshots/{candidate.id}/promote-note/"

    listing = client.get(f"/servers/api/{server.id}/memory/snapshots/")
    assert listing.status_code == 200
    listed_candidate = next(item for item in listing.json()["items"] if item["id"] == candidate.id)
    assert listed_candidate["kind"] == "llm_candidate"

    forbidden = client.post(endpoint, data="{}", content_type="application/json")
    assert forbidden.status_code == 403
    revalidation.refresh_from_db()
    assert revalidation.status == ServerMemoryRevalidation.STATUS_OPEN
    assert revalidation.decided_by_id is None

    owner.is_staff = True
    owner.save(update_fields=["is_staff"])
    approved = client.post(endpoint, data="{}", content_type="application/json")
    assert approved.status_code == 200
    revalidation.refresh_from_db()
    assert revalidation.status == ServerMemoryRevalidation.STATUS_VERIFIED_TRUE
    assert revalidation.decided_by_id == owner.id
    assert revalidation.decided_at is not None
    assert revalidation.decision_reason == "promoted_to_manual_note"
    older_revalidation.refresh_from_db()
    assert older_revalidation.status != ServerMemoryRevalidation.STATUS_VERIFIED_TRUE
    assert older_revalidation.decided_by_id is None
