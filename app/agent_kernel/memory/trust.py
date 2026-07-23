from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any

TRUST_MANUAL_VERIFIED = "manual_verified"
TRUST_SYSTEM_MEASURED = "system_measured"
TRUST_HUMAN_OBSERVED = "human_observed"
TRUST_AGENT_REPORTED = "agent_reported"
TRUST_AGENT_INFERRED = "agent_inferred"
TRUST_LLM_DISTILLED = "llm_distilled"
TRUST_UNVERIFIED = "unverified"
TRUST_STALE = "stale"

VERIFICATION_VERIFIED = "verified"
VERIFICATION_MEASURED = "measured"
VERIFICATION_UNVERIFIED = "unverified"
VERIFICATION_NEEDS_REVALIDATION = "needs_revalidation"

CANONICAL_TRUST_LEVELS = {TRUST_MANUAL_VERIFIED, TRUST_SYSTEM_MEASURED}
NON_CANONICAL_TRUST_LEVELS = {
    TRUST_AGENT_REPORTED,
    TRUST_AGENT_INFERRED,
    TRUST_LLM_DISTILLED,
    TRUST_UNVERIFIED,
}


def stable_payload_hash(*, raw_text: str = "", payload: Any | None = None) -> str:
    normalized = json.dumps(
        {"raw_text": raw_text or "", "payload": payload if payload is not None else {}},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_idempotency_key(
    *,
    server_id: int,
    source_kind: str,
    source_ref: str = "",
    session_id: str = "",
    event_type: str,
    payload_hash: str,
) -> str:
    locator = (source_ref or session_id or "no-ref")[:58]
    parts = [
        str(server_id),
        str(source_kind or "unknown")[:30],
        str(locator),
        str(event_type or "event")[:40],
        str(payload_hash or "")[:32],
    ]
    return ":".join(parts)[:180]


def infer_event_trust_metadata(
    *,
    source_kind: str,
    actor_kind: str,
    event_type: str = "",
    payload: dict[str, Any] | None = None,
    source_ref: str = "",
) -> dict[str, Any]:
    payload = payload or {}
    source = str(source_kind or "").strip()
    actor = str(actor_kind or "").strip()
    has_measured_exit = isinstance(payload.get("exit_code"), int)
    marked_verified = bool(payload.get("verified"))

    trust_level = TRUST_UNVERIFIED
    verification_status = VERIFICATION_UNVERIFIED
    source_confidence = 0.4

    if source == "manual_knowledge":
        trust_level = TRUST_MANUAL_VERIFIED
        verification_status = VERIFICATION_VERIFIED
        source_confidence = 0.95
    elif source in {"monitoring", "watcher", "system"}:
        trust_level = TRUST_SYSTEM_MEASURED
        verification_status = VERIFICATION_MEASURED
        source_confidence = 0.9
    elif has_measured_exit and source in {"terminal", "pipeline"} and actor != "agent":
        trust_level = TRUST_HUMAN_OBSERVED if actor == "human" else TRUST_SYSTEM_MEASURED
        verification_status = VERIFICATION_MEASURED
        source_confidence = 0.82 if actor == "human" else 0.88
    elif source == "terminal" and actor == "human":
        trust_level = TRUST_HUMAN_OBSERVED
        verification_status = VERIFICATION_VERIFIED if marked_verified else VERIFICATION_UNVERIFIED
        source_confidence = 0.72 if marked_verified else 0.62
    elif source == "pipeline" and has_measured_exit:
        trust_level = TRUST_SYSTEM_MEASURED
        verification_status = VERIFICATION_MEASURED
        source_confidence = 0.84
    elif source in {"agent_run", "agent_event"} or actor == "agent":
        trust_level = TRUST_AGENT_REPORTED
        verification_status = VERIFICATION_VERIFIED if marked_verified else VERIFICATION_UNVERIFIED
        source_confidence = 0.58 if marked_verified else 0.48

    evidence_refs = []
    if source_ref:
        evidence_refs.append(f"{source}:{source_ref}")
    if event_type:
        evidence_refs.append(f"event_type:{event_type}")

    return {
        "trust_level": trust_level,
        "verification_status": verification_status,
        "evidence_refs": evidence_refs,
        "source_actor_kind": actor or "system",
        "source_confidence": source_confidence,
    }


def enrich_metadata_with_trust(
    metadata: dict[str, Any] | None,
    *,
    source_kind: str = "",
    actor_kind: str = "",
    event_type: str = "",
    payload: dict[str, Any] | None = None,
    source_ref: str = "",
    fallback_trust_level: str = TRUST_UNVERIFIED,
    fallback_verification_status: str = VERIFICATION_UNVERIFIED,
) -> dict[str, Any]:
    result = dict(metadata or {})
    inferred = infer_event_trust_metadata(
        source_kind=source_kind,
        actor_kind=actor_kind,
        event_type=event_type,
        payload=payload,
        source_ref=source_ref,
    )
    if (
        inferred["trust_level"] == TRUST_UNVERIFIED
        and fallback_trust_level
        and fallback_trust_level != TRUST_UNVERIFIED
    ):
        inferred["trust_level"] = fallback_trust_level
        inferred["verification_status"] = fallback_verification_status or VERIFICATION_UNVERIFIED
    for key, value in inferred.items():
        result.setdefault(key, value)
    return result


def aggregate_trust_metadata(items: Iterable[Any]) -> dict[str, Any]:
    trust_values: list[str] = []
    verification_values: list[str] = []
    evidence_refs: list[str] = []
    event_ids: list[int] = []
    episode_ids: list[int] = []
    actor_values: list[str] = []
    confidences: list[float] = []

    for item in items:
        metadata = dict(getattr(item, "metadata", None) or {})
        if not metadata:
            metadata = infer_event_trust_metadata(
                source_kind=str(getattr(item, "source_kind", "") or ""),
                actor_kind=str(getattr(item, "actor_kind", "") or ""),
                event_type=str(getattr(item, "event_type", "") or ""),
                payload=getattr(item, "structured_payload", None) or {},
                source_ref=str(getattr(item, "source_ref", "") or ""),
            )
        trust_values.append(str(metadata.get("trust_level") or TRUST_UNVERIFIED))
        verification_values.append(str(metadata.get("verification_status") or VERIFICATION_UNVERIFIED))
        evidence_refs.extend(str(ref) for ref in metadata.get("evidence_refs", []) if str(ref).strip())
        actor_values.append(str(metadata.get("source_actor_kind") or getattr(item, "actor_kind", "") or "system"))
        confidence = metadata.get("source_confidence")
        if isinstance(confidence, (int, float)):
            confidences.append(float(confidence))
        item_id = getattr(item, "id", None)
        if item_id is not None:
            if hasattr(item, "episode_kind"):
                episode_ids.append(int(item_id))
            else:
                event_ids.append(int(item_id))

    trust_set = set(trust_values)
    verification_set = set(verification_values)
    if not trust_values:
        trust_level = TRUST_UNVERIFIED
        verification_status = VERIFICATION_UNVERIFIED
    elif trust_set <= {TRUST_MANUAL_VERIFIED}:
        trust_level = TRUST_MANUAL_VERIFIED
        verification_status = VERIFICATION_VERIFIED
    elif trust_set <= {TRUST_SYSTEM_MEASURED, TRUST_MANUAL_VERIFIED}:
        trust_level = TRUST_SYSTEM_MEASURED
        verification_status = VERIFICATION_MEASURED
    elif trust_set <= {TRUST_HUMAN_OBSERVED, TRUST_MANUAL_VERIFIED, TRUST_SYSTEM_MEASURED} and verification_set <= {
        VERIFICATION_VERIFIED,
        VERIFICATION_MEASURED,
    }:
        trust_level = TRUST_HUMAN_OBSERVED
        verification_status = VERIFICATION_MEASURED
    elif trust_set & {TRUST_AGENT_REPORTED, TRUST_AGENT_INFERRED}:
        trust_level = TRUST_AGENT_REPORTED
        verification_status = VERIFICATION_NEEDS_REVALIDATION
    elif trust_set & {TRUST_LLM_DISTILLED}:
        trust_level = TRUST_LLM_DISTILLED
        verification_status = VERIFICATION_NEEDS_REVALIDATION
    else:
        trust_level = TRUST_UNVERIFIED
        verification_status = VERIFICATION_NEEDS_REVALIDATION

    result = {
        "trust_level": trust_level,
        "verification_status": verification_status,
        "evidence_refs": list(dict.fromkeys(evidence_refs))[:12],
        "derived_from_event_ids": list(dict.fromkeys(event_ids))[:80],
        "derived_from_episode_ids": list(dict.fromkeys(episode_ids))[:40],
        "source_actor_kind": ",".join(list(dict.fromkeys(actor_values))[:4]) or "system",
        "source_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.45,
    }
    return result


def metadata_can_promote_to_canonical(metadata: dict[str, Any] | None) -> bool:
    metadata = metadata or {}
    trust = str(metadata.get("trust_level") or TRUST_UNVERIFIED)
    verification = str(metadata.get("verification_status") or VERIFICATION_UNVERIFIED)
    if trust in CANONICAL_TRUST_LEVELS:
        return True
    return bool(trust == TRUST_HUMAN_OBSERVED and verification in {VERIFICATION_VERIFIED, VERIFICATION_MEASURED})


def prompt_provenance_label(
    *,
    metadata: dict[str, Any] | None = None,
    confidence: float | None = None,
    last_verified_at: Any | None = None,
    source_kind: str = "",
    source_ref: str = "",
) -> str:
    metadata = metadata or {}
    trust = str(
        metadata.get("trust_level") or (TRUST_SYSTEM_MEASURED if source_kind == "monitoring" else TRUST_UNVERIFIED)
    )
    verification = str(metadata.get("verification_status") or VERIFICATION_UNVERIFIED)
    pieces = [trust, verification]
    if confidence is not None:
        pieces.append(f"conf={max(0.0, min(float(confidence), 1.0)):.2f}")
    verified_at = _format_dt(last_verified_at)
    if verified_at:
        pieces.append(f"verified={verified_at}")
    if source_ref:
        pieces.append(f"src={source_kind}:{source_ref}" if source_kind else f"src={source_ref}")
    elif source_kind:
        pieces.append(f"src={source_kind}")
    return "".join(f"[{piece}]" for piece in pieces if piece)


def _format_dt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value)
    return text[:10] if text else ""
