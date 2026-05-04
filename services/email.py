#!/usr/bin/env python3
"""Email composition and sending helpers for Jetzi."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import List, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Jetzi").strip()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
FROM_EMAIL = os.getenv("FROM_EMAIL", "").strip()
REPLY_TO_EMAIL = os.getenv("REPLY_TO_EMAIL", FROM_EMAIL).strip()
EMAIL_TO = os.getenv("EMAIL_TO", "").strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5001").strip().rstrip("/")

LOW_SPAM_FOOTER = (
    "Jetzi sends alerts only when a deal looks worth booking. Unsubscribe anytime."
)

EMAIL_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"

AIRLINE_NAMES = {
    "AA": "American",
    "AS": "Alaska",
    "B6": "JetBlue",
    "DL": "Delta",
    "F9": "Frontier",
    "NK": "Spirit",
    "UA": "United",
    "WN": "Southwest",
}


def build_unsubscribe_url(unsubscribe_token: str) -> str:
    return f"{APP_BASE_URL}/unsubscribe/{unsubscribe_token}"

def build_manage_alert_url(unsubscribe_token: str) -> str:
    return f"{APP_BASE_URL}/alerts/manage/{unsubscribe_token}"

def _load_email_template(name: str) -> str:
    template_path = EMAIL_TEMPLATES_DIR / name
    if not template_path.exists():
        raise RuntimeError(f"Missing email template: {template_path}")
    return template_path.read_text(encoding="utf-8")


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _format_money(amount: float | int | None, currency: str = "USD", decimals: int = 0) -> str:
    if amount is None:
        return "-"
    try:
        numeric = float(amount)
    except (TypeError, ValueError):
        return "-"

    if currency.upper() == "USD":
        if decimals == 0:
            return f"${numeric:,.0f}"
        return f"${numeric:,.{decimals}f}"
    if decimals == 0:
        return f"{currency.upper()} {numeric:,.0f}"
    return f"{currency.upper()} {numeric:,.{decimals}f}"


def _extract_booking_url(deal: dict) -> str:
    candidates = [
        "booking_url",
        "book_url",
        "deeplink",
        "deep_link",
        "url",
    ]
    for key in candidates:
        value = str(deal.get(key, "") or "").strip()
        if value.startswith("http://") or value.startswith("https://"):
            return value
    return ""


def _airline_display(carrier: str, flight_number: str) -> str:
    carrier = (carrier or "").strip().upper()
    flight_number = (flight_number or "").strip()

    airline_name = AIRLINE_NAMES.get(carrier, carrier)
    if airline_name and flight_number:
        return f"{airline_name} · Flight {flight_number}"
    return airline_name


def compose_alert_email(
    *,
    to_email: str,
    subject: str,
    intro: str,
    lines: List[str],
    unsubscribe_token: str,
) -> Tuple[str, str, str]:
    del to_email
    unsubscribe_url = build_unsubscribe_url(unsubscribe_token)

    text_lines = [
        intro,
        "",
        *lines,
        "",
        LOW_SPAM_FOOTER,
        f"Unsubscribe: {unsubscribe_url}",
    ]

    list_html = "".join(f"<li>{_escape(line)}</li>" for line in lines)
    html_body = f"""
    <html>
      <body style="margin:0;padding:0;background:#f5f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
        <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
          <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:20px;padding:28px;">
            <p style="margin:0 0 16px 0;font-size:16px;line-height:1.6;">{_escape(intro)}</p>
            <ul style="margin:0 0 20px 18px;padding:0;font-size:16px;line-height:1.7;color:#0f172a;">
              {list_html}
            </ul>
            <p style="margin:24px 0 8px 0;font-size:12px;line-height:1.6;color:#64748b;">{_escape(LOW_SPAM_FOOTER)}</p>
            <p style="margin:0;font-size:12px;line-height:1.6;color:#64748b;">
              To stop these emails, <a href="{_escape(unsubscribe_url)}" style="color:#4f46e5;text-decoration:none;">unsubscribe</a>.
            </p>
          </div>
        </div>
      </body>
    </html>
    """
    return subject, "\n".join(text_lines), html_body


def compose_deal_alert_email(
    *,
    to_email: str,
    alert: dict,
    deal: dict,
    baseline_price: float | None,
    percent_drop: int | None,
    reasons: List[str],
    confidence_line: str,
    unsubscribe_token: str,
) -> Tuple[str, str, str]:
    del to_email

    origin = str(deal.get("origin", "") or "").upper()
    destination = str(deal.get("destination", "") or "").upper()
    currency = str(deal.get("currency", "USD") or "USD").upper()

    adults = int(alert.get("adults", 1) or 1)
    total_price = float(deal.get("total_price", 0) or 0)
    per_traveler_price = total_price / max(1, adults)

    rounded_total_price = round(total_price)
    rounded_per_traveler_price = round(per_traveler_price)

    baseline_total = float(baseline_price) if baseline_price is not None else None
    baseline_per_traveler = (
        baseline_total / max(1, adults) if baseline_total is not None else None
    )

    booking_url = _extract_booking_url(deal)
    unsubscribe_url = build_unsubscribe_url(unsubscribe_token)

    depart_at = str(deal.get("departing_at", "") or "").strip()
    arriving_at = str(deal.get("arriving_at", "") or "").strip()
    carrier = str(deal.get("carrier", "") or "").strip()
    flight_number = str(deal.get("flight_number", "") or "").strip()
    airline_display = _airline_display(carrier, flight_number)

    traveler_label = "traveler" if adults == 1 else "travelers"

    subject = f"{origin} → {destination} for {_format_money(rounded_per_traveler_price, currency)} per traveler ✈️"

    text_lines: List[str] = [
        f"{origin} → {destination} for {_format_money(rounded_per_traveler_price, currency)} per traveler",
        confidence_line,
        "Book soon — deals like this usually don’t last.",
        "",
        "Price snapshot",
        (
            f"- Typical price: {_format_money(round(baseline_per_traveler), currency)} per traveler"
            if baseline_per_traveler is not None
            else "- Typical price: -"
        ),
        (
            f"- Current price: {_format_money(rounded_per_traveler_price, currency)} per traveler "
            f"for {adults} {traveler_label} ({_format_money(rounded_total_price, currency)} total)"
        ),
    ]

    if percent_drop is not None:
        text_lines.append(f"- Price drop: {percent_drop}%")

    if depart_at:
        text_lines.append(f"- Departure: {depart_at}")
    if arriving_at:
        text_lines.append(f"- Arrival: {arriving_at}")
    if airline_display:
        text_lines.append(f"- Airline: {airline_display}")

    text_lines.extend([
        "",
        "Why you're getting this alert",
        *[f"- {reason}" for reason in reasons],
    ])

    if booking_url:
        text_lines.extend([
            "",
            f"Search on Google Flights: {booking_url}",
        ])

    text_lines.extend([
        "",
        "You’re receiving this because Jetzi is watching flights based on your preferences and only flags deals that look worth booking.",
        "",
        LOW_SPAM_FOOTER,
        f"Unsubscribe: {unsubscribe_url}",
    ])

    reasons_html = "".join(
        f"<li style='margin:0 0 8px 0;'>{_escape(reason)}</li>" for reason in reasons
    )

    cta_html = ""
    if booking_url:
        cta_html = f"""
        <div style="text-align:center;margin:28px 0 8px 0;">
          <a href="{_escape(booking_url)}"
             target="_blank"
             style="display:inline-block;background:#4f46e5;color:#ffffff;text-decoration:none;
                    padding:14px 22px;border-radius:12px;font-size:16px;font-weight:700;">
            Search on Google Flights →
          </a>
        </div>
        """

    detail_rows = []
    if depart_at:
        detail_rows.append(
            f"<div style='margin:0 0 8px 0;'><strong>Departure:</strong> {_escape(depart_at)}</div>"
        )
    if arriving_at:
        detail_rows.append(
            f"<div style='margin:0 0 8px 0;'><strong>Arrival:</strong> {_escape(arriving_at)}</div>"
        )
    if airline_display:
        detail_rows.append(
            f"<div style='margin:0 0 8px 0;'><strong>Airline:</strong> {_escape(airline_display)}</div>"
        )

    details_html = "".join(detail_rows)

    percent_drop_html = ""
    if percent_drop is not None:
        percent_drop_html = f"""
          <div style="margin:0 0 10px 0;font-size:16px;color:#0f172a;">
            <strong>Price drop:</strong> {_escape(percent_drop)}%
          </div>
        """

    typical_html = (
        f"{_escape(_format_money(round(baseline_per_traveler), currency))} per traveler"
        if baseline_per_traveler is not None
        else "-"
    )

    current_html = (
        f"{_escape(_format_money(rounded_per_traveler_price, currency))} per traveler "
        f"for {_escape(adults)} {_escape(traveler_label)} "
        f"({_escape(_format_money(rounded_total_price, currency))} total)"
    )

    html_body = f"""
    <html>
      <body style="margin:0;padding:0;background:#f5f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
        <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
          <div style="padding:0 4px 20px 4px;">
            <div style="font-size:13px;font-weight:700;color:#4f46e5;letter-spacing:0.02em;text-transform:uppercase;">
              Jetzi
            </div>
            <h1 style="margin:8px 0 10px 0;font-size:34px;line-height:1.1;font-weight:800;color:#0f172a;">
              {_escape(origin)} → {_escape(destination)} for {_escape(_format_money(rounded_per_traveler_price, currency))} per traveler
            </h1>
            <p style="margin:0;font-size:18px;line-height:1.6;color:#334155;">
              {_escape(confidence_line)}
            </p>
            <p style="margin:8px 0 0 0;font-size:15px;line-height:1.6;color:#64748b;">
              Book soon — deals like this usually don’t last.
            </p>
          </div>

          <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:20px;padding:24px;">
            <div style="margin:0 0 18px 0;font-size:14px;font-weight:700;color:#64748b;letter-spacing:0.04em;text-transform:uppercase;">
              Price snapshot
            </div>

            <div style="background:#f8fafc;border:1px solid #e5e7eb;border-radius:16px;padding:18px 18px 8px 18px;margin-bottom:24px;">
              <div style="margin:0 0 10px 0;font-size:16px;color:#0f172a;">
                <strong>Typical price:</strong> {typical_html}
              </div>
              <div style="margin:0 0 10px 0;font-size:16px;color:#0f172a;">
                <strong>Current price:</strong> {current_html}
              </div>
              {percent_drop_html}
            </div>

            {details_html}

            <h2 style="margin:24px 0 12px 0;font-size:18px;line-height:1.3;font-weight:800;color:#0f172a;">
              Why you're getting this alert
            </h2>
            <ul style="margin:0 0 8px 18px;padding:0;font-size:16px;line-height:1.7;color:#0f172a;">
              {reasons_html}
            </ul>

            {cta_html}

            <p style="margin:20px 0 0 0;font-size:14px;line-height:1.7;color:#475569;">
              You’re receiving this because Jetzi is watching flights based on your preferences and only flags deals that look worth booking.
            </p>

            <div style="margin-top:28px;padding-top:18px;border-top:1px solid #e5e7eb;">
              <p style="margin:0 0 8px 0;font-size:12px;line-height:1.6;color:#64748b;">
                {_escape(LOW_SPAM_FOOTER)}
              </p>

              <p style="margin:0;font-size:12px;line-height:1.6;color:#64748b;">
                To stop these emails, <a href="{_escape(unsubscribe_url)}" style="color:#4f46e5;text-decoration:none;">unsubscribe</a>.
              </p>
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    return subject, "\n".join(text_lines), html_body


