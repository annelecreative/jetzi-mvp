#!/usr/bin/env python3
import difflib
import json
from pathlib import Path
from typing import Dict, List, Tuple

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
AIRPORTS_PATH = BASE_DIR / "data" / "airports_min.json"


def load_airports() -> List[Dict[str, str]]:
    raw = json.loads(AIRPORTS_PATH.read_text(encoding="utf-8"))
    airports = []
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


AIRPORTS = load_airports()

app = Flask(__name__)


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


def _rank_airports(query: str, airports: List[Dict[str, str]]) -> List[Dict[str, str]]:
    q = _norm(query)
    ranked: List[Tuple[Tuple[float, str], Dict[str, str]]] = []

    for airport in airports:
        code = _norm(airport["code"])
        city = _norm(airport["city"])
        name = _norm(airport["name"])

        # Group 0: exact IATA code match
        if code == q:
            key = (0.0, code)
            ranked.append((key, airport))
            continue

        # Group 1: prefix match on code/city/name
        if code.startswith(q):
            key = (1.0, code)
            ranked.append((key, airport))
            continue
        if city.startswith(q) or name.startswith(q):
            key = (2.0, code)
            ranked.append((key, airport))
            continue

        # Group 2: contains match
        if q in city or q in name:
            key = (3.0, code)
            ranked.append((key, airport))
            continue

        # Group 3: light fuzzy for misspellings
        ratio = _fuzzy_score(q, airport)
        if ratio >= 0.72:
            key = (4.0 - ratio, code)
            ranked.append((key, airport))

    ranked.sort(key=lambda pair: pair[0])
    return [item for _, item in ranked[:10]]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/airports/search")
def search_airports():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"error": "Query must be at least 2 characters", "items": []}), 400

    items = _rank_airports(q, AIRPORTS)
    return jsonify({"items": items})


@app.post("/alerts/create")
def create_alert():
    origin_airport_code = request.form.get("origin_airport_code", "").strip().upper()
    destination_codes_raw = request.form.get("destination_airport_codes", "[]")

    try:
        destination_airport_codes = json.loads(destination_codes_raw)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid destination list format"}), 400

    if not origin_airport_code:
        return jsonify({"error": "origin_airport_code is required"}), 400
    if not isinstance(destination_airport_codes, list) or len(destination_airport_codes) < 1:
        return jsonify({"error": "At least one destination airport is required"}), 400

    cleaned_destinations = []
    for code in destination_airport_codes:
        if isinstance(code, str) and code.strip():
            cleaned_destinations.append(code.strip().upper())

    if len(cleaned_destinations) < 1:
        return jsonify({"error": "At least one destination airport is required"}), 400

    return jsonify(
        {
            "ok": True,
            "origin_airport_code": origin_airport_code,
            "destination_airport_codes": cleaned_destinations,
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
