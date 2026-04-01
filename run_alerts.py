#!/usr/bin/env python3
"""Runner for Jetzi alert sending and weekly no-deal check-ins."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from services import alerts as alert_service
from services import duffel as duffel_service
from services import email as email_service
from services import flights as flight_service
from services import price_observations
from services import runtime_config


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _deal_reasons(
    *,
    alert: dict,
    deal: dict,
    baseline_price: float | None,
    percent_drop: int | None,
    significant_drop_pct: int,
) -> list[str]:
    reasons: list[str] = []

    adults = int(alert.get("adults", 1) or 1)
    max_price = float(alert.get("max_price_per_traveler", 0) or 0)
    current_total = float(deal.get("total_price", 0) or 0)
    per_traveler = current_total / max(1, adults)

    if max_price > 0:
        if per_traveler <= max_price:
            reasons.append(f"Within your target price of ${max_price:.0f} per traveler")
        elif per_traveler <= max_price * 1.3:
            reasons.append(f"Close to your target price of ${max_price:.0f} per traveler")

    if baseline_price is not None and current_total < baseline_price:
        diff = baseline_price - current_total
        reasons.append(f"About ${diff:.0f} lower than recent prices we've seen")

    if (
        baseline_price is not None
        and percent_drop is not None
        and percent_drop >= significant_drop_pct
    ):
        reasons.append(f"Strong fare drop: {percent_drop}% below recent baseline")

    reasons.append("Matches your trip window and traveler settings")

    return reasons[:3]


def _confidence_line(*, baseline_price: float | None, current_price: float) -> str:
    if baseline_price is None:
        return "This matches your alert settings and is worth a look."

    if current_price <= baseline_price * 0.85:
        return "This looks unusually good compared with recent prices."

    if current_price < baseline_price:
        return "This is lower than what we've seen recently."

    return "This matches your alert settings and price target."


def _deal_score(
    *,
    alert: dict,
    deal: dict,
    baseline_price: float | None,
    percent_drop: int | None,
    significant_drop_pct: int,
) -> int:
    score = 0

    adults = int(alert.get("adults", 1) or 1)
    max_price = float(alert.get("max_price_per_traveler", 0) or 0)
    total_price = float(deal.get("total_price", 0) or 0)
    per_traveler = total_price / max(1, adults)

    if max_price > 0:
        if per_traveler <= max_price:
            score += 5
        elif per_traveler <= max_price * 1.15:
            score += 2

    if baseline_price is not None and total_price < baseline_price:
        score += 3

    if percent_drop is not None:
        if percent_drop >= significant_drop_pct:
            score += 4
        elif percent_drop >= max(5, significant_drop_pct // 2):
            score += 2

    if total_price <= 250:
        score += 3
    elif total_price <= 400:
        score += 2
    elif total_price <= 600:
        score += 1

    return score


def _pick_best_deal(
    *,
    alert: dict,
    deals: list[dict],
    lookback_days: int,
    min_observations: int,
    significant_drop_pct: int,
) -> tuple[dict, float | None, int | None, int]:
    ranked: list[tuple[int, float, int, dict, float | None, int | None]] = []

    for idx, deal in enumerate(deals):
        baseline_price = price_observations.baseline_for_alert_destination(
            alert,
            str(deal.get("destination", "")),
            lookback_days=lookback_days,
            min_observations=min_observations,
        )

        current_price = float(deal.get("total_price", 0) or 0)
        percent_drop = None
        if baseline_price and baseline_price > 0:
            percent_drop = round(((baseline_price - current_price) / baseline_price) * 100)

        score = _deal_score(
            alert=alert,
            deal=deal,
            baseline_price=baseline_price,
            percent_drop=percent_drop,
            significant_drop_pct=significant_drop_pct,
        )

        ranked.append((score, -current_price, -idx, deal, baseline_price, percent_drop))

    ranked.sort(reverse=True)
    best_score, _, _, best_deal, baseline_price, percent_drop = ranked[0]
    return best_deal, baseline_price, percent_drop, best_score


def run_deal_alerts(dry_run: bool = False, limit: int | None = None) -> dict:
    if not duffel_service.DUFFEL_TOKEN:
        raise RuntimeError("DUFFEL_TOKEN is required for --mode deals")
    if not email_service.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is required for sending alerts")
    if not email_service.FROM_EMAIL:
        raise RuntimeError("FROM_EMAIL is required for sending alerts")

    lookback_days = runtime_config.baseline_lookback_days()
    min_observations = runtime_config.baseline_min_observations()
    significant_drop_pct = runtime_config.significant_drop_pct()
    dedupe_hours = runtime_config.dedupe_hours()

    alerts = alert_service.list_active_alerts()
    if limit is not None and limit > 0:
        alerts = alerts[:limit]

    sent = 0
    skipped_duplicate = 0
    matched_alerts = 0
    no_match_alerts = 0
    search_error_alerts = 0

    for alert in alerts:
        if not alert.get("is_active", True):
            continue

        if not alert.get("email"):
            continue

        try:
            print(f"Checking alert {alert.get('alert_id')} for {alert.get('email')}")
            deals = flight_service.retrieve_and_filter_offers(alert)
            print(f"Deals fetched: {len(deals)}")
        except Exception as e:
            print(f"Skipping alert {alert.get('alert_id')} due to search error: {e}")
            search_error_alerts += 1
            continue

        if deals:
            price_observations.record_observations(alert, deals, lookback_days)

        if not deals:
            print("No matching deals for this alert")
            no_match_alerts += 1
            continue

        matched_alerts += 1

        best_deal, baseline_price, percent_drop, best_score = _pick_best_deal(
            alert=alert,
            deals=deals,
            lookback_days=lookback_days,
            min_observations=min_observations,
            significant_drop_pct=significant_drop_pct,
        )

        if best_deal:
            print("DEBUG DEAL:", best_deal)

        signature = alert_service.build_deal_signature(best_deal)
        if alert_service.is_recent_duplicate(alert, signature, within_hours=dedupe_hours):
            skipped_duplicate += 1
            continue

        current_price = float(best_deal.get("total_price", 0) or 0)

        reasons = _deal_reasons(
            alert=alert,
            deal=best_deal,
            baseline_price=baseline_price,
            percent_drop=percent_drop,
            significant_drop_pct=significant_drop_pct,
        )
        confidence_line = _confidence_line(
            baseline_price=baseline_price,
            current_price=current_price,
        )

        subject, text_body, html_body = email_service.compose_deal_alert_email(
            to_email=str(alert.get("email")),
            alert=alert,
            deal=best_deal,
            baseline_price=baseline_price,
            percent_drop=percent_drop,
            reasons=reasons,
            confidence_line=confidence_line,
            unsubscribe_token=str(alert.get("unsubscribe_token", "")),
        )

        if dry_run:
            print(f"[DRY RUN] Would send deal email to {alert.get('email')}")
            print(f"[DRY RUN] Subject: {subject}")
            print(f"[DRY RUN] Score: {best_score}")
            print(f"[DRY RUN] Reasons: {reasons}")
            print(f"[DRY RUN] Confidence: {confidence_line}")
            print(f"[DRY RUN] booking_url: {best_deal.get('booking_url', '')}")
        else:
            email_service.send_email_resend([str(alert.get("email"))], subject, text_body, html_body)

            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            alert_service.update_alert_record(
                str(alert.get("alert_id")),
                {
                    "last_deal_sent_at": now_iso,
                    "last_deal_signature": signature,
                },
            )
            sent += 1

    return {
        "processed": len(alerts),
        "matched_alerts": matched_alerts,
        "no_match_alerts": no_match_alerts,
        "search_error_alerts": search_error_alerts,
        "sent": sent,
        "skipped_duplicate": skipped_duplicate,
    }


def run_no_deal_checkins(limit: int | None = None) -> dict:
    if not email_service.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is required for sending alerts")
    if not email_service.FROM_EMAIL:
        raise RuntimeError("FROM_EMAIL is required for sending alerts")

    checkin_days = runtime_config.no_deal_checkin_days()
    alerts = alert_service.list_active_alerts()
    if limit is not None and limit > 0:
        alerts = alerts[:limit]

    sent = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=checkin_days)

    for alert in alerts:
        if not alert.get("is_active", True):
            continue

        if not alert.get("email"):
            continue

        last_deal_sent_at = _parse_iso(str(alert.get("last_deal_sent_at") or ""))
        if last_deal_sent_at and last_deal_sent_at >= cutoff:
            continue

        last_no_deal_sent_at = _parse_iso(str(alert.get("last_no_deal_sent_at") or ""))
        if last_no_deal_sent_at and last_no_deal_sent_at >= cutoff:
            continue

        subject, text_body, html_body = email_service.compose_no_deal_checkin_email(
            to_email=str(alert.get("email")),
            unsubscribe_token=str(alert.get("unsubscribe_token", "")),
        )
        email_service.send_email_resend([str(alert.get("email"))], subject, text_body, html_body)

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        alert_service.update_alert_record(
            str(alert.get("alert_id")),
            {
                "last_no_deal_sent_at": now_iso,
            },
        )
        sent += 1

    return {"processed": len(alerts), "sent": sent}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Jetzi alert processing")
    parser.add_argument(
        "--mode",
        choices=["deals", "no-deals", "all"],
        default="all",
        help="Select which alert jobs to run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run deal alerts without sending emails",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit how many active alerts are processed in this run",
    )
    args = parser.parse_args()

    if args.mode in {"deals", "all"}:
        deal_result = run_deal_alerts(dry_run=args.dry_run, limit=args.limit)
        print(f"deal_alerts: {deal_result}")

    if args.mode in {"no-deals", "all"}:
        no_deal_result = run_no_deal_checkins(limit=args.limit)
        print(f"no_deal_checkins: {no_deal_result}")


if __name__ == "__main__":
    main()