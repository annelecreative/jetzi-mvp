#!/usr/bin/env python3
"""Flight/airport service helpers for Jetzi."""

from __future__ import annotations

import difflib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

from services import duffel
from services import search_cache

BASE_DIR = Path(__file__).resolve().parent.parent

# Keep airport data in the repo, not on the persistent disk.
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

AIRPORT_SEARCH_ALIASES = {
    "hawaii": ["HNL", "OGG", "KOA", "LIH"],
    "maui": ["OGG"],
    "oahu": ["HNL"],
    "honolulu": ["HNL"],
    "kauai": ["LIH"],
    "big island": ["KOA", "ITO"],

    "spain": ["MAD", "BCN", "AGP", "PMI", "SVQ", "VLC"],
    "italy": ["FCO", "MXP", "VCE", "NAP", "FLR"],
    "france": ["CDG", "ORY", "NCE", "LYS"],
    "japan": ["HND", "NRT", "KIX", "ITM", "CTS", "FUK"],
    "thailand": ["BKK", "DMK", "HKT", "CNX"],
    "bali": ["DPS"],
    "greece": ["ATH", "JTR", "HER", "SKG"],
    "portugal": ["LIS", "OPO", "FAO"],
    "mexico": ["MEX", "CUN", "GDL", "PVR", "SJD"],

    "nyc": ["JFK", "LGA", "EWR"],
    "new york city": ["JFK", "LGA", "EWR"],
    "bay area": ["SFO", "OAK", "SJC"],
    "sf bay area": ["SFO", "OAK", "SJC"],
    "la": ["LAX", "BUR", "LGB", "SNA"],
    "los angeles area": ["LAX", "BUR", "LGB", "SNA"],
    "dc": ["DCA", "IAD", "BWI"],
    "washington dc": ["DCA", "IAD", "BWI"],
}

# MVP tuning:
# Slightly relax the user's max price filter so we do not over-filter too early.
MVP_PRICE_FLEX_MULTIPLIER = 1.3

# Candidate-date defaults for MVP.
DEFAULT_START_DAYS_FROM_TODAY = 7
DEFAULT_DAYS_AHEAD = 7
DEFAULT_MAX_DATES_TO_CHECK = 3


def load_airports() -> List[Dict[str, str]]:
    if not AIRPORTS_PATH.exists():
        raise FileNotFoundError(
            f"Required airport seed file is missing: {AIRPORTS_PATH}. "
            "Keep airports_min.json in the repo under data/ and do not mount your persistent disk over /data."
        )

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


COUNTRY_SEARCH_ALIASES = {
    "spain": {
        "label": "🇪🇸 Spain",
        "subtitle": "Country — searches Madrid, Barcelona, Málaga",
        "country": "Spain",
        "codes": ["MAD", "BCN", "AGP"],
    },
    "france": {
        "label": "🇫🇷 France",
        "subtitle": "Country — searches Paris, Nice, Lyon",
        "country": "France",
        "codes": ["CDG", "ORY", "NCE"],
    },
    "italy": {
        "label": "🇮🇹 Italy",
        "subtitle": "Country — searches Rome, Milan, Venice",
        "country": "Italy",
        "codes": ["FCO", "MXP", "VCE"],
    },
    "japan": {
        "label": "🇯🇵 Japan",
        "subtitle": "Country — searches Tokyo, Osaka",
        "country": "Japan",
        "codes": ["HND", "NRT", "KIX"],
    },
    "thailand": {
        "label": "🇹🇭 Thailand",
        "subtitle": "Country — searches Bangkok, Phuket, Chiang Mai",
        "country": "Thailand",
        "codes": ["BKK", "HKT", "CNX"],
    },
    "mexico": {
        "label": "🇲🇽 Mexico",
        "subtitle": "Country — searches Mexico City, Cancun, Guadalajara",
        "country": "Mexico",
        "codes": ["MEX", "CUN", "GDL"],
    },
    "greece": {
        "label": "🇬🇷 Greece",
        "subtitle": "Country — searches Athens, Santorini, Heraklion",
        "country": "Greece",
        "codes": ["ATH", "JTR", "HER"],
    },
    "portugal": {
        "label": "🇵🇹 Portugal",
        "subtitle": "Country — searches Lisbon, Porto, Faro",
        "country": "Portugal",
        "codes": ["LIS", "OPO", "FAO"],
    },
}

