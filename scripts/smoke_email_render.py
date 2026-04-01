#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import email as email_service


if __name__ == "__main__":
    subject, text, html = email_service.compose_deal_alert_email(
        to_email="demo@example.com",
        alert={"alert_id": "demo-alert"},
        deal={
            "origin": "SFO",
            "destination": "LAX",
            "departing_at": "2026-03-01T09:00:00Z",
            "total_price": 180.0,
            "currency": "USD",
        },
        baseline_price=240.0,
        percent_drop=25,
        reasons=[
            "Matches your max price",
            "Matches your trip window and traveler settings",
            "Significant short-term fare drop",
        ],
        confidence_line="This is lower than what we've seen recently.",
        unsubscribe_token="demo-token",
    )

    assert subject
    assert "Why you're getting this alert" in html
    assert "Normal price" in html
    assert "Unsubscribe" in html
    assert text
    print("smoke_email_render: ok")
