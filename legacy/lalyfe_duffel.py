#!/usr/bin/env python3
"""
lalyfe_duffel.py

Improvements implemented (all 4 in one pass):
1) Consolidate emails: 1 email per (user × route × preference label), grouped by date
2) Deal ranking: price asc, then duration asc, then depart time asc
3) User preferences: load users.json (multi-user). Falls back to EMAIL_TO + in-file PREFERENCES if users.json missing.
4) Booking UX: one Duffel Links button per date section + optional Google Flights link + copy/paste helper line
   (Note: Duffel Links does not deep-link to a specific offer; it opens a Duffel-hosted search/booking UI.)
"""

import os
import json
import uuid
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv


# Load .env located next to this script (reliable regardless of working directory)
SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=SCRIPT_DIR / ".env")


# -------------------------
# Config (env)
# -------------------------
APP_NAME = os.getenv("APP_NAME", "lalyfe").strip()

DUFFEL_TOKEN = (os.getenv("DUFFEL_TOKEN") or os.getenv("DUFFEL_ACCESS_TOKEN") or "").strip()
DUFFEL_BASE_URL = os.getenv("DUFFEL_BASE_URL", "https://api.duffel.com").strip().rstrip("/")
DUFFEL_VERSION = os.getenv("DUFFEL_VERSION", "v2").strip()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()          # must match a verified Sender Identity in SendGrid
EMAIL_TO = os.getenv("EMAIL_TO", "").strip()              # comma-separated ok: "a@x.com,b@y.com"
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", EMAIL_FROM).strip()

DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "USD").strip()
MAX_RESULTS_PER_SEARCH = int(os.getenv("MAX_RESULTS_PER_SEARCH", "10").strip())
DELAY_BETWEEN_REQUESTS_SEC = float(os.getenv("DELAY_BETWEEN_REQUESTS_SEC", "1.2").strip())
MIN_DAYS_FROM_TODAY = int(os.getenv("MIN_DAYS_FROM_TODAY", "7").strip())

# Placeholder URLs (replace later with your real domain)
PUBLIC_SUCCESS_URL = os.getenv("PUBLIC_SUCCESS_URL", "https://example.com/success").strip()
PUBLIC_FAILURE_URL = os.getenv("PUBLIC_FAILURE_URL", "https://example.com/failure").strip()
PUBLIC_ABANDON_URL = os.getenv("PUBLIC_ABANDON_URL", "https://example.com/abandon").strip()

# Optional branding for Duffel Links (safe placeholders)
LOGO_URL = os.getenv("LALYFE_LOGO_URL", "").strip()
PRIMARY_COLOR = os.getenv("LALYFE_PRIMARY_COLOR", "#111111").strip()
SECONDARY_COLOR = os.getenv("LALYFE_SECONDARY_COLOR", "#111111").strip()

# Optional: include Google Flights link in emails
INCLUDE_GOOGLE_FLIGHTS_LINK = os.getenv("INCLUDE_GOOGLE_FLIGHTS_LINK", "1").strip() not in ("0", "false", "False")


# -------------------------
# Default Preferences (fallback if users.json not present)
# -------------------------
PREFERENCES = [
    {
        "label": "SFO to Paris",
        "origins": ["SFO"],
        "destinations": ["CDG"],
        "max_price_per_traveler": 1200.0,
        "currency": "USD",
        "start_date": "2026-02-01",
        "days_ahead": 14,
        "adults": 1,
        "cabin_class": "economy",
        "max_dates_to_check": 3,
    },
    {
        "label": "SFO to Bangkok",
        "origins": ["SFO"],
        "destinations": ["BKK"],
        "max_price_per_traveler": 1500.0,
        "currency": "USD",
        "start_date": "2026-02-01",
        "days_ahead": 14,
        "adults": 1,
        "cabin_class": "economy",
        "max_dates_to_check": 3,
    },
]


# -------------------------
# Types
# -------------------------
@dataclass
class Deal:
    origin: str
    destination: str
    carrier: str
    flight_number: str
    price: float
    currency: str
    departing_at: str
    arriving_at: str
    offer_id: str
    duration_minutes: int


# -------------------------
# Formatting helpers
# -------------------------
def pretty_date(iso_yyyy_mm_dd: str) -> str:
    # 02 Feb 2026
    return datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d").strftime("%d %b %Y")