CITY_SEARCH_ALIASES = {
    "paris": {
        "label": "🇫🇷 Paris, France",
        "subtitle": "All airports — CDG, ORY",
        "city": "Paris",
        "country": "France",
        "codes": ["CDG", "ORY"],
    },
    "new york": {
        "label": "🇺🇸 New York City",
        "subtitle": "All airports — JFK, LGA, EWR",
        "city": "New York",
        "country": "United States",
        "codes": ["JFK", "LGA", "EWR"],
    },
    "nyc": {
        "label": "🇺🇸 New York City",
        "subtitle": "All airports — JFK, LGA, EWR",
        "city": "New York",
        "country": "United States",
        "codes": ["JFK", "LGA", "EWR"],
    },
    "london": {
        "label": "🇬🇧 London, United Kingdom",
        "subtitle": "All airports — LHR, LGW, STN",
        "city": "London",
        "country": "United Kingdom",
        "codes": ["LHR", "LGW", "STN"],
    },
    "tokyo": {
        "label": "🇯🇵 Tokyo, Japan",
        "subtitle": "All airports — HND, NRT",
        "city": "Tokyo",
        "country": "Japan",
        "codes": ["HND", "NRT"],
    },
    "san francisco": {
        "label": "🇺🇸 San Francisco Bay Area",
        "subtitle": "All airports — SFO, OAK, SJC",
        "city": "San Francisco",
        "country": "United States",
        "codes": ["SFO", "OAK", "SJC"],
    },
    "bay area": {
        "label": "🇺🇸 San Francisco Bay Area",
        "subtitle": "All airports — SFO, OAK, SJC",
        "city": "San Francisco",
        "country": "United States",
        "codes": ["SFO", "OAK", "SJC"],
    },
    "los angeles": {
        "label": "🇺🇸 Los Angeles Area",
        "subtitle": "All airports — LAX, BUR, LGB",
        "city": "Los Angeles",
        "country": "United States",
        "codes": ["LAX", "BUR", "LGB"],
    },
    "la": {
        "label": "🇺🇸 Los Angeles Area",
        "subtitle": "All airports — LAX, BUR, LGB",
        "city": "Los Angeles",
        "country": "United States",
        "codes": ["LAX", "BUR", "LGB"],
    },
}


def _airport_result(airport: Dict[str, str]) -> Dict[str, Any]:
    code = str(airport.get("code", "")).upper().strip()
    city = str(airport.get("city", "")).strip()
    name = str(airport.get("name", "")).strip()
    country = str(airport.get("country", "")).strip()

    return {
        "type": "airport",
        "code": code,
        "codes": [code] if code else [],
        "name": name,
        "city": city,
        "country": country,
        "label": f"✈️ {city} ({code})",
        "subtitle": name,
    }


def _city_result(data: Dict[str, Any], airports_by_code_lookup: Dict[str, Dict[str, str]]) -> Dict[str, Any] | None:
    available_codes = [
        code
        for code in data.get("codes", [])
        if code.lower() in airports_by_code_lookup
    ]

    if not available_codes:
        return None

    return {
        "type": "city",
        "code": available_codes[0],
        "codes": available_codes,
        "name": data.get("label", ""),
        "city": data.get("city", ""),
        "country": data.get("country", ""),
        "label": data.get("label", ""),
        "subtitle": data.get("subtitle", "All airports"),
    }


def _country_result(data: Dict[str, Any], airports_by_code_lookup: Dict[str, Dict[str, str]]) -> Dict[str, Any] | None:
    available_codes = [
        code
        for code in data.get("codes", [])
        if code.lower() in airports_by_code_lookup
    ]

    if not available_codes:
        return None

    return {
        "type": "country",
        "code": available_codes[0],
        "codes": available_codes,
        "name": data.get("label", ""),
        "city": "",
        "country": data.get("country", ""),
        "label": data.get("label", ""),
        "subtitle": data.get("subtitle", "Country"),
    }


