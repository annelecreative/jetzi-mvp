#!/usr/bin/env python3
"""Alert schema, validation, and JSON storage for Jetzi."""

from __future__ import annotations

import json
import secrets
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from services.flights import VALID_WEEKDAYS, airport_brief


BASE_DIR = Path(__file__).resolve().parent.parent
ALERTS_PATH = BASE_DIR / "data" / "alerts.json"
MAX_DESTINATIONS = 5

ALERT_SCHEMA_KEYS = (
    "alert_id",
    "created_at",
    "unsubscribe_token",
    "email",
    "status",
    "origin_airport_code",
    "destination_airport_codes",
    "trip_type",
    "adults",
    "max_price_per_traveler",
    "available_departure_days",
    "min_days",
    "frequency",
    "only_send_matching_deals",
    "origin_airport",
    "destination_airports",
)


DAY_LABELS = {
    "mon": "Mon",
    "tue": "Tue",
    "wed": "Wed",
    "thu": "Thu",
    "fri": "Fri",
    "sat": "Sat",
    "sun": "Sun",
}


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def format_created_display(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        localized = parsed.astimezone()
        day = localized.strftime("%d").lstrip("0") or "0"
        hour = localized.strftime("%I").lstrip("0") or "0"
        return f"{day} {localized.strftime('%b %Y')}, {hour}:{localized.strftime('%M %p')}"
    except (ValueError, AttributeError):
        return value


def is_valid_email(email: str) -> bool:
    candidate = (email or "").strip()
    if "@" not in candidate or "." not in candidate:
        return False
    at_index = candidate.find("@")
    dot_index = candidate.rfind(".")
    return at_index > 0 and dot_index > at_index + 1 and dot_index < len(candidate) - 1


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _normalize_departure_days(raw_days: Any) -> Tuple[List[str], bool]:
    if not isinstance(raw_days, list):
        return [], False
    cleaned_days: List[str] = []
    for day in raw_days:
        if not isinstance(day, str):
            continue
        normalized_day = day.strip().lower()
        if normalized_day in VALID_WEEKDAYS and normalized_day not in cleaned_days:
            cleaned_days.append(normalized_day)
    return cleaned_days, True


def _normalize_alert_record(alert: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(alert)
    normalized.setdefault("alert_id", str(uuid.uuid4()))
    normalized.setdefault("created_at", _iso_utc_now())
    normalized.setdefault("unsubscribe_token", secrets.token_urlsafe(32))

    email = normalized.get("email")
    if email in ("",):
        email = None
    normalized["email"] = email

    status = normalized.get("status")
    if status not in {"pending_email", "active", "unsubscribed"}:
        status = "active" if email else "pending_email"
    normalized["status"] = status

    normalized.setdefault("available_departure_days", [])
    normalized.setdefault("destination_airport_codes", [])

    return {key: normalized.get(key) for key in ALERT_SCHEMA_KEYS}


def load_alert_records() -> List[Dict[str, Any]]:
    if not ALERTS_PATH.exists():
        return []
    try:
        raw = json.loads(ALERTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(raw, list):
        return []

    normalized_list = []
    changed = False
    for item in raw:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_alert_record(item)
        if normalized != item:
            changed = True
        normalized_list.append(normalized)

    if changed:
        save_alert_records(normalized_list)
    return normalized_list


def save_alert_records(alerts: List[Dict[str, Any]]) -> None:
    clean_alerts = [_normalize_alert_record(alert) for alert in alerts]
    _atomic_write_json(ALERTS_PATH, clean_alerts)


def append_alert_record(alert: Dict[str, Any]) -> Dict[str, Any]:
    alerts = load_alert_records()
    normalized = _normalize_alert_record(alert)
    alerts.append(normalized)
    save_alert_records(alerts)
    return normalized


def update_alert_record(alert_id: str, updates: Dict[str, Any]) -> Dict[str, Any] | None:
    alerts = load_alert_records()
    updated_alert: Dict[str, Any] | None = None

    for idx, alert in enumerate(alerts):
        if alert.get("alert_id") != alert_id:
            continue
        merged = {**alert, **updates}
        updated = _normalize_alert_record(merged)
        alerts[idx] = updated
        updated_alert = updated
        break

    if updated_alert is None:
        return None

    save_alert_records(alerts)
    return updated_alert


def find_alert_by_token(unsubscribe_token: str) -> Dict[str, Any] | None:
    for alert in load_alert_records():
        if alert.get("unsubscribe_token") == unsubscribe_token:
            return alert
    return None


def unsubscribe_alert(unsubscribe_token: str) -> Dict[str, Any] | None:
    alerts = load_alert_records()
    updated_alert: Dict[str, Any] | None = None

    for idx, alert in enumerate(alerts):
        if alert.get("unsubscribe_token") != unsubscribe_token:
            continue
        merged = {**alert, "status": "unsubscribed"}
        updated = _normalize_alert_record(merged)
        alerts[idx] = updated
        updated_alert = updated
        break

    if updated_alert is None:
        return None

    save_alert_records(alerts)
    return updated_alert


def build_alert_summary(alert: Dict[str, Any]) -> Dict[str, Any]:
    selected_days = alert.get("available_departure_days", [])
    day_labels = [DAY_LABELS.get(day, day) for day in selected_days] if selected_days else ["Any day"]
    return {
        "trip_type_label": "Round trip" if alert.get("trip_type") == "round_trip" else "One way",
        "available_day_labels": day_labels,
        "frequency_label": "Immediately" if alert.get("frequency") == "immediately" else "Daily digest",
        "created_display": format_created_display(alert.get("created_at", "")),
    }


def validate_and_build_alert(form: Dict[str, str], airports_by_code: Dict[str, Dict[str, str]]) -> Tuple[Dict[str, Any] | None, str | None]:
    origin_airport_code = form.get("origin_airport_code", "").strip().upper()
    destination_codes_raw = form.get("destination_airport_codes", "[]")
    trip_type = form.get("trip_type", "round_trip").strip()
    adults_raw = form.get("travelers", "").strip()
    max_price_raw = form.get("max_price_per_traveler", "").strip()
    departure_days_raw = form.get("available_departure_days", "[]")
    min_days_raw = form.get("min_days", "").strip()
    frequency = form.get("frequency", "").strip().lower()
    only_send_matching_raw = form.get("only_send_matching_deals")

    try:
        destination_airport_codes = json.loads(destination_codes_raw)
    except json.JSONDecodeError:
        return None, "Invalid destination list format"

    try:
        available_departure_days_raw = json.loads(departure_days_raw)
    except json.JSONDecodeError:
        return None, "Invalid available_departure_days format"

    if not origin_airport_code:
        return None, "origin_airport_code is required"
    if not isinstance(destination_airport_codes, list) or len(destination_airport_codes) < 1:
        return None, "At least one destination airport is required"
    if len(destination_airport_codes) > MAX_DESTINATIONS:
        return None, "You can select up to 5 destinations"

    cleaned_destinations: List[str] = []
    for code in destination_airport_codes:
        if isinstance(code, str) and code.strip():
            normalized_code = code.strip().upper()
            if normalized_code not in cleaned_destinations:
                cleaned_destinations.append(normalized_code)

    if len(cleaned_destinations) < 1:
        return None, "At least one destination airport is required"
    if len(cleaned_destinations) > MAX_DESTINATIONS:
        return None, "You can select up to 5 destinations"

    try:
        adults = int(adults_raw)
    except ValueError:
        return None, "travelers must be an integer"
    if adults < 1 or adults > 4:
        return None, "travelers must be between 1 and 4"

    try:
        max_price_per_traveler = float(max_price_raw)
    except ValueError:
        return None, "max_price_per_traveler must be a number"
    if max_price_per_traveler < 1:
        return None, "max_price_per_traveler must be at least 1"

    available_departure_days, days_type_valid = _normalize_departure_days(available_departure_days_raw)
    if not days_type_valid:
        return None, "available_departure_days must be a list"

    try:
        min_days = int(min_days_raw)
    except ValueError:
        return None, "min_days must be an integer"
    if min_days < 1:
        return None, "min_days must be at least 1"

    if frequency not in {"immediately", "daily"}:
        return None, "frequency must be immediately or daily"

    if trip_type not in {"round_trip", "one_way"}:
        return None, "trip_type must be round_trip or one_way"

    if frequency == "immediately":
        only_send_matching_deals = True
    else:
        only_send_matching_deals = str(only_send_matching_raw or "").lower() in {
            "1",
            "true",
            "on",
            "yes",
        }

    record: Dict[str, Any] = {
        "alert_id": str(uuid.uuid4()),
        "created_at": _iso_utc_now(),
        "unsubscribe_token": secrets.token_urlsafe(32),
        "email": None,
        "status": "pending_email",
        "origin_airport_code": origin_airport_code,
        "destination_airport_codes": cleaned_destinations,
        "trip_type": trip_type,
        "adults": adults,
        "max_price_per_traveler": max_price_per_traveler,
        "available_departure_days": available_departure_days,
        "min_days": min_days,
        "frequency": frequency,
        "only_send_matching_deals": only_send_matching_deals,
        "origin_airport": airport_brief(origin_airport_code, airports_by_code),
        "destination_airports": [airport_brief(code, airports_by_code) for code in cleaned_destinations],
    }
    return {key: record[key] for key in ALERT_SCHEMA_KEYS}, None


def activate_alert_with_email(alert_id: str, email: str) -> Tuple[Dict[str, Any] | None, str | None]:
    if not is_valid_email(email):
        return None, "Enter a valid email address."

    updated = update_alert_record(alert_id, {"email": email.strip(), "status": "active"})
    if updated is None:
        return None, "Alert not found."
    return updated, None


def list_active_alerts() -> List[Dict[str, Any]]:
    return [alert for alert in load_alert_records() if alert.get("status") == "active"]
