#!/usr/bin/env python3
"""Persistent email verification tokens for Jetzi."""

from __future__ import annotations

import json
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
PERSIST_DIR = BASE_DIR / "persist"
TOKENS_PATH = PERSIST_DIR / "email_verifications.json"

TOKEN_TTL_HOURS = 24


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _ensure_store_exists() -> None:
    if TOKENS_PATH.exists():
        return
    _atomic_write_json(TOKENS_PATH, [])


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "token": str(record.get("token", "") or "").strip(),
        "alert_id": str(record.get("alert_id", "") or "").strip(),
        "email": str(record.get("email", "") or "").strip().lower(),
        "created_at": str(record.get("created_at", "") or _iso_now()).strip(),
        "expires_at": str(record.get("expires_at", "") or "").strip(),
        "used_at": str(record.get("used_at", "") or "").strip() or None,
    }


def load_records() -> List[Dict[str, Any]]:
    _ensure_store_exists()
    try:
        raw = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(raw, list):
        return []

    out: List[Dict[str, Any]] = []
    changed = False
    for item in raw:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_record(item)
        if normalized != item:
            changed = True
        out.append(normalized)

    if changed:
        save_records(out)

    return out


def save_records(records: List[Dict[str, Any]]) -> None:
    clean = [_normalize_record(record) for record in records]
    _atomic_write_json(TOKENS_PATH, clean)


def purge_expired() -> None:
    now = datetime.now(timezone.utc)
    kept: List[Dict[str, Any]] = []
    changed = False

    for record in load_records():
        expires_at = _parse_iso(record.get("expires_at", ""))
        used_at = _parse_iso(record.get("used_at", ""))
        if used_at is not None:
            changed = True
            continue
        if expires_at is not None and expires_at < now:
            changed = True
            continue
        kept.append(record)

    if changed:
        save_records(kept)


def create_token(alert_id: str, email: str) -> Dict[str, Any]:
    purge_expired()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=TOKEN_TTL_HOURS)

    records = load_records()
    token = secrets.token_urlsafe(32)

    record = {
        "token": token,
        "alert_id": str(alert_id or "").strip(),
        "email": str(email or "").strip().lower(),
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "used_at": None,
    }
    records.append(record)
    save_records(records)
    return record


def find_token(token: str) -> Dict[str, Any] | None:
    purge_expired()
    target = str(token or "").strip()
    if not target:
        return None
    for record in load_records():
        if record.get("token") == target:
            return record
    return None


def mark_used(token: str) -> Dict[str, Any] | None:
    target = str(token or "").strip()
    if not target:
        return None

    records = load_records()
    updated_record: Dict[str, Any] | None = None

    for idx, record in enumerate(records):
        if record.get("token") != target:
            continue
        updated = dict(record)
        updated["used_at"] = _iso_now()
        records[idx] = _normalize_record(updated)
        updated_record = records[idx]
        break

    if updated_record is None:
        return None

    save_records(records)
    return updated_record