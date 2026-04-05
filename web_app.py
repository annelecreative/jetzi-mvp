#!/usr/bin/env python3

import os
from flask import request

import os
from urllib.parse import urlsplit

import config as app_config
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

from services import alerts as alert_service
from services import flights as flight_service
from services import users as user_service

from dotenv import load_dotenv
load_dotenv()



AIRPORTS = flight_service.load_airports()
flight_service.assert_required_airports_present(AIRPORTS)
AIRPORTS_BY_CODE = flight_service.airports_by_code(AIRPORTS)

# Normalize old records (adds status/email/unsubscribe_token defaults).
alert_service.load_alert_records()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv(
    "FLASK_SECRET_KEY", getattr(app_config, "FLASK_SECRET_KEY", "dev-only-change-me")
)
ALERT_SESSION_KEY = "last_alert"
REFERRED_BY_CODE_SESSION_KEY = "referred_by_code"
USER_EMAIL_SESSION_KEY = "user_email"
DEV_TRUSTED_HOSTS = (
    "localhost",
    "localhost:5000",
    "127.0.0.1",
    "127.0.0.1:5000",
    "::1",
    "[::1]",
    "[::1]:5000",
)


def _is_production_mode() -> bool:
    env_candidates = (
        os.getenv("APP_ENV", ""),
        os.getenv("JETZI_ENV", ""),
        os.getenv("FLASK_ENV", ""),
    )
    return any(candidate.strip().lower() == "production" for candidate in env_candidates)


