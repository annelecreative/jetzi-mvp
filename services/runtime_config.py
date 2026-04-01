#!/usr/bin/env python3
"""Runtime configuration helpers with safe defaults and fail-fast parsing."""

from __future__ import annotations

import os

import config as app_config


DEFAULTS = {
    "BASE_DESTINATION_LIMIT": 3,
    "BASELINE_LOOKBACK_DAYS": 30,
    "BASELINE_MIN_OBSERVATIONS": 5,
    "SIGNIFICANT_DROP_PCT": 20,
    "DEAL_DEDUPE_HOURS": 24,
    "NO_DEAL_CHECKIN_DAYS": 7,
}


def _raw_value(name: str) -> str:
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value.strip()

    cfg_value = getattr(app_config, name, DEFAULTS[name])
    return str(cfg_value).strip()


def get_int(name: str) -> int:
    if name not in DEFAULTS:
        raise RuntimeError(f"Unknown config key requested: {name}")

    raw = _raw_value(name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer (got {raw!r})") from exc

    if value < 1:
        raise RuntimeError(f"{name} must be >= 1 (got {value})")
    return value


def baseline_lookback_days() -> int:
    return get_int("BASELINE_LOOKBACK_DAYS")


def baseline_min_observations() -> int:
    return get_int("BASELINE_MIN_OBSERVATIONS")


def significant_drop_pct() -> int:
    return get_int("SIGNIFICANT_DROP_PCT")


def dedupe_hours() -> int:
    return get_int("DEAL_DEDUPE_HOURS")


def no_deal_checkin_days() -> int:
    return get_int("NO_DEAL_CHECKIN_DAYS")


def base_destination_limit() -> int:
    return get_int("BASE_DESTINATION_LIMIT")
