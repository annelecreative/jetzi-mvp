#!/usr/bin/env python3
"""Alert schema, validation, and JSON storage for Jetzi."""

from __future__ import annotations

import json
import secrets
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from services.flights import VALID_WEEKDAYS, airport_brief


BASE_DIR = Path(__file__).resolve().parent.parent
PERSIST_DIR = BASE_DIR / "persist"
LEGACY_DATA_DIR = BASE_DIR / "data"

ALERTS_PATH = PERSIST_DIR / "alerts.json"
LEGACY_ALERTS_PATH = LEGACY_DATA_DIR / "alerts.json"

MAX_DESTINATIONS = 5
BASE_PRICE_BUCKET_USD = 25

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
    "last_deal_sent_at",
    "last_deal_signature",
    "last_deal_total_price",
    "last_no_deal_sent_at",
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


def _normalize_price(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    if normalized < 0:
        return None
    return round(normalized, 2)


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
    normalized.setdefault("last_deal_sent_at", None)
    normalized.setdefault("last_deal_signature", None)
    normalized["last_deal_total_price"] = _normalize_price(normalized.get("last_deal_total_price"))
    normalized.setdefault("last_no_deal_sent_at", None)

    return {key: normalized.get(key) for key in ALERT_SCHEMA_KEYS}


def _initial_alert_payload() -> List[Dict[str, Any]]:
    """
    First-run seed behavior:
    - Prefer existing persisted alerts if present
    - Otherwise seed from legacy repo data/alerts.json if present
    - Otherwise start empty
    """
    if LEGACY_ALERTS_PATH.exists():
        try:
            raw = json.loads(LEGACY_ALERTS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [item for item in raw if isinstance(item, dict)]
        except json.JSONDecodeError:
            pass
    return []


def _ensure_alert_store_exists() -> None:
    if ALERTS_PATH.exists():
        return
    seed = _initial_alert_payload()
    clean_seed = [_normalize_alert_record(alert) for alert in seed]
    _atomic_write_json(ALERTS_PATH, clean_seed)


def load_alert_records() -> List[Dict[str, Any]]:
    _ensure_alert_store_exists()

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


def validate_and_build_alert(
    form: Dict[str, str],
    airports_by_code: Dict[str, Dict[str, str]],
    *,
    max_destinations: int = MAX_DESTINATIONS,
) -> Tuple[Dict[str, Any] | None, str | None]:
    origin_airport_code = form.get("origin_airport_code", "").strip().upper()
    destination_codes_raw = form.get("destination_airport_codes", "[]")
    trip_type = form.get("trip_type", "round_trip").strip()
    adults_raw = form.get("travelers", "").strip()
    max_price_raw = form.get("max_price_per_traveler", "").strip()
    trip_days_raw = form.get("available_departure_days", "[]")
    min_days_raw = form.get("min_days", "").strip()
    frequency = form.get("frequency", "").strip().lower()
    only_send_matching_raw = form.get("only_send_matching_deals")

    try:
        destination_airport_codes = json.loads(destination_codes_raw)
    except json.JSONDecodeError:
        return None, "Invalid destination list format"

    try:
        available_departure_days_raw = json.loads(trip_days_raw)
    except json.JSONDecodeError:
        return None, "Invalid available_departure_days format"

    if not origin_airport_code:
        return None, "origin_airport_code is required"
    if not isinstance(destination_airport_codes, list) or len(destination_airport_codes) < 1:
        return None, "At least one destination airport is required"
    if len(destination_airport_codes) > max_destinations:
        return None, f"You can select up to {max_destinations} destinations"

    cleaned_destinations: List[str] = []
    for code in destination_airport_codes:
        if isinstance(code, str) and code.strip():
            normalized_code = code.strip().upper()
            if normalized_code not in cleaned_destinations:
                cleaned_destinations.append(normalized_code)

    if len(cleaned_destinations) < 1:
        return None, "At least one destination airport is required"
    if len(cleaned_destinations) > max_destinations:
        return None, f"You can select up to {max_destinations} destinations"

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
    if len(available_departure_days) < 1:
        return None, "Select at least 1 day you can be on a trip."

    try:
        min_days = int(min_days_raw)
    except ValueError:
        return None, "min_days must be an integer"
    if min_days < 1:
        return None, "min_days must be at least 1"
    selected_day_count = len(available_departure_days)
    if min_days > selected_day_count:
        return (
            None,
            f"Minimum trip length can't be greater than your selected available departure days ({selected_day_count}).",
        )

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
        "last_deal_sent_at": None,
        "last_deal_signature": None,
        "last_deal_total_price": None,
        "last_no_deal_sent_at": None,
    }
    return {key: record[key] for key in ALERT_SCHEMA_KEYS}, None


def activate_alert_with_email(alert_id: str, email: str) -> Tuple[Dict[str, Any] | None, str | None]:
    if not is_valid_email(email):
        return None, "Enter a valid email address."

    updated = update_alert_record(alert_id, {"email": email.strip().lower(), "status": "active"})
    if updated is None:
        return None, "Alert not found."
    return updated, None


def list_active_alerts() -> List[Dict[str, Any]]:
    return [alert for alert in load_alert_records() if alert.get("status") == "active"]


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_deal_signature(deal: Dict[str, Any], *, price_bucket_usd: int = BASE_PRICE_BUCKET_USD) -> str:
    destination = str(deal.get("destination", "")).upper()
    departure_date = str(deal.get("departing_at", ""))[:10]
    try:
        total_price = float(deal.get("total_price", 0) or 0)
    except (TypeError, ValueError):
        total_price = 0.0

    bucket_size = max(1, price_bucket_usd)
    price_bucket = int(total_price // bucket_size) * bucket_size
    return f"{destination}|{departure_date}|{price_bucket}"


def is_recent_duplicate(alert: Dict[str, Any], signature: str, *, within_hours: int) -> bool:
    last_signature = str(alert.get("last_deal_signature") or "")
    if not last_signature or last_signature != signature:
        return False

    last_sent = _parse_iso(str(alert.get("last_deal_sent_at") or ""))
    if not last_sent:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, within_hours))
    return last_sent >= cutoff


def should_suppress_repeat_send(
    alert: Dict[str, Any],
    *,
    new_total_price: float,
    within_hours: int,
    min_absolute_improvement_usd: float = 50.0,
    min_percent_improvement: int = 10,
) -> tuple[bool, str]:
    last_sent = _parse_iso(str(alert.get("last_deal_sent_at") or ""))
    if not last_sent:
        return False, "no prior sent deal"

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, within_hours))
    if last_sent < cutoff:
        return False, "outside repeat-send window"

    last_total_price = _normalize_price(alert.get("last_deal_total_price"))
    if last_total_price is None:
        return True, "recent deal already sent and missing last sent price"

    new_total_price = round(float(new_total_price), 2)
    if new_total_price >= last_total_price:
        return True, f"recent deal already sent at ${last_total_price:.0f}; new deal is not better"

    absolute_improvement = last_total_price - new_total_price
    percent_improvement = 0
    if last_total_price > 0:
        percent_improvement = round((absolute_improvement / last_total_price) * 100)

    if (
        absolute_improvement < float(min_absolute_improvement_usd)
        and percent_improvement < int(min_percent_improvement)
    ):
        return (
            True,
            f"recent deal already sent; improvement too small (${absolute_improvement:.0f}, {percent_improvement}%)",
        )

    return False, f"meaningfully better deal (${absolute_improvement:.0f}, {percent_improvement}%)"