def _hosts_from_value(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [host.strip() for host in value.split(",") if host.strip()]
    return [str(host).strip() for host in value if str(host).strip()]


def _configured_trusted_hosts() -> list[str]:
    cfg_hosts = _hosts_from_value(getattr(app_config, "TRUSTED_HOSTS", None))
    env_hosts = _hosts_from_value(os.getenv("TRUSTED_HOSTS", ""))
    return sorted({*cfg_hosts, *env_hosts})


def _effective_trusted_hosts() -> list[str]:
    configured = _configured_trusted_hosts()
    if _is_production_mode():
        return configured
    return sorted({*configured, *DEV_TRUSTED_HOSTS})


def _configure_trusted_hosts() -> list[str]:
    trusted_hosts = _effective_trusted_hosts()
    app.config["JETZI_TRUSTED_HOSTS"] = trusted_hosts
    return trusted_hosts


def _host_variants(host: str) -> set[str]:
    normalized = (host or "").strip()
    if not normalized:
        return set()

    variants = {normalized}
    if normalized.startswith("["):
        closing_bracket = normalized.find("]")
        if closing_bracket != -1:
            ipv6_host = normalized[1:closing_bracket]
            variants.add(ipv6_host)
            variants.add(f"[{ipv6_host}]")
        return variants

    if normalized.count(":") == 1:
        host_without_port, _ = normalized.rsplit(":", 1)
        variants.add(host_without_port)
        return variants

    if normalized.count(":") > 1:
        variants.add(f"[{normalized}]")
    return variants


def _is_request_host_trusted(host: str, trusted_hosts: set[str]) -> bool:
    return any(variant in trusted_hosts for variant in _host_variants(host))


def _configured_app_base_url() -> str:
    raw_env = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if raw_env:
        return raw_env
    raw_cfg = str(getattr(app_config, "APP_BASE_URL", "") or "").strip().rstrip("/")
    return raw_cfg


def _build_referral_copy_url(referral_code: str) -> str:
    code = (referral_code or "").strip()
    if not code:
        return ""

    referral_path = url_for("referral_landing", code=code)
    app_base_url = _configured_app_base_url()
    if app_base_url:
        parsed = urlsplit(app_base_url)
        if parsed.scheme and parsed.netloc:
            return f"{app_base_url}{referral_path}"
    return f"{request.host_url.rstrip('/')}{referral_path}"


TRUSTED_HOSTS = set(_configure_trusted_hosts())


@app.before_request
def enforce_trusted_hosts():
    if not TRUSTED_HOSTS:
        return None

    host = request.host or ""
    if _is_request_host_trusted(host, TRUSTED_HOSTS):
        return None

    app.logger.warning(
        "Blocked host %s not in trusted hosts %s",
        host,
        sorted(TRUSTED_HOSTS),
    )
    abort(403)


@app.get("/")
def index():
    if request.args.get("fresh") == "1":
        session.pop(ALERT_SESSION_KEY, None)
    referred_code = request.args.get("referred", "").strip()
    user_email = session.get(USER_EMAIL_SESSION_KEY)
    allowed_destinations = user_service.allowed_destinations_for_email(user_email)
    can_invite_from_create_page = False
    destination_helper_tip = (
        "Invite friends to unlock more destinations."
        if can_invite_from_create_page
        else "More destinations coming later (subscription + referrals)."
    )
    initial_alert = session.get(ALERT_SESSION_KEY) if request.args.get("restore") == "1" else None
    return render_template(
        "index.html",
        initial_alert=initial_alert,
        allowed_destinations=allowed_destinations,
        destination_helper_tip=destination_helper_tip,
        can_invite_from_create_page=can_invite_from_create_page,
        server_error=None,
        referred_code=referred_code,
    )


@app.get("/alert-created")
def alert_created():
    alert = session.get(ALERT_SESSION_KEY)
    if not alert:
        return redirect(url_for("index"))
    user_email = alert.get("email") or session.get(USER_EMAIL_SESSION_KEY, "")
    user = user_service.find_user_by_email(user_email)
    referral_code = user.get("referral_code", "") if user else ""
    referral_copy_url = _build_referral_copy_url(referral_code)

    return render_template(
        "success.html",
        alert=alert,
        summary=alert_service.build_alert_summary(alert),
        email_error=None,
        email_value=alert.get("email", "") or "",
        referral_code=referral_code,
        referral_copy_url=referral_copy_url,
    )


@app.get("/alerts/activated")
def alerts_activated():
    alert = session.get(ALERT_SESSION_KEY)
    if not alert or alert.get("status") != "active":
        return redirect(url_for("index"))
    user = user_service.find_user_by_email(alert.get("email", ""))
    referral_code = user.get("referral_code", "") if user else ""
    referral_copy_url = _build_referral_copy_url(referral_code)
    allowed_destinations = user_service.allowed_destinations_for_email(alert.get("email"))
    return render_template(
        "activated.html",
        alert=alert,
        referral_code=referral_code,
        referral_copy_url=referral_copy_url,
        allowed_destinations=allowed_destinations,
        bonus_slots=max(0, allowed_destinations - 1),
    )


@app.get("/r/<code>")
def referral_landing(code: str):
    app.logger.info("Referral hit: %s", code)
    if user_service.find_user_by_referral_code(code):
        session[REFERRED_BY_CODE_SESSION_KEY] = code
    return redirect(url_for("index", referred=code))


@app.get("/unsubscribe/<token>")
def unsubscribe(token: str):
    alert = alert_service.unsubscribe_alert(token)
    return render_template("unsubscribe.html", unsubscribed=bool(alert), alert=alert)


@app.get("/api/airports/search")
def search_airports():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify({"error": "Query must be at least 2 characters", "items": []}), 400

    items = flight_service.rank_airports(query, AIRPORTS)
    return jsonify({"items": items})


@app.post("/alerts/create")
def create_alert():
    app.logger.info("POST /alerts/create hit")
    user_email = session.get(USER_EMAIL_SESSION_KEY)
    allowed_destinations = user_service.allowed_destinations_for_email(user_email)
    app.logger.info(
        "create_alert request context: user_email=%s destination_limit=%s",
        user_email,
        allowed_destinations,
    )
    alert, error = alert_service.validate_and_build_alert(
        request.form,
        AIRPORTS_BY_CODE,
        max_destinations=allowed_destinations,
    )
    if error:
        app.logger.info("create_alert validation failed: %s", error)
        return (
            render_template(
                "index.html",
                initial_alert=session.get(ALERT_SESSION_KEY),
                allowed_destinations=allowed_destinations,
                destination_helper_tip="More destinations coming later (subscription + referrals).",
                can_invite_from_create_page=False,
                server_error=error,
            ),
            400,
        )

    created = alert_service.append_alert_record(alert)
    app.logger.info("create_alert succeeded: alert_id=%s", created.get("alert_id"))
    session[ALERT_SESSION_KEY] = created
    return redirect(url_for("alert_created"))


@app.post("/alerts/confirm-email")
def confirm_alert_email():
    alert = session.get(ALERT_SESSION_KEY)
    if not alert:
        return redirect(url_for("index"))

    email_input = request.form.get("email", "")
    normalized_email = user_service.normalize_email(email_input)

    if not alert_service.is_valid_email(normalized_email):
        return (
            render_template(
                "success.html",
                alert=alert,
                summary=alert_service.build_alert_summary(alert),
                email_error="Enter a valid email address.",
                email_value=email_input.strip(),
            ),
            400,
        )

    allowed_destinations = user_service.allowed_destinations_for_email(normalized_email)
    selected_destinations = alert.get("destination_airport_codes", []) or []
    if len(selected_destinations) > allowed_destinations:
        return (
            render_template(
                "success.html",
                alert=alert,
                summary=alert_service.build_alert_summary(alert),
                email_error=f"This account can track up to {allowed_destinations} destinations. Remove some destinations or invite friends to unlock more slots.",
                email_value=email_input.strip(),
            ),
            400,
        )

    _, created = user_service.ensure_user(normalized_email)
    referred_by_code = session.get(REFERRED_BY_CODE_SESSION_KEY, "")
    if created and referred_by_code:
        user_service.apply_referral_for_new_user(normalized_email, referred_by_code)
    session.pop(REFERRED_BY_CODE_SESSION_KEY, None)

    updated, error = alert_service.activate_alert_with_email(
        alert.get("alert_id", ""), normalized_email
    )
    
    if error:
        return (
            render_template(
                "success.html",
                alert=alert,
                summary=alert_service.build_alert_summary(alert),
                email_error=error,
                email_value=request.form.get("email", "").strip(),
                referral_code="",
                referral_copy_url="",
            ),
            400,
        )

    from services import email as email_service

    subject, text_body, html_body = email_service.compose_alert_email(
    to_email=normalized_email,
    subject="Your Jetzi alert is live ✈️",
    intro="Jetzi is now watching your trip.",
    lines=[
        f"Route: {alert.get('origin_airport_code')} → {', '.join(alert.get('destination_airport_codes', []))}",
        f"Budget: ${int(alert.get('max_price_per_traveler', 0))} per traveler",
        "We’ll email you when a deal worth booking appears.",
        "Most alerts don’t trigger every day — we only send the good ones."
    ],
    unsubscribe_token=updated.get("unsubscribe_token"),
    )

    email_service.send_email_resend([normalized_email], subject, text_body, html_body)

    session[ALERT_SESSION_KEY] = updated
    session[USER_EMAIL_SESSION_KEY] = normalized_email
    return redirect(url_for("alerts_activated"))

@app.get("/internal/run-alerts")
def run_alerts_internal():
    if request.args.get("key") != os.getenv("INTERNAL_API_KEY"):
        return "Unauthorized", 403

    from run_alerts import main as run_alerts_main

    try:
        run_alerts_main(["--mode", "deals"])
        return "Alerts run successfully", 200
    except Exception as e:
        import traceback
        return f"<pre>{traceback.format_exc()}</pre>", 500

if __name__ == "__main__":
    app.run(debug=True)
