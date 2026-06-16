from __future__ import annotations

from mars.models import MarsSession
from mars.services import serialize_run, serialize_session


def serialize_project_session(session: MarsSession) -> dict:
    latest_run = getattr(session, "latest_run", None)
    run_count = getattr(session, "run_count", None)
    return {
        "session": serialize_session(session),
        "latest_run": serialize_run(latest_run) if latest_run else None,
        "run_count": int(run_count or 0),
        "recommended_skills": [],
    }
