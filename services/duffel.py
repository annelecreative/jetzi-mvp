#!/usr/bin/env python3
"""Duffel API integration for Jetzi flight offer retrieval."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import quote

import requests
from dotenv import load_dotenv


load_dotenv()

DUFFEL_TOKEN = (os.getenv("DUFFEL_API_KEY") or os.getenv("DUFFEL_TOKEN") or "").strip()
DUFFEL_BASE_URL = os.getenv("DUFFEL_BASE_URL", "https://api.duffel.com").strip().rstrip("/")
DUFFEL_VERSION = os.getenv("DUFFEL_VERSION", "v2").strip()
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "USD").strip()
MAX_RESULTS_PER_SEARCH = int(os.getenv("MAX_RESULTS_PER_SEARCH", "30").strip())
MIN_DAYS_FROM_TODAY = int(os.getenv("MIN_DAYS_FROM_TODAY", "7").strip())
DEFAULT_DAYS_AHEAD = int(os.getenv("SEARCH_DAYS_AHEAD", "7").strip())
DEFAULT_MAX_DATES = int(os.getenv("MAX_DATES_TO_CHECK", "3").strip())


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {DUFFEL_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Duffel-Version": DUFFEL_VERSION,
    }


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _outbound_weekday(iso_datetime: str) -> str:
    dt = _parse_iso_datetime(iso_datetime)
    if not dt:
        return ""
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][dt.weekday()]


def _candidate_dates(
    *,
    start_date: str | None = None,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
    limit: int = DEFAULT_MAX_DATES,
    min_days_from_today: int = MIN_DAYS_FROM_TODAY,
) -> List[str]:
    today = datetime.now(timezone.utc).date()
    min_date = today + timedelta(days=min_days_from_today)

    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            start = min_date
    else:
        start = min_date

    base = max(start, min_date)
    out: List[str] = []
    for idx in range(max(0, days_ahead + 1)):
        out.append((base + timedelta(days=idx)).isoformat())
        if len(out) >= limit:
            break
    return out


def _build_google_flights_url(
    *,
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
) -> str:
    if not origin or not destination or not departure_date:
        return ""

    if return_date:
        query = f"Flights from {origin} to {destination} on {departure_date} through {return_date}"
    else:
        query = f"Flights from {origin} to {destination} on {departure_date}"

    return f"https://www.google.com/travel/flights?q={quote(query)}"


def _post_offer_request(
    *,
    slices: List[Dict[str, str]],
    adults: int,
    cabin_class: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    if not DUFFEL_TOKEN:
        raise RuntimeError("DUFFEL_TOKEN is not configured")

    url = f"{DUFFEL_BASE_URL}/air/offer_requests"
    payload = {
        "data": {
            "slices": slices,
            "passengers": [{"type": "adult"} for _ in range(max(1, adults))],
            "cabin_class": cabin_class,
        }
    }

    response = requests.post(url, headers=_headers(), data=json.dumps(payload), timeout=(5, 8))
    if response.status_code >= 400:
        raise RuntimeError(f"Duffel offer_request error {response.status_code}: {response.text}")

    body = response.json().get("data", {})
    offers = body.get("offers", []) or []
    return offers[:max_results]


def _offer_to_deal(offer: Dict[str, Any], adults: int) -> Dict[str, Any] | None:
    total_amount = offer.get("total_amount")
    total_currency = offer.get("total_currency") or DEFAULT_CURRENCY

    try:
        total_price = float(total_amount)
    except (TypeError, ValueError):
        return None

    slices = offer.get("slices", []) or []
    first_slice = slices[0] if slices else {}
    segments = first_slice.get("segments", []) or []

    carrier = ""
    flight_number = ""
    if segments:
        carrier = (segments[0].get("marketing_carrier", {}) or {}).get("iata_code", "")
        flight_number = segments[0].get("marketing_carrier_flight_number", "")

    departing_at = first_slice.get("departing_at", "")
    arriving_at = first_slice.get("arriving_at", "")
    origin = (first_slice.get("origin") or {}).get("iata_code", "")
    destination = (first_slice.get("destination") or {}).get("iata_code", "")

    departure_date = departing_at[:10] if departing_at else ""
    return_date = ""
    if len(slices) > 1:
        second_slice = slices[1] or {}
        return_departing_at = str(second_slice.get("departing_at", "") or "")
        return_date = return_departing_at[:10] if return_departing_at else ""

    booking_url = _build_google_flights_url(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
    )

    return {
        "offer_id": offer.get("id", ""),
        "origin": origin,
        "destination": destination,
        "carrier": carrier,
        "flight_number": flight_number,
        "departing_at": departing_at,
        "arriving_at": arriving_at,
        "outbound_weekday": _outbound_weekday(departing_at),
        "total_price": total_price,
        "price_per_traveler": total_price / max(1, adults),
        "currency": total_currency,
        "booking_url": booking_url,
    }


def fetch_round_trip_offers(
    origin: str,
    destination: str,
    outbound_date: str,
    return_date: str,
    *,
    adults: int = 1,
    cabin_class: str = "economy",
    max_results: int = MAX_RESULTS_PER_SEARCH,
) -> List[Dict[str, Any]]:
    slices = [
        {"origin": origin, "destination": destination, "departure_date": outbound_date},
        {"origin": destination, "destination": origin, "departure_date": return_date},
    ]
    offers = _post_offer_request(
        slices=slices,
        adults=adults,
        cabin_class=cabin_class,
        max_results=max_results,
    )
    deals = [_offer_to_deal(offer, adults) for offer in offers]
    return [deal for deal in deals if deal]


def fetch_one_way_offers(
    origin: str,
    destination: str,
    departure_date: str,
    *,
    adults: int = 1,
    cabin_class: str = "economy",
    max_results: int = MAX_RESULTS_PER_SEARCH,
) -> List[Dict[str, Any]]:
    slices = [{"origin": origin, "destination": destination, "departure_date": departure_date}]
    offers = _post_offer_request(
        slices=slices,
        adults=adults,
        cabin_class=cabin_class,
        max_results=max_results,
    )
    deals = [_offer_to_deal(offer, adults) for offer in offers]
    return [deal for deal in deals if deal]


def search_offers(alert_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Search offers for a canonical alert dict and return normalized deals."""
    origin = alert_dict.get("origin_airport_code", "")
    destinations = alert_dict.get("destination_airport_codes", []) or []
    trip_type = alert_dict.get("trip_type", "round_trip")
    adults = int(alert_dict.get("adults", 1) or 1)
    cabin_class = str(alert_dict.get("cabin_class", "economy") or "economy")
    max_results = int(alert_dict.get("max_results", MAX_RESULTS_PER_SEARCH) or MAX_RESULTS_PER_SEARCH)

    outbound_dates = alert_dict.get("outbound_dates")
    if not isinstance(outbound_dates, list) or not outbound_dates:
        outbound_dates = _candidate_dates(
            start_date=alert_dict.get("start_date"),
            days_ahead=int(alert_dict.get("days_ahead", DEFAULT_DAYS_AHEAD) or DEFAULT_DAYS_AHEAD),
            limit=int(alert_dict.get("max_dates_to_check", DEFAULT_MAX_DATES) or DEFAULT_MAX_DATES),
        )

    all_deals: List[Dict[str, Any]] = []
    for destination in destinations:
        for outbound_date in outbound_dates:
            if trip_type == "round_trip":
                min_days = int(alert_dict.get("min_days", 1) or 1)
                return_date = (
                    datetime.strptime(outbound_date, "%Y-%m-%d").date() + timedelta(days=max(1, min_days))
                ).isoformat()
                deals = fetch_round_trip_offers(
                    origin,
                    destination,
                    outbound_date,
                    return_date,
                    adults=adults,
                    cabin_class=cabin_class,
                    max_results=max_results,
                )
            else:
                deals = fetch_one_way_offers(
                    origin,
                    destination,
                    outbound_date,
                    adults=adults,
                    cabin_class=cabin_class,
                    max_results=max_results,
                )
            all_deals.extend(deals)

    return all_deals