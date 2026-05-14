from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from django.utils.dateparse import parse_datetime


CHAT_CONTEXT_SESSION_KEY = "chatcontext"
CHAT_TIMEOUT_MINUTES = 10
PENDING_ACTION_KEYS = ("pending_action", "pending_summary", "pending_booking_id", "confirmation_approved")

CITY_MAP = {
    "banglore": ["bangalore", "bengaluru", "banglore", "bglr"],
    "mumbai": ["mumbai", "bombay"],
    "delhi": ["delhi", "new delhi", "ndls"],
    "chennai": ["chennai", "madras"],
    "kolkata": ["kolkata", "calcutta"],
    "hyderabad": ["hyderabad", "hyd"],
}


def read_chat_payload(request: HttpRequest) -> dict[str, Any]:
    if request.method == "POST":
        try:
            body = request.body.decode("utf-8") if request.body else "{}"
            payload = json.loads(body)
            return payload if isinstance(payload, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
    return {
        "query": request.GET.get("query", ""),
        "mode": request.GET.get("mode", ""),
        "required_fields": request.GET.get("required_fields", []),
    }


def normalize_required_fields(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            return []
    return []


def get_agent_context(request: HttpRequest, mode: str) -> dict[str, Any]:
    context = request.session.get(CHAT_CONTEXT_SESSION_KEY, {})
    if not isinstance(context, dict):
        context = {}

    last_raw = context.get("last_modified_at")
    last_time = parse_datetime(last_raw) if last_raw else None
    mode_changed = bool(context.get("agent_mode")) and context.get("agent_mode") != mode

    if mode_changed or (last_time and timezone.now() > last_time + timedelta(minutes=CHAT_TIMEOUT_MINUTES)):
        context = {}

    context.setdefault("agent_mode", mode)
    request.session[CHAT_CONTEXT_SESSION_KEY] = context
    return context


def normalize_city_name(value: str) -> str:
    city = (value or "").lower().strip()
    for standard_city, variants in CITY_MAP.items():
        if city in variants:
            return standard_city
    return city


def merge_agent_filters(context: dict[str, Any], filters: dict[str, Any]) -> None:
    previous_city = context.get("city", "")
    previous_area = context.get("area", "")
    previous_sport = context.get("sporttype", "")
    previous_ground_type = context.get("ground_or_turf", "")

    updated_keys: set[str] = set()
    for key, value in filters.items():
        if key == "shifts":
            if isinstance(value, dict) and any(value.get(part) for part in ("start_day", "middle_days", "end_day")):
                context[key] = value
                updated_keys.add(key)
            continue
        if value not in ("", None, False):
            context[key] = value
            updated_keys.add(key)

    if "city" in context:
        context["city"] = normalize_city_name(context["city"])

    if previous_city and context.get("city") and previous_city != context["city"]:
        context.pop("area", None)
        context.pop("ground_or_turf_name", None)

    if previous_area and context.get("area") and previous_area != context["area"]:
        context.pop("ground_or_turf_name", None)

    if previous_sport and context.get("sporttype") and previous_sport != context["sporttype"]:
        context.pop("ground_or_turf", None)
        context.pop("ground_or_turf_name", None)

    if previous_ground_type and context.get("ground_or_turf") and previous_ground_type != context["ground_or_turf"]:
        context.pop("ground_or_turf_name", None)

    if updated_keys:
        for key in PENDING_ACTION_KEYS:
            context.pop(key, None)

    context["last_modified_at"] = timezone.now().isoformat()


def reset_agent_context(context: dict[str, Any], mode: str) -> None:
    context.clear()
    context["agent_mode"] = mode
    context["last_modified_at"] = timezone.now().isoformat()
