#!/usr/bin/env python3
"""Email composition and sending helpers for Jetzi."""

from __future__ import annotations

import json
import os
import uuid
from typing import List, Tuple

import requests


APP_NAME = os.getenv("APP_NAME", "Jetzi").strip()
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", EMAIL_FROM).strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5001").strip().rstrip("/")


def build_unsubscribe_url(unsubscribe_token: str) -> str:
    return f"{APP_BASE_URL}/unsubscribe/{unsubscribe_token}"


def compose_alert_email(
    *,
    to_email: str,
    subject: str,
    intro: str,
    lines: List[str],
    unsubscribe_token: str,
) -> Tuple[str, str, str]:
    unsubscribe_url = build_unsubscribe_url(unsubscribe_token)
    text_lines = [intro, "", *lines, "", f"Unsubscribe: {unsubscribe_url}"]

    list_html = "".join(f"<li>{line}</li>" for line in lines)
    html = (
        f"<p>{intro}</p>"
        f"<ul>{list_html}</ul>"
        f"<p style='font-size:12px;color:#666'>"
        f"To stop these emails, <a href='{unsubscribe_url}'>unsubscribe</a>."
        f"</p>"
    )
    return subject, "\n".join(text_lines), html


def send_email_sendgrid(to_emails: List[str], subject: str, text_body: str, html_body: str) -> None:
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY is required to send email")
    if not EMAIL_FROM:
        raise RuntimeError("EMAIL_FROM is required to send email")

    headers = {"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "personalizations": [{"to": [{"email": e} for e in to_emails]}],
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

    response = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers=headers,
        data=json.dumps(payload),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"SendGrid error {response.status_code}: {response.text}")


def send_test_email() -> None:
    target = os.getenv("EMAIL_TO", "").strip()
    if not target:
        raise RuntimeError("EMAIL_TO is required for test email")

    subject, text_body, html_body = compose_alert_email(
        to_email=target,
        subject=f"[{APP_NAME}] Test email",
        intro="Jetzi email configuration is working.",
        lines=["This is a test email."],
        unsubscribe_token="test-token",
    )
    send_email_sendgrid([target], subject, text_body, html_body)


if __name__ == "__main__":
    send_test_email()
