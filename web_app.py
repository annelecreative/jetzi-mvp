#!/usr/bin/env python3
import os

import config as app_config
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from services import alerts as alert_service
from services import flights as flight_service


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


@app.get("/")
def index():
    if request.args.get("fresh") == "1":
        session.pop(ALERT_SESSION_KEY, None)
    initial_alert = session.get(ALERT_SESSION_KEY) if request.args.get("restore") == "1" else None
    return render_template("index.html", initial_alert=initial_alert)


@app.get("/alert-created")
def alert_created():
    alert = session.get(ALERT_SESSION_KEY)
    if not alert:
        return redirect(url_for("index"))

    return render_template(
        "success.html",
        alert=alert,
        summary=alert_service.build_alert_summary(alert),
        email_error=None,
        email_value=alert.get("email", "") or "",
    )


@app.get("/alerts/activated")
def alerts_activated():
    alert = session.get(ALERT_SESSION_KEY)
    if not alert or alert.get("status") != "active":
        return redirect(url_for("index"))
    return render_template("activated.html", alert=alert)


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
    alert, error = alert_service.validate_and_build_alert(request.form, AIRPORTS_BY_CODE)
    if error:
        return jsonify({"error": error}), 400

    created = alert_service.append_alert_record(alert)
    session[ALERT_SESSION_KEY] = created
    return jsonify({"ok": True, **created, "redirect_url": url_for("alert_created")})


@app.post("/alerts/confirm-email")
def confirm_alert_email():
    alert = session.get(ALERT_SESSION_KEY)
    if not alert:
        return redirect(url_for("index"))

    updated, error = alert_service.activate_alert_with_email(
        alert.get("alert_id", ""), request.form.get("email", "")
    )
    if error:
        return (
            render_template(
                "success.html",
                alert=alert,
                summary=alert_service.build_alert_summary(alert),
                email_error=error,
                email_value=request.form.get("email", "").strip(),
            ),
            400,
        )

    session[ALERT_SESSION_KEY] = updated
    return redirect(url_for("alerts_activated"))


if __name__ == "__main__":
    app.run(debug=True)