def rank_airports(
    query: str,
    airports: List[Dict[str, str]],
    *,
    mode: str = "destination",
) -> List[Dict[str, Any]]:
    q = _norm(query)
    if not q:
        return []

    airports_by_code_lookup = {
        _norm(airport["code"]): airport for airport in airports
    }

    combined: List[Dict[str, Any]] = []
    seen_keys = set()

    def add_result(item: Dict[str, Any] | None) -> None:
        if not item:
            return

        key = (
            item.get("type", "airport"),
            item.get("label") or item.get("code"),
            ",".join(item.get("codes", [])),
        )

        if key in seen_keys:
            return

        seen_keys.add(key)
        combined.append(item)

    # Destination mode can show country-level choices like Spain/Japan.
    # Origin mode stays stricter because the backend needs one clean departure airport.
    if mode == "destination":
        for alias, data in COUNTRY_SEARCH_ALIASES.items():
            if alias.startswith(q) or q in alias:
                add_result(_country_result(data, airports_by_code_lookup))

    # City groupings are useful for both origin and destination.
    for alias, data in CITY_SEARCH_ALIASES.items():
        if alias.startswith(q) or q in alias:
            add_result(_city_result(data, airports_by_code_lookup))

    alias_codes = AIRPORT_SEARCH_ALIASES.get(q, [])
    for code in alias_codes:
        airport = airports_by_code_lookup.get(code.lower())
        if airport:
            add_result(_airport_result(airport))

    ranked: List[Tuple[Tuple[float, str], Dict[str, str]]] = []

    for airport in airports:
        code = _norm(airport["code"])
        city = _norm(airport["city"])
        name = _norm(airport["name"])
        country = _norm(airport["country"])

        score = None

        if code == q:
            score = 0.0
        elif city == q:
            score = 0.5
        elif code.startswith(q):
            score = 1.0
        elif city.startswith(q):
            score = 2.0
        elif name.startswith(q):
            score = 3.0
        elif q in city:
            score = 4.0
        elif q in name:
            score = 5.0
        elif q in country:
            score = 6.0
        else:
            ratio = _fuzzy_score(q, airport)
            if ratio >= 0.72:
                score = 7.0 - ratio

        if score is not None:
            ranked.append(((score, code), airport))

    ranked.sort(key=lambda pair: pair[0])

    for _, airport in ranked:
        add_result(_airport_result(airport))

    return combined[:8]


def is_trip_within_allowed_weekdays(
    depart_date: date,
    return_date: date,
    allowed_weekdays_set: set[str],
) -> bool:
    if not allowed_weekdays_set:
        return True

    if return_date < depart_date:
        return False

    cursor = depart_date
    while cursor <= return_date:
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][cursor.weekday()]
        if weekday not in allowed_weekdays_set:
            return False
        cursor += timedelta(days=1)
    return True


def _date_from_iso_datetime(value: str) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    if len(raw) >= 10:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _candidate_outbound_dates(alert: Dict[str, Any]) -> List[str]:
    outbound_dates = alert.get("outbound_dates")
    if isinstance(outbound_dates, list):
        cleaned = [str(item).strip() for item in outbound_dates if str(item).strip()]
        if cleaned:
            return cleaned

    start_days_from_today = max(
        1, int(alert.get("start_days_from_today", DEFAULT_START_DAYS_FROM_TODAY) or DEFAULT_START_DAYS_FROM_TODAY)
    )
    days_ahead = max(0, int(alert.get("days_ahead", DEFAULT_DAYS_AHEAD) or DEFAULT_DAYS_AHEAD))
    max_dates = max(
        1,
        int(alert.get("max_dates_to_check", DEFAULT_MAX_DATES_TO_CHECK) or DEFAULT_MAX_DATES_TO_CHECK),
    )

    base = date.today() + timedelta(days=start_days_from_today)

    dates: List[str] = []
    for idx in range(days_ahead + 1):
        dates.append((base + timedelta(days=idx)).isoformat())
        if len(dates) >= max_dates:
            break
    return dates


def matches_price_per_traveler(
    total_itinerary_price: float, adults: int, max_price_per_traveler: float
) -> bool:
    if adults < 1:
        return False
    if max_price_per_traveler <= 0:
        return True

    flexible_max = max_price_per_traveler * MVP_PRICE_FLEX_MULTIPLIER
    return (total_itinerary_price / adults) <= flexible_max


def _build_google_flights_url(
    *,
    origin: str,
    destination: str,
    departure_date: str = "",
    return_date: str = "",
) -> str:
    origin = (origin or "").upper().strip()
    destination = (destination or "").upper().strip()
    departure_date = (departure_date or "").strip()
    return_date = (return_date or "").strip()

    if not origin or not destination:
        return ""

    if departure_date and return_date:
        query = f"Flights from {origin} to {destination} on {departure_date} through {return_date}"
    elif departure_date:
        query = f"Flights from {origin} to {destination} on {departure_date}"
    else:
        query = f"Flights from {origin} to {destination}"

    return f"https://www.google.com/travel/flights?q={quote(query)}"


