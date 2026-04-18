#!/usr/bin/env python3
"""Simple persistent rate limiting for Jetzi MVP."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
PERSIST_DIR = BASE_DIR / "persist"
RATE_LIMITS_PATH = PERSIST_DIR / "rate_limits.json"


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _ensure_store_exists() -> None:
    if RATE_LIMITS_PATH.exists():
        return
    _atomic_write_json(RATE_LIMITS_PATH, {})


def _load_store() -> Dict[str, List[int]]:
    _ensure_store_exists()
    try:
        raw = json.loads(RATE_LIMITS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    if not isinstance(raw, dict):
        return {}

    cleaned: Dict[str, List[int]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        timestamps: List[int] = []
        for item in value:
            try:
                timestamps.append(int(item))
            except (TypeError, ValueError):
                continue
        cleaned[key] = timestamps
    return cleaned


def _save_store(store: Dict[str, List[int]]) -> None:
    _atomic_write_json(RATE_LIMITS_PATH, store)


def _prune(timestamps: List[int], *, window_seconds: int, now_ts: int) -> List[int]:
    cutoff = now_ts - max(1, int(window_seconds))
    return [ts for ts in timestamps if ts > cutoff]


def hit(
    key: str,
    *,
    limit: int,
    window_seconds: int,
) -> Tuple[bool, int]:
    """
    Record one hit for a key.

    Returns:
        (allowed, retry_after_seconds)
    """
    now_ts = _now_ts()
    store = _load_store()

    current = _prune(store.get(key, []), window_seconds=window_seconds, now_ts=now_ts)

    if len(current) >= max(1, int(limit)):
        oldest_relevant = min(current) if current else now_ts
        retry_after = max(1, (oldest_relevant + max(1, int(window_seconds))) - now_ts)
        store[key] = current
        _save_store(store)
        return False, retry_after

    current.append(now_ts)
    store[key] = current
    _save_store(store)
    return True, 0