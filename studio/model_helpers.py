from __future__ import annotations


def collect_monitoring_filters(data: dict | None) -> dict:
    raw_data = data if isinstance(data, dict) else {}
    nested = raw_data.get("monitoring_filters") if isinstance(raw_data.get("monitoring_filters"), dict) else {}
    filters: dict[str, object] = dict(nested)

    if isinstance(raw_data.get("server_ids"), list):
        server_ids = [int(item) for item in raw_data.get("server_ids", []) if str(item).strip().isdigit()]
        if server_ids:
            filters["server_ids"] = server_ids

    for key in ("severities", "alert_types", "container_names"):
        raw_values = raw_data.get(key)
        if isinstance(raw_values, list):
            values = [str(item or "").strip() for item in raw_values if str(item or "").strip()]
            if values:
                filters[key] = values

    match_text = str(raw_data.get("match_text") or "").strip()
    if match_text:
        filters["match_text"] = match_text

    return filters
