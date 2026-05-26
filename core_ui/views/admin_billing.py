"""
Provider billing helpers for the admin dashboard.
"""

import json
import os
import time
from datetime import datetime, timezone
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from loguru import logger

_PROVIDER_BILLING_CACHE = {"ts": 0.0, "date": "", "data": {}}
_PROVIDER_BILLING_CACHE_TTL_SECONDS = int(os.getenv("DASHBOARD_BILLING_CACHE_TTL_SECONDS", "600"))


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _extract_numeric_by_key(payload, key_candidates):
    key_candidates = {k.lower() for k in key_candidates}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in key_candidates:
                parsed = _to_float(value)
                if parsed is not None:
                    return parsed
        for value in payload.values():
            parsed = _extract_numeric_by_key(value, key_candidates)
            if parsed is not None:
                return parsed
    elif isinstance(payload, list):
        for item in payload:
            parsed = _extract_numeric_by_key(item, key_candidates)
            if parsed is not None:
                return parsed
    return None


def _http_get_json(url: str, headers: dict | None = None, timeout: int = 4):
    req = urllib_request.Request(url=url, method="GET", headers=headers or {})
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset))


def _sum_openai_costs(payload: dict) -> float:
    total = 0.0
    for bucket in payload.get("data", []):
        amount = bucket.get("amount")
        if isinstance(amount, dict):
            value = _to_float(amount.get("value"))
            if value is not None:
                total += value
        else:
            value = _to_float(amount)
            if value is not None:
                total += value
        for result in bucket.get("results", []):
            amount = result.get("amount")
            value = _to_float(amount.get("value")) if isinstance(amount, dict) else _to_float(amount)
            if value is not None:
                total += value
    return total


def _sum_anthropic_costs(payload: dict) -> float:
    total = 0.0
    for bucket in payload.get("data", []):
        rows = bucket.get("results") or [bucket]
        for row in rows:
            amount = row.get("amount")
            if isinstance(amount, dict):
                value = _to_float(amount.get("value") or amount.get("usd") or amount.get("amount"))
            else:
                value = _to_float(amount)
            if value is not None:
                total += value
    return total


def _fetch_openai_billing(today_start_ts: int, now_ts: int) -> dict:
    admin_key = os.getenv("OPENAI_ADMIN_API_KEY", "").strip()
    result = {
        "actual_spend_usd": None,
        "balance_usd": None,
        "billing_source": "estimated_logs",
        "billing_note": "Set OPENAI_ADMIN_API_KEY for actual spend.",
    }
    if not admin_key:
        return result

    total_cost = 0.0
    next_page = None
    try:
        for _ in range(5):
            params = {
                "start_time": str(today_start_ts),
                "end_time": str(now_ts),
                "bucket_width": "1d",
                "limit": "31",
            }
            if next_page:
                params["page"] = next_page
            url = "https://api.openai.com/v1/organization/costs?" + urllib_parse.urlencode(params)
            payload = _http_get_json(
                url,
                headers={
                    "Authorization": f"Bearer {admin_key}",
                    "Content-Type": "application/json",
                },
            )
            total_cost += _sum_openai_costs(payload)
            next_page = payload.get("next_page")
            if not payload.get("has_more") or not next_page:
                break
        result["actual_spend_usd"] = round(total_cost, 4)
        result["billing_source"] = "openai_organization_costs_api"
        result["billing_note"] = "Actual spend from OpenAI costs API."
    except urllib_error.HTTPError as exc:
        if exc.code in (401, 403):
            result["billing_note"] = "OpenAI admin key is required for /organization/costs."
        else:
            result["billing_note"] = f"OpenAI billing API HTTP {exc.code}."
    except Exception as exc:
        logger.debug(f"OpenAI billing fetch failed: {exc}")
        result["billing_note"] = "OpenAI billing API unavailable."
    return result