def compose_no_deal_checkin_email(
    *,
    to_email: str,
    alert: dict,
    unsubscribe_token: str,
) -> Tuple[str, str, str]:
    del to_email

    origin = str(alert.get("origin_airport_code", "")).upper()
    destinations = ", ".join(alert.get("destination_airport_codes", []) or [])
    days = alert.get("available_departure_days", [])

    if days and len(days) < 7:
        days_label = ", ".join(day.capitalize() for day in days)
        flexibility = f"({days_label})"
    else:
        flexibility = "(flexible dates)"

    if len(destinations.split(",")) == 1:
        subject = f"No deals this week: {origin} → {destinations.strip()} {flexibility}"
    else:
        subject = f"No deals this week: {origin} → multiple destinations {flexibility}"

    unsubscribe_url = build_unsubscribe_url(unsubscribe_token)
    manage_url = build_manage_alert_url(unsubscribe_token)

    text = "\n".join(
        [
            f"No deals found this week for {origin} → {destinations}.",
            f"Travel flexibility: {flexibility}",
            "",
            "We're still monitoring and will notify you when something worth booking appears.",
            "",
            LOW_SPAM_FOOTER,
            f"Unsubscribe: {unsubscribe_url}",
        ]
    )

    html_template = _load_email_template("no_deal_checkin.html")

    html_body = html_template.format(
        origin=origin,
        destinations=destinations,
        flexibility=flexibility,
        low_spam_footer=LOW_SPAM_FOOTER,
        unsubscribe_url=unsubscribe_url,
        manage_url=manage_url,
    )
    
    return subject, text, html_body


