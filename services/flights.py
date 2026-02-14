#!/usr/bin/env python3
"""Flight/airport service helpers for Jetzi."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from services import duffel

BASE_DIR = Path(__file__).resolve().parent.parent
AIRPORTS_PATH = BASE_DIR / "data" / "airports_min.json"
REQUIRED_AIRPORT_CODES = {
    "SJC",
    "SAN",
    "OAK",
    "SMF",
    "SNA",
    "BUR",
    "LGB",
    "SEA",
    "PDX",
    "PHX",
    "DEN",
    "ORD",
    "DFW",
    "IAH",
    "ATL",
    "MIA",
    "BOS",
    "JFK",
    "LGA",
    "EWR",
    "IAD",
    "DCA",
}
VALID_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def load_airports() -> List[Dict[str, str]]:
    raw = json.loads(AIRPORTS_PATH.read_text(encoding="utf-8"))
    airports: List[Dict[str, str]] = []
    for item in raw:
        airports.append(
            {
                "code": str(item.get("code", "")).upper().strip(),
                "name": str(item.get("name", "")).strip(),
                "city": str(item.get("city", "")).strip(),
                "country": str(item.get("country", "")).strip(),
            }
        )
    return airports


def assert_required_airports_present(airports: List[Dict[str, str]]) -> None:
    available_codes = {airport.get("code", "").upper().strip() for airport in airports}
    missing_codes = sorted(REQUIRED_AIRPORT_CODES - available_codes)
    if missing_codes:
        raise RuntimeError(
            f"airports_min.json is missing required airports: {', '.join(missing_codes)}"
        )


def airports_by_code(airports: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {airport["code"]: airport for airport in airports}


def airport_brief(code: str, by_code: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    airport = by_code.get((code or "").upper(), {})
    return {
        "code": (code or "").upper(),
        "city": airport.get("city", (code or "").upper()),
        "name": airport.get("name", ""),
        "country": airport.get("country", ""),
    }


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _fuzzy_score(query: str, airport: Dict[str, str]) -> float:
    fields = [
        _norm(airport["code"]),
        _norm(airport["city"]),
        _norm(airport["name"]),
        _norm(f"{airport['city']} {airport['name']}"),
    ]
    return max(difflib.SequenceMatcher(a=query, b=field).ratio() for field in fields)


def rank_airports(query: str, airports: List[Dict[str, str]]) -> List[Dict[str, str]]:
    q = _norm(query)
    ranked: List[Tuple[Tuple[float, str], Dict[str, str]]] = []

    for airport in airports:
        code = _norm(airport["code"])
        city = _norm(airport["city"])
        name = _norm(airport["name"])

        if code == q:
            ranked.append(((0.0, code), airport))
            continue

        if code.startswith(q):
            ranked.append(((1.0, code), airport))
            continue
        if city.startswith(q) or name.startswith(q):
            ranked.append(((2.0, code), airport))
            continue

        if q in city or q in name:
            ranked.append(((3.0, code), airport))
            continue

        ratio = _fuzzy_score(q, airport)
        if ratio >= 0.72:
            ranked.append(((4.0 - ratio, code), airport))

    ranked.sort(key=lambda pair: pair[0])
    return [item for _, item in ranked[:10]]


def matches_departure_weekday(
    available_departure_days: List[str], outbound_departure_weekday: str
) -> bool:
    if not available_departure_days:
        return True
    return outbound_departure_weekday.lower() in set(available_departure_days)


def matches_price_per_traveler(
    total_itinerary_price: float, adults: int, max_price_per_traveler: float
) -> bool:
    if adults < 1:
        return False
    return (total_itinerary_price / adults) <= max_price_per_traveler


def filter_matching_deals(alert: Dict[str, Any], deals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    adults = int(alert.get("adults", 1) or 1)
    max_price = float(alert.get("max_price_per_traveler", 0) or 0)
    selected_days = alert.get("available_departure_days") or []

    matching: List[Dict[str, Any]] = []
    for deal in deals:
        total_price = float(deal.get("total_price", 0) or 0)
        weekday = str(deal.get("outbound_weekday", "")).lower()

        if not matches_departure_weekday(selected_days, weekday):
            continue
        if not matches_price_per_traveler(total_price, adults, max_price):
            continue
        matching.append(deal)
    return matching


def process_active_alerts(
    alerts: List[Dict[str, Any]], deals_by_alert: Dict[str, List[Dict[str, Any]]] | None = None
) -> Dict[str, List[Dict[str, Any]]]:
    processed: Dict[str, List[Dict[str, Any]]] = {}
    deals_by_alert = deals_by_alert or {}
    for alert in alerts:
        if alert.get("status") != "active":
            continue

        alert_id = alert.get("alert_id", "")
        candidate_deals = deals_by_alert.get(alert_id)
        if candidate_deals is None:
            candidate_deals = duffel.search_offers(alert)
        if alert.get("only_send_matching_deals", True):
            processed[alert_id] = filter_matching_deals(alert, candidate_deals)
        else:
            processed[alert_id] = candidate_deals
    return processed


def retrieve_and_filter_offers(alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Pull candidate offers from Duffel and apply Jetzi filtering rules:
    - available_departure_days outbound filter (empty means any day)
    - max price per traveler filter: total_itinerary_price / adults <= max_price_per_traveler
    """
    candidate_deals = duffel.search_offers(alert)
    return filter_matching_deals(alert, candidate_deals)