def _fetch_anthropic_billing(day_start_utc: datetime, day_end_utc: datetime) -> dict:
    admin_key = os.getenv("ANTHROPIC_ADMIN_API_KEY", "").strip()
    result = {
        "actual_spend_usd": None,
        "balance_usd": None,
        "billing_source": "estimated_logs",
        "billing_note": "Set ANTHROPIC_ADMIN_API_KEY for actual spend.",
    }
    if not admin_key:
        return result

    total_cost = 0.0
    next_page = None
    start_iso = day_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = day_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    beta_header = os.getenv("ANTHROPIC_USAGE_COST_BETA", "usage-2025-06-01").strip()
    try:
        for _ in range(5):
            params = {
                "starting_at": start_iso,
                "ending_at": end_iso,
                "limit": "31",
            }
            if next_page:
                params["page"] = next_page
            url = "https://api.anthropic.com/v1/organizations/cost_report?" + urllib_parse.urlencode(params)
            headers = {
                "x-api-key": admin_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            if beta_header:
                headers["anthropic-beta"] = beta_header
            payload = _http_get_json(url, headers=headers)
            total_cost += _sum_anthropic_costs(payload)
            next_page = payload.get("next_page")
            if not payload.get("has_more") or not next_page:
                break
        result["actual_spend_usd"] = round(total_cost, 4)
        result["billing_source"] = "anthropic_cost_report_api"
        result["billing_note"] = "Actual spend from Anthropic cost report API."
    except urllib_error.HTTPError as exc:
        if exc.code in (401, 403):
            result["billing_note"] = "Anthropic admin key is required for cost report API."
        else:
            result["billing_note"] = f"Anthropic billing API HTTP {exc.code}."
    except Exception as exc:
        logger.debug(f"Anthropic billing fetch failed: {exc}")
        result["billing_note"] = "Anthropic billing API unavailable."
    return result


def _fetch_xai_billing(team_id: str, now_ts: int) -> dict:
    management_key = os.getenv("XAI_MANAGEMENT_API_KEY", "").strip()
    result = {
        "actual_spend_usd": None,
        "balance_usd": None,
        "billing_source": "estimated_logs",
        "billing_note": "Set XAI_MANAGEMENT_API_KEY and XAI_TEAM_ID for billing data.",
    }
    if not management_key or not team_id:
        return result

    base_url = f"https://management-api.x.ai/v1/billing/teams/{urllib_parse.quote(team_id, safe='')}"
    headers = {"Authorization": f"Bearer {management_key}", "Content-Type": "application/json"}

    try:
        balance_payload = _http_get_json(f"{base_url}/prepaid/balance", headers=headers)
        balance = _extract_numeric_by_key(
            balance_payload,
            {
                "balance",
                "current_balance",
                "remaining_balance",
                "prepaid_balance",
                "available_balance",
                "credit_balance",
            },
        )
        if balance is not None:
            result["balance_usd"] = round(balance, 4)
            result["billing_source"] = "xai_management_api"
            result["billing_note"] = "Balance from xAI management billing API."
    except urllib_error.HTTPError as exc:
        if exc.code in (401, 403):
            result["billing_note"] = "xAI management API key/team access required."
        else:
            result["billing_note"] = f"xAI balance API HTTP {exc.code}."
    except Exception as exc:
        logger.debug(f"xAI balance fetch failed: {exc}")
        result["billing_note"] = "xAI balance API unavailable."

    usage_urls = [
        f"{base_url}/usage?{urllib_parse.urlencode({'end_time': str(now_ts), 'bucket_width': '1d', 'limit': '1'})}",
        f"{base_url}/usage",
    ]
    for usage_url in usage_urls:
        try:
            usage_payload = _http_get_json(usage_url, headers=headers)
            spend = _extract_numeric_by_key(
                usage_payload,
                {
                    "total_cost",
                    "total_spend",
                    "spent",
                    "spend",
                    "cost_usd",
                    "amount_usd",
                },
            )
            if spend is not None:
                result["actual_spend_usd"] = round(spend, 4)
                if result["billing_source"] == "estimated_logs":
                    result["billing_source"] = "xai_management_api"
                result["billing_note"] = "Spend from xAI management usage API."
                break
        except Exception:
            continue

    return result


def _get_provider_billing_snapshot(now_utc: datetime, providers: dict) -> dict:
    global _PROVIDER_BILLING_CACHE

    cache_date = now_utc.date().isoformat()
    cache_age = time.monotonic() - _PROVIDER_BILLING_CACHE["ts"]
    if (
        _PROVIDER_BILLING_CACHE["data"]
        and _PROVIDER_BILLING_CACHE["date"] == cache_date
        and cache_age < _PROVIDER_BILLING_CACHE_TTL_SECONDS
    ):
        return _PROVIDER_BILLING_CACHE["data"]

    day_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    day_end = now_utc
    day_start_ts = int(day_start.timestamp())
    now_ts = int(day_end.timestamp())
    team_id = os.getenv("XAI_TEAM_ID", "").strip()

    data = {
        "gemini": {
            "actual_spend_usd": None,
            "balance_usd": None,
            "billing_source": "estimated_logs",
            "billing_note": "Gemini API key has no direct balance endpoint; use Google Cloud Billing.",
        },
        "grok": {
            "actual_spend_usd": None,
            "balance_usd": None,
            "billing_source": "estimated_logs",
            "billing_note": "Set XAI_MANAGEMENT_API_KEY and XAI_TEAM_ID for xAI billing data.",
        },
        "claude": {
            "actual_spend_usd": None,
            "balance_usd": None,
            "billing_source": "estimated_logs",
            "billing_note": "Set ANTHROPIC_ADMIN_API_KEY for Anthropic cost report.",
        },
        "openai": {
            "actual_spend_usd": None,
            "balance_usd": None,
            "billing_source": "estimated_logs",
            "billing_note": "Set OPENAI_ADMIN_API_KEY for OpenAI organization costs.",
        },
        "ollama": {
            "actual_spend_usd": None,
            "balance_usd": None,
            "billing_source": "local_runtime",
            "billing_note": "Ollama runs locally; billing and balance are not applicable.",
        },
    }

    if providers.get("openai", {}).get("enabled"):
        data["openai"] = _fetch_openai_billing(day_start_ts, now_ts)
    if providers.get("claude", {}).get("enabled"):
        data["claude"] = _fetch_anthropic_billing(day_start, day_end)
    if providers.get("grok", {}).get("enabled"):
        data["grok"] = _fetch_xai_billing(team_id, now_ts)

    _PROVIDER_BILLING_CACHE = {"ts": time.monotonic(), "date": cache_date, "data": data}
    return data