def send_email_resend(to_emails: List[str], subject: str, text_body: str, html_body: str) -> None:
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is required")
    if not FROM_EMAIL:
        raise RuntimeError("FROM_EMAIL is required")
    if not to_emails:
        raise RuntimeError("At least one recipient is required")

    payload = {
        "from": f"Jetzi Alerts <{FROM_EMAIL}>",
        "to": to_emails,
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }
    if REPLY_TO_EMAIL:
        payload["reply_to"] = REPLY_TO_EMAIL

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"Resend error {response.status_code}: {response.text}")


def send_test_email() -> None:
    target = EMAIL_TO
    if not target:
        raise RuntimeError("EMAIL_TO is required")

    subject, text_body, html_body = compose_alert_email(
        to_email=target,
        subject="Jetzi test email ✈️",
        intro="Your Jetzi email setup is working.",
        lines=["This is a test email."],
        unsubscribe_token="test-token",
    )
    send_email_resend([target], subject, text_body, html_body)


def compose_verification_email(
    *,
    email: str,
    origin: str,
    destination: str,
    budget: str,
    verify_url: str,
) -> Tuple[str, str, str]:

    subject = f"Verify your Jetzi alert ✈️"

    text = f"""
Confirm your email to activate your Jetzi alert.

Route: {origin} → {destination}
Budget: {budget}

Verify your email:
{verify_url}

Jetzi sends alerts only when a deal is worth booking.
"""

    html = f"""
    <html>
      <body style="margin:0;padding:0;background:#f5f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
        <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
          
          <div style="font-size:13px;font-weight:700;color:#4f46e5;letter-spacing:0.02em;text-transform:uppercase;margin-bottom:12px;">
            Jetzi
          </div>

          <h1 style="margin:0 0 16px;font-size:28px;font-weight:800;">
            Confirm your email ✈️
          </h1>

          <p style="font-size:16px;margin-bottom:16px;">
            Activate your alert to start receiving great deals.
          </p>

          <ul style="margin:0 0 24px 18px;font-size:16px;">
            <li><strong>Route:</strong> {origin} → {destination}</li>
            <li><strong>Budget:</strong> {budget}</li>
          </ul>

          <!-- BUTTON -->
          <div style="margin:24px 0;">
            <a href="{verify_url}" 
               style="display:inline-block;background:#4f46e5;color:#ffffff;
                      padding:14px 22px;border-radius:10px;
                      text-decoration:none;font-weight:600;font-size:16px;">
              Verify email
            </a>
          </div>

          <p style="font-size:13px;color:#64748b;">
            If the button doesn’t work, use this link:
          </p>

          <p style="font-size:13px;color:#64748b;word-break:break-all;">
            {verify_url}
          </p>

        </div>
      </body>
    </html>
    """

    return subject, text, html


if __name__ == "__main__":
    send_test_email()