def _ensure_booking_url(
    deal: Dict[str, Any],
    *,
    return_date: str = "",
) -> Dict[str, Any]:
    existing = str(deal.get("booking_url", "") or "").strip()
    if existing.startswith("http://") or existing.startswith("https://"):
        return deal

    departing_at = str(deal.get("departing_at", "") or "").strip()
    departure_date = departing_at[:10] if departing_at else ""

    booking_url = _build_google_flights_url(
        origin=str(deal.get("origin", "") or ""),
        destination=str(deal.get("destination", "") or ""),
        departure_date=departure_date,
        return_date=return_date,
    )

    enriched = dict(deal)
    enriched["booking_url"] = booking_url
    return enriched


def filter_matching_deals(alert: Dict[str, Any], deals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    adults = int(alert.get("adults", 1) or 1)
    max_price = float(alert.get("max_price_per_traveler", 0) or 0)
    selected_days = set(alert.get("available_departure_days") or [])
    trip_type = str(alert.get("trip_type", "round_trip"))
    min_days = max(1, int(alert.get("min_days", 1) or 1))

    matching: List[Dict[str, Any]] = []
    for deal in deals:
        total_price = float(deal.get("total_price", 0) or 0)

        if not matches_price_per_traveler(total_price, adults, max_price):
            continue

        depart_date = _date_from_iso_datetime(str(deal.get("departing_at", "")))
        if depart_date:
            if trip_type == "round_trip":
                return_date = depart_date + timedelta(days=min_days)
            else:
                return_date = depart_date

            if not is_trip_within_allowed_weekdays(depart_date, return_date, selected_days):
                continue

        matching.append(deal)

    return matching


def _retrieve_shared_offers(alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    origin = str(alert.get("origin_airport_code", "")).upper()
    destinations = [str(item).upper() for item in (alert.get("destination_airport_codes") or [])]
    trip_type = str(alert.get("trip_type", "round_trip"))
    adults = int(alert.get("adults", 1) or 1)
    min_days = max(1, int(alert.get("min_days", 1) or 1))
    outbound_dates = _candidate_outbound_dates(alert)

    all_deals: List[Dict[str, Any]] = []

    error_count = 0
    live_duffel_calls = 0

    MAX_ERRORS = 2
    MAX_LIVE_DUFFEL_CALLS = 5

    for destination in destinations:
        for outbound_date in outbound_dates:
            if error_count >= MAX_ERRORS:
                print("Too many Duffel errors — stopping early")
                return all_deals

            return_date = ""
            if trip_type == "round_trip":
                outbound_dt = datetime.strptime(outbound_date, "%Y-%m-%d").date()
                return_date = (outbound_dt + timedelta(days=min_days)).isoformat()

            key = search_cache.build_key(
                origin,
                destination,
                outbound_date,
                return_date,
                adults,
                trip_type,
            )

            cached = search_cache.get(key)
            if cached is not None:
                print(f"Cache hit: {origin} → {destination} ({outbound_date})")
                deals = cached
            else:
                if live_duffel_calls >= MAX_LIVE_DUFFEL_CALLS:
                    print(
                        f"Live Duffel call budget reached "
                        f"({MAX_LIVE_DUFFEL_CALLS}) — stopping early"
                    )
                    return all_deals

                live_duffel_calls += 1
                print(
                    f"Cache miss: {origin} → {destination} ({outbound_date}) "
                    f"(calling Duffel {live_duffel_calls}/{MAX_LIVE_DUFFEL_CALLS})"
                )

                try:
                    if trip_type == "round_trip":
                        deals = duffel.fetch_round_trip_offers(
                            origin,
                            destination,
                            outbound_date,
                            return_date,
                            adults=adults,
                        )
                    else:
                        deals = duffel.fetch_one_way_offers(
                            origin,
                            destination,
                            outbound_date,
                            adults=adults,
                        )
                except Exception as e:
                    error_count += 1
                    print(f"Duffel error for {origin} → {destination} ({outbound_date}): {e}")
                    continue

                print(f"Raw offers from Duffel: {len(deals)}")
                search_cache.set(key, deals)

            deals = [_ensure_booking_url(deal, return_date=return_date) for deal in deals]
            all_deals.extend(deals)

    return all_deals


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
            candidate_deals = _retrieve_shared_offers(alert)

        if alert.get("only_send_matching_deals", True):
            processed[alert_id] = filter_matching_deals(alert, candidate_deals)
        else:
            processed[alert_id] = candidate_deals

    return processed


def retrieve_and_filter_offers(alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Pull candidate offers using shared-cache-backed Duffel requests,
    then apply Jetzi filtering rules:
    - available_departure_days trip-day filter (if dates are present)
    - slightly relaxed max price per traveler filter for MVP tuning
    """
    candidate_deals = _retrieve_shared_offers(alert)
    return filter_matching_deals(alert, candidate_deals)