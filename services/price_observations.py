#!/usr/bin/env python3
"""Price observation storage for baseline calculations."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


BASE_DIR = Path(__file__).resolve().parent.parent
OBSERVATIONS_PATH = BASE_DIR / "data" / "price_observations.json"
OBSERVATION_SCHEMA_KEYS = (
    "observed_at",
    "origin_airport_code",
    "destination_airport_code",
    "trip_type",
    "depart_window",
    "return_window",
    "price",
)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_observation(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("observed_at", _iso_utc_now())
    normalized["origin_airport_code"] = str(normalized.get("origin_airport_code", "")).strip().upper()
    normalized["destination_airport_code"] = str(normalized.get("destination_airport_code", "")).strip().upper()
    normalized["trip_type"] = str(normalized.get("trip_type", "round_trip")).strip()
    normalized["depart_window"] = str(normalized.get("depart_window", "any")).strip().lower()
    normalized["return_window"] = str(normalized.get("return_window", "n/a")).strip().lower()

    try:
        normalized["price"] = float(normalized.get("price", 0) or 0)
    except (TypeError, ValueError):
        normalized["price"] = 0.0

    return {key: normalized.get(key) for key in OBSERVATION_SCHEMA_KEYS}


def _build_depart_window(alert: Dict[str, Any]) -> str:
    days = alert.get("available_departure_days") or []
    if not isinstance(days, list) or not days:
        return "any"
    clean = sorted({str(day).strip().lower() for day in days if str(day).strip()})
    return ",".join(clean) if clean else "any"


def _build_return_window(alert: Dict[str, Any]) -> str:
    trip_type = str(alert.get("trip_type", "round_trip")).strip()
    if trip_type == "round_trip":
        min_days = int(alert.get("min_days", 1) or 1)
        return f"min_days:{min_days}"
    return "n/a"


def load_observations() -> List[Dict[str, Any]]:
    if not OBSERVATIONS_PATH.exists():
        return []
    try:
        raw = json.loads(OBSERVATIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []

    normalized = []
    changed = False
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = _normalize_observation(item)
        if row != item:
            changed = True
        normalized.append(row)

    if changed:
        save_observations(normalized)
    return normalized


def save_observations(items: List[Dict[str, Any]]) -> None:
    clean = [_normalize_observation(item) for item in items]
    _atomic_write_json(OBSERVATIONS_PATH, clean)


def prune_old_observations(items: List[Dict[str, Any]], lookback_days: int) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, lookback_days))
    kept: List[Dict[str, Any]] = []
    for item in items:
        observed_at = _parse_iso(str(item.get("observed_at", "")))
        if observed_at and observed_at >= cutoff:
            kept.append(item)
    return kept


def record_observation(alert: Dict[str, Any], deal: Dict[str, Any], lookback_days: int) -> None:
    observations = load_observations()
    observations = prune_old_observations(observations, lookback_days)

    entry = {
        "observed_at": _iso_utc_now(),
        "origin_airport_code": alert.get("origin_airport_code", ""),
        "destination_airport_code": deal.get("destination", ""),
        "trip_type": alert.get("trip_type", "round_trip"),
        "depart_window": _build_depart_window(alert),
        "return_window": _build_return_window(alert),
        "price": float(deal.get("total_price", 0) or 0),
    }
    observations.append(_normalize_observation(entry))
    save_observations(observations)


def record_observations(alert: Dict[str, Any], deals: List[Dict[str, Any]], lookback_days: int) -> None:
    observations = load_observations()
    observations = prune_old_observations(observations, lookback_days)

    for deal in deals:
        entry = {
            "observed_at": _iso_utc_now(),
            "origin_airport_code": alert.get("origin_airport_code", ""),
            "destination_airport_code": deal.get("destination", ""),
            "trip_type": alert.get("trip_type", "round_trip"),
            "depart_window": _build_depart_window(alert),
            "return_window": _build_return_window(alert),
            "price": float(deal.get("total_price", 0) or 0),
        }
        observations.append(_normalize_observation(entry))

    save_observations(observations)


def calculate_baseline_price(
    *,
    observations: List[Dict[str, Any]],
    origin_airport_code: str,
    destination_airport_code: str,
    trip_type: str,
    depart_window: str,
    return_window: str,
    lookback_days: int,
    min_observations: int,
) -> float | None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, lookback_days))

    filtered_prices: List[float] = []
    for row in observations:
        observed_at = _parse_iso(str(row.get("observed_at", "")))
        if not observed_at or observed_at < cutoff:
            continue

        if str(row.get("origin_airport_code", "")).upper() != origin_airport_code.upper():
            continue
        if str(row.get("destination_airport_code", "")).upper() != destination_airport_code.upper():
            continue
        if str(row.get("trip_type", "")).strip() != trip_type:
            continue
        if str(row.get("depart_window", "")).strip().lower() != depart_window.lower():
            continue
        if str(row.get("return_window", "")).strip().lower() != return_window.lower():
            continue

        try:
            price = float(row.get("price", 0) or 0)
        except (TypeError, ValueError):
            continue
        if price > 0:
            filtered_prices.append(price)

    if len(filtered_prices) < max(1, min_observations):
        return None

    return sum(filtered_prices) / len(filtered_prices)


def baseline_for_alert_destination(
    alert: Dict[str, Any],
    destination_airport_code: str,
    *,
    lookback_days: int,
    min_observations: int,
) -> float | None:
    observations = load_observations()
    return calculate_baseline_price(
        observations=observations,
        origin_airport_code=str(alert.get("origin_airport_code", "")),
        destination_airport_code=destination_airport_code,
        trip_type=str(alert.get("trip_type", "round_trip")),
        depart_window=_build_depart_window(alert),
        return_window=_build_return_window(alert),
        lookback_days=lookback_days,
        min_observations=min_observations,
    )