def _parse_iso_dt(dt_str: str) -> Optional[datetime]:
    if not dt_str:
        return None
    # Handles "2026-02-01T10:15:00" and with offsets "2026-02-01T10:15:00+00:00"
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def pretty_dt(dt_str: str) -> str:
    # 02 Feb 2026 10:15
    dt = _parse_iso_dt(dt_str)
    if not dt:
        return dt_str or ""
    return dt.strftime("%d %b %Y %H:%M")


def minutes_between(start_iso: str, end_iso: str) -> int:
    a = _parse_iso_dt(start_iso)
    b = _parse_iso_dt(end_iso)
    if not a or not b:
        return 10**9
    delta = b - a
    return max(0, int(delta.total_seconds() // 60))


def fmt_duration(mins: int) -> str:
    if mins >= 10**8:
        return ""
    h = mins // 60
    m = mins % 60
    if h <= 0:
        return f"{m}m"
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


def google_flights_link(origin: str, destination: str, depart_date_iso: str) -> str:
    # Simple, reliable query URL
    q = f"Flights from {origin} to {destination} on {depart_date_iso} one-way"
    return f"https://www.google.com/travel/flights?q={quote_plus(q)}"


# -------------------------
# Duffel helpers
# -------------------------
def _duffel_headers():
    return {
        "Authorization": f"Bearer {DUFFEL_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Duffel-Version": DUFFEL_VERSION,
    }


def _require_env():
    missing = []
    if not DUFFEL_TOKEN:
        missing.append("DUFFEL_TOKEN")
    if not SENDGRID_API_KEY:
        missing.append("SENDGRID_API_KEY")
    if not EMAIL_FROM:
        missing.append("EMAIL_FROM")
    if not EMAIL_TO and not (SCRIPT_DIR / "users.json").exists():
        # If users.json exists, EMAIL_TO can be empty because per-user emails come from the file.
        missing.append("EMAIL_TO (or create users.json)")
    if missing:
        raise RuntimeError(f"Missing required env var(s): {', '.join(missing)}")


def candidate_dates(start_date_yyyy_mm_dd: str, days_ahead: int, limit: int, min_days_from_today: int = 7):
    """
    Returns up to `limit` dates starting from max(start_date, today+min_days_from_today).
    Avoids Duffel rejecting dates that are too early (422 invalid_date).
    """
    today = datetime.now(timezone.utc).date()
    min_date = today + timedelta(days=min_days_from_today)

    start = datetime.strptime(start_date_yyyy_mm_dd, "%Y-%m-%d").date()
    base = max(start, min_date)

    out = []
    for i in range(max(0, days_ahead + 1)):
        out.append((base + timedelta(days=i)).isoformat())
        if len(out) >= limit:
            break
    return out


def create_offer_request(origin: str, destination: str, departure_date: str, adults: int = 1, cabin_class: str = "economy"):
    """
    POST /air/offer_requests
    """
    url = f"{DUFFEL_BASE_URL}/air/offer_requests"
    payload = {
        "data": {
            "slices": [{"origin": origin, "destination": destination, "departure_date": departure_date}],
            "passengers": [{"type": "adult"} for _ in range(adults)],
            "cabin_class": cabin_class,
        }
    }
    resp = requests.post(url, headers=_duffel_headers(), data=json.dumps(payload), timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Duffel offer_request error {resp.status_code}: {resp.text}")
    return resp.json()["data"]


def search_offers(origin: str, destination: str, departure_date: str, adults: int = 1, cabin_class: str = "economy", max_results: int = 10):
    """
    Returns offers from one Offer Request.
    """
    data = create_offer_request(origin, destination, departure_date, adults=adults, cabin_class=cabin_class)
    offers = data.get("offers", []) or []
    return offers[:max_results]


def parse_money(total_amount, total_currency):
    if total_amount is None:
        return None, None
    try:
        amt = float(total_amount)
    except Exception:
        amt = None
    cur = total_currency or ""
    return amt, cur


def offer_to_deal(offer: Dict[str, Any]) -> Optional[Deal]:
    total_amount, total_currency = parse_money(offer.get("total_amount"), offer.get("total_currency"))
    if total_amount is None:
        return None

    slices = offer.get("slices", []) or []
    first_slice = slices[0] if slices else {}

    segs = first_slice.get("segments", []) or []
    carrier = (segs[0].get("marketing_carrier", {}) or {}).get("iata_code", "") if segs else ""
    flight_num = segs[0].get("marketing_carrier_flight_number", "") if segs else ""

    depart = first_slice.get("departing_at", "")
    arrive = first_slice.get("arriving_at", "")
    origin = (first_slice.get("origin") or {}).get("iata_code", "")
    dest = (first_slice.get("destination") or {}).get("iata_code", "")

    offer_id = offer.get("id", "")
    dur = minutes_between(depart, arrive)

    return Deal(
        origin=origin,
        destination=dest,
        carrier=carrier,
        flight_number=flight_num,
        price=float(total_amount),
        currency=total_currency,
        departing_at=depart,
        arriving_at=arrive,
        offer_id=offer_id,
        duration_minutes=dur,
    )


# -------------------------
# Duffel Links
# -------------------------
def create_links_session(reference: str, traveller_currency: str = "USD"):
    """
    POST /links/sessions
    """
    url = f"{DUFFEL_BASE_URL}/links/sessions"
    data = {
        "reference": reference,
        "success_url": PUBLIC_SUCCESS_URL,
        "failure_url": PUBLIC_FAILURE_URL,
        "abandonment_url": PUBLIC_ABANDON_URL,
        "traveller_currency": traveller_currency,
        "should_hide_traveller_currency_selector": True,
        "primary_color": PRIMARY_COLOR,
        "secondary_color": SECONDARY_COLOR,
        "flights": {"enabled": True},
        "stays": {"enabled": False},
    }
    if LOGO_URL:
        data["logo_url"] = LOGO_URL

    resp = requests.post(url, headers=_duffel_headers(), data=json.dumps({"data": data}), timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Duffel Links error {resp.status_code}: {resp.text}")
    return resp.json()["data"]["url"]


# -------------------------
# SendGrid (email)
# -------------------------
def send_email_sendgrid(to_emails: List[str], subject: str, text_body: str, html_body: str):
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"}
    tos = [{"email": e} for e in to_emails]

    payload = {
        "personalizations": [{"to": tos}],
        "from": {"email": EMAIL_FROM, "name": APP_NAME},
        "reply_to": {"email": EMAIL_REPLY_TO},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_body},
            {"type": "text/html", "value": html_body},
        ],
        "tracking_settings": {
            "click_tracking": {"enable": False, "enable_text": False},
            "open_tracking": {"enable": True},
        },
        "categories": [APP_NAME],
        "headers": {"X-Entity-Ref-ID": str(uuid.uuid4())},
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"SendGrid error {resp.status_code}: {resp.text}")


# -------------------------
# users.json
# -------------------------
def load_users() -> List[Dict[str, Any]]:
    """
    users.json format (in same folder as this script):
    [
      {
        "email": "anne@example.com",
        "preferences": [ { ... same shape as PREFERENCES items ... } ]
      },
      ...
    ]
    """
    p = SCRIPT_DIR / "users.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    # fallback: one "user" with EMAIL_TO recipients and default PREFERENCES
    to_list = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]
    return [{"email": ",".join(to_list), "preferences": PREFERENCES}]


def normalize_pref(pref: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(pref)
    out.setdefault("currency", DEFAULT_CURRENCY)
    out.setdefault("days_ahead", 14)
    out.setdefault("adults", 1)
    out.setdefault("cabin_class", "economy")
    out.setdefault("max_dates_to_check", 3)
    return out


def parse_user_emails(user_email_field: str) -> List[str]:
    # allow one user object to include multiple recipients in a comma-separated field
    return [e.strip() for e in (user_email_field or "").split(",") if e.strip()]


# -------------------------
# Email building (consolidated + grouped by date)
# -------------------------
def rank_deals(deals: List[Deal]) -> List[Deal]:
    def depart_key(d: Deal):
        dt = _parse_iso_dt(d.departing_at)
        return dt.timestamp() if dt else 10**18

    return sorted(
        deals,
        key=lambda d: (
            d.price,
            d.duration_minutes,
            depart_key(d),
            d.carrier,
            d.flight_number,
        ),
    )


def build_consolidated_email(
    label: str,
    origin: str,
    destination: str,
    grouped: Dict[str, List[Deal]],  # date_iso -> deals
    currency: str,
    max_price_per_traveler: float,
    links_cache: Dict[Tuple[str, str, str], str],
) -> Tuple[str, str, str]:
    # Subject uses human-friendly date if only one date, otherwise "N dates"
    dates = sorted(grouped.keys())
    if len(dates) == 1:
        subj = f"[{APP_NAME}] Deals: {origin}→{destination} ({pretty_date(dates[0])})"
    else:
        subj = f"[{APP_NAME}] Deals: {origin}→{destination} ({len(dates)} dates)"

    header_txt = [
        f"{label}",
        f"Route: {origin} → {destination}",
        f"Max price per traveler: {max_price_per_traveler:g} {currency}",
        "",
        "Deals grouped by date:",
        "",
    ]

    header_html = [
        f"<h2>{label}</h2>",
        f"<p><b>Route:</b> {origin} → {destination}<br/>"
        f"<b>Max price per traveler:</b> {max_price_per_traveler:g} {currency}</p>",
        "<hr/>",
    ]

    txt_parts = header_txt[:]
    html_parts = header_html[:]

    for date_iso in dates:
        nice_date = pretty_date(date_iso)

        # One Duffel Links session per (origin,dest,date) section
        key = (origin, destination, date_iso)
        if key not in links_cache:
            ref = f"{APP_NAME}|{origin}-{destination}|{date_iso}"
            links_cache[key] = create_links_session(reference=ref, traveller_currency=currency)
            # tiny pace to avoid burst if many sessions
            time.sleep(max(0.2, min(1.0, DELAY_BETWEEN_REQUESTS_SEC)))

        duffel_link = links_cache[key]
        gf_link = google_flights_link(origin, destination, date_iso) if INCLUDE_GOOGLE_FLIGHTS_LINK else ""

        deals_sorted = rank_deals(grouped[date_iso])

        txt_parts.append(f"=== {nice_date} ===")
        txt_parts.append(f"Open booking/search (Duffel): {duffel_link}")
        if gf_link:
            txt_parts.append(f"Search on Google Flights: {gf_link}")
        txt_parts.append("")

        html_parts.append(f"<h3>✈️ {nice_date}</h3>")
        html_parts.append(
            f"<p>"
            f"<a href='{duffel_link}' style='display:inline-block;padding:10px 14px;background:#111;color:#fff;"
            f"text-decoration:none;border-radius:8px;'>Open booking/search</a>"
            f"</p>"
        )
        if gf_link:
            html_parts.append(f"<p><a href='{gf_link}'>Search on Google Flights</a></p>")

        html_parts.append("<ul>")

        for d in deals_sorted:
            # Copy/paste helper (great for internal testing)
            helper = f"{origin}→{destination} | {date_iso} | {d.price:g} {d.currency} | {pretty_dt(d.departing_at)}"

            txt_parts.append(
                f"- {d.carrier}{d.flight_number} | {d.price:g} {d.currency} | "
                f"{pretty_dt(d.departing_at)} → {pretty_dt(d.arriving_at)} | {fmt_duration(d.duration_minutes)}"
            )
            txt_parts.append(f"  Copy/paste: {helper}")
            txt_parts.append(f"  offer_id: {d.offer_id}")
            txt_parts.append("")

            html_parts.append(
                "<li>"
                f"<div><b>{d.carrier}{d.flight_number}</b> — <b>{d.price:g} {d.currency}</b>"
                f" <span style='color:#666'>({fmt_duration(d.duration_minutes)})</span></div>"
                f"<div>{pretty_dt(d.departing_at)} → {pretty_dt(d.arriving_at)}</div>"
                f"<div style='color:#666;font-size:12px'>Copy/paste: {helper}</div>"
                f"<div style='color:#666;font-size:12px'>offer_id: {d.offer_id}</div>"
                "</li><br/>"
            )

        html_parts.append("</ul>")
        html_parts.append("<hr/>")

    html_parts.append(
        "<p style='color:#666;font-size:12px'>"
        "Note: Duffel Links opens a Duffel-hosted search & booking page. "
        "Duffel Links sessions do not deep-link directly into a specific offer."
        "</p>"
    )

    return subj, "\n".join(txt_parts), "\n".join(html_parts)


# -------------------------
# Main
# -------------------------
def main():
    _require_env()

    print(f"DEBUG DUFFEL_TOKEN loaded: {bool(DUFFEL_TOKEN)}")
    print(f"===== {APP_NAME} (Duffel) Started =====\n")

    users = load_users()
    all_emails_sent = 0

    # Cache offer searches across all users to reduce calls:
    # (origin,dest,date,adults,cabin,max_results) -> list[Deal]
    offer_cache: Dict[Tuple[str, str, str, int, str, int], List[Deal]] = {}

    # Cache Duffel Links sessions (origin,dest,date) -> url
    links_cache: Dict[Tuple[str, str, str], str] = {}

    for user in users:
        user_emails = parse_user_emails(user.get("email", ""))
        if not user_emails:
            continue

        prefs = [normalize_pref(p) for p in (user.get("preferences") or PREFERENCES)]

        print(f"--- User: {', '.join(user_emails)} ---")

        # For each preference, consolidate emails by (origin,dest)
        for pref in prefs:
            label = pref.get("label", "Deals")
            max_price_per_traveler = float(pref.get("max_price_per_traveler", 999999))
            currency = pref.get("currency", DEFAULT_CURRENCY)
            adults = int(pref.get("adults", 1))
            cabin = pref.get("cabin_class", "economy")
            start_date = pref.get("start_date", datetime.now(timezone.utc).date().isoformat())
            days_ahead = int(pref.get("days_ahead", 14))
            max_dates_to_check = int(pref.get("max_dates_to_check", 3))

            dates = candidate_dates(start_date, days_ahead, max_dates_to_check, min_days_from_today=MIN_DAYS_FROM_TODAY)

            # accumulator: (origin,dest) -> date_iso -> deals
            grouped_by_route: Dict[Tuple[str, str], Dict[str, List[Deal]]] = {}

            print(f"=== Checking: {label} ===")

            for origin in pref.get("origins", []):
                for dest in pref.get("destinations", []):
                    for depart_date in dates:
                        print(
                            f"Searching {origin} → {dest}, max ${max_price_per_traveler:g} per traveler, date {depart_date}"
                        )

                        cache_key = (origin, dest, depart_date, adults, cabin, MAX_RESULTS_PER_SEARCH)
                        if cache_key in offer_cache:
                            deals_all = offer_cache[cache_key]
                        else:
                            try:
                                offers = search_offers(
                                    origin, dest, depart_date,
                                    adults=adults,
                                    cabin_class=cabin,
                                    max_results=MAX_RESULTS_PER_SEARCH
                                )
                                # pace Duffel calls
                                if DELAY_BETWEEN_REQUESTS_SEC > 0:
                                    time.sleep(DELAY_BETWEEN_REQUESTS_SEC)
                            except Exception as e:
                                print(f"  Error searching offers: {e}")
                                continue

                            deals_all = []
                            for offer in offers:
                                d = offer_to_deal(offer)
                                if not d:
                                    continue
                                deals_all.append(d)

                            offer_cache[cache_key] = deals_all

                        # Filter for this user's pref (currency + price)
                        deals_matching: List[Deal] = []
                        for d in deals_all:
                            if d.currency and d.currency != currency:
                                continue
                            if (d.price / max(1, adults)) <= max_price_per_traveler:
                                deals_matching.append(d)

                        if not deals_matching:
                            print("  No matching deals.\n")
                            continue

                        route_key = (origin, dest)
                        grouped_by_route.setdefault(route_key, {})
                        grouped_by_route[route_key].setdefault(depart_date, [])
                        grouped_by_route[route_key][depart_date].extend(deals_matching)

            # Send consolidated emails per route (one email per (origin,dest) for this preference)
            for (origin, dest), grouped_dates in grouped_by_route.items():
                # De-dup offers (same offer might appear multiple times in edge cases)
                for date_iso, deals_list in grouped_dates.items():
                    uniq = {}
                    for d in deals_list:
                        uniq[d.offer_id] = d
                    grouped_dates[date_iso] = list(uniq.values())

                subject, text_body, html_body = build_consolidated_email(
                    label=label,
                    origin=origin,
                    destination=dest,
                    grouped=grouped_dates,
                    currency=currency,
                    max_price_per_traveler=max_price_per_traveler,
                    links_cache=links_cache,
                )

                try:
                    send_email_sendgrid(user_emails, subject, text_body, html_body)
                    all_emails_sent += 1
                    print(f"  ✅ Email sent: {subject}\n")
                except Exception as e:
                    print(f"  ❌ Failed to send email: {e}\n")

        print("")

    print(f"===== {APP_NAME} (Duffel) Finished | emails_sent={all_emails_sent} =====")


if __name__ == "__main__":
    main()
