from kubernetes_ops.services.admin_watch import _normalize_watch_payload


def test_watch_bookmark_does_not_skip_truncated_resource_events():
    events, truncated, latest_resource_version = _normalize_watch_payload(
        {
            "items": [
                {"type": "ADDED", "object": {"metadata": {"name": "pod-a", "resourceVersion": "10"}}},
                {"type": "MODIFIED", "object": {"metadata": {"name": "pod-b", "resourceVersion": "11"}}},
                {"type": "BOOKMARK", "object": {"metadata": {"resourceVersion": "99"}}},
            ]
        },
        limit=1,
    )

    assert truncated is True
    assert len(events) == 1
    assert events[0]["resource_version"] == "10"
    assert latest_resource_version == "10"
