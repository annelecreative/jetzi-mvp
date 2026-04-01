#!/usr/bin/env python3

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CACHE_PATH = Path("search_cache.json")
import os

TTL_MINUTES = int(os.getenv("SEARCH_CACHE_TTL_MINUTES", "30").strip())


def _now():
    return datetime.now(timezone.utc)


def _load():
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text())
    except:
        return {}


def _save(data):
    CACHE_PATH.write_text(json.dumps(data, indent=2))


def build_key(origin, destination, outbound_date, return_date, adults, trip_type):
    return f"{origin}|{destination}|{outbound_date}|{return_date}|{adults}|{trip_type}"


def get(key):
    data = _load()
    entry = data.get(key)
    if not entry:
        return None

    ts = datetime.fromisoformat(entry["ts"])
    if _now() - ts > timedelta(minutes=TTL_MINUTES):
        return None

    return entry["results"]


def set(key, results):
    data = _load()
    data[key] = {
        "ts": _now().isoformat(),
        "results": results,
    }
    _save(data)