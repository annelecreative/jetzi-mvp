#!/usr/bin/env python3
"""User profile and referral storage for Jetzi."""

from __future__ import annotations

import json
import secrets
import string
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from services import runtime_config

BASE_DIR = Path(__file__).resolve().parent.parent
USERS_PATH = BASE_DIR / "data" / "users.json"
MAX_BONUS_DESTINATION_SLOTS = 3
MAX_TOTAL_DESTINATION_SLOTS = 4

USER_SCHEMA_KEYS = (
    "email",
    "created_at",
    "referral_code",
    "referral_count",
    "bonus_destination_slots",
    "referred_emails",
    "referred_by_code",
)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _generate_referral_code(existing_codes: set[str]) -> str:
    alphabet = string.ascii_letters + string.digits
    for _ in range(20):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if code not in existing_codes:
            return code
    raise RuntimeError("Unable to generate unique referral code")


def _normalize_user_record(record: Dict[str, Any], existing_codes: set[str]) -> Dict[str, Any]:
    normalized = dict(record)
    normalized["email"] = normalize_email(str(normalized.get("email", "")))
    normalized.setdefault("created_at", _iso_utc_now())

    referral_code = str(normalized.get("referral_code", "")).strip()
    if not referral_code:
        referral_code = _generate_referral_code(existing_codes)
    normalized["referral_code"] = referral_code
    existing_codes.add(referral_code)

    try:
        referral_count = int(normalized.get("referral_count", 0) or 0)
    except (TypeError, ValueError):
        referral_count = 0
    normalized["referral_count"] = max(0, referral_count)
    normalized["bonus_destination_slots"] = min(normalized["referral_count"], MAX_BONUS_DESTINATION_SLOTS)

    referred_emails = normalized.get("referred_emails")
    if not isinstance(referred_emails, list):
        referred_emails = []
    cleaned_referred: List[str] = []
    for email in referred_emails:
        normalized_email = normalize_email(str(email))
        if normalized_email and normalized_email not in cleaned_referred:
            cleaned_referred.append(normalized_email)
    normalized["referred_emails"] = cleaned_referred

    raw_referred_by_code = normalized.get("referred_by_code")
    if raw_referred_by_code in (None, "", "None"):
        referred_by_code = None
    else:
        referred_by_code = str(raw_referred_by_code).strip() or None
    normalized["referred_by_code"] = referred_by_code

    if not normalized["email"]:
        return {}

    return {key: normalized.get(key) for key in USER_SCHEMA_KEYS}


def load_user_records() -> List[Dict[str, Any]]:
    if not USERS_PATH.exists():
        return []

    try:
        raw = json.loads(USERS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(raw, list):
        return []

    normalized: List[Dict[str, Any]] = []
    changed = False
    codes: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = _normalize_user_record(item, codes)
        if not row:
            continue
        if row != item:
            changed = True
        normalized.append(row)

    if changed:
        save_user_records(normalized)
    return normalized


def save_user_records(users: List[Dict[str, Any]]) -> None:
    codes: set[str] = set()
    clean = []
    for user in users:
        row = _normalize_user_record(user, codes)
        if row:
            clean.append(row)
    _atomic_write_json(USERS_PATH, clean)


def find_user_by_email(email: str) -> Dict[str, Any] | None:
    normalized_email = normalize_email(email)
    for user in load_user_records():
        if user.get("email") == normalized_email:
            return user
    return None


def find_user_by_referral_code(referral_code: str) -> Dict[str, Any] | None:
    code = (referral_code or "").strip()
    if not code:
        return None

    for user in load_user_records():
        if user.get("referral_code") == code:
            return user
    return None


def ensure_user(email: str) -> Tuple[Dict[str, Any], bool]:
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise RuntimeError("User email is required")

    users = load_user_records()
    for user in users:
        if user.get("email") == normalized_email:
            return user, False

    existing_codes = {str(user.get("referral_code", "")).strip() for user in users}
    new_user = {
        "email": normalized_email,
        "created_at": _iso_utc_now(),
        "referral_code": _generate_referral_code(existing_codes),
        "referral_count": 0,
        "bonus_destination_slots": 0,
        "referred_emails": [],
        "referred_by_code": None,
    }
    users.append(new_user)
    save_user_records(users)
    return new_user, True


def allowed_destinations_for_email(email: str | None) -> int:
    base_limit = runtime_config.base_destination_limit()
    normalized_email = normalize_email(email or "")
    if not normalized_email:
        return min(MAX_TOTAL_DESTINATION_SLOTS, base_limit)

    user = find_user_by_email(normalized_email)
    bonus = int(user.get("bonus_destination_slots", 0) or 0) if user else 0
    total = base_limit + max(0, min(bonus, MAX_BONUS_DESTINATION_SLOTS))
    return min(MAX_TOTAL_DESTINATION_SLOTS, total)


def apply_referral_for_new_user(referred_email: str, referred_by_code: str) -> bool:
    code = (referred_by_code or "").strip()
    normalized_referred_email = normalize_email(referred_email)
    if not code or not normalized_referred_email:
        return False

    users = load_user_records()
    referrer_index = -1
    referred_index = -1
    for idx, user in enumerate(users):
        if user.get("referral_code") == code:
            referrer_index = idx
        if user.get("email") == normalized_referred_email:
            referred_index = idx

    if referrer_index < 0 or referred_index < 0:
        return False

    referrer = users[referrer_index]
    referred = users[referred_index]

    if referrer.get("email") == normalized_referred_email:
        return False

    if referred.get("referred_by_code"):
        return False

    referred_emails = list(referrer.get("referred_emails") or [])
    if normalized_referred_email in referred_emails:
        return False

    referred["referred_by_code"] = code
    referred_emails.append(normalized_referred_email)
    referrer["referred_emails"] = referred_emails
    referrer["referral_count"] = int(referrer.get("referral_count", 0) or 0) + 1
    referrer["bonus_destination_slots"] = min(
        int(referrer.get("referral_count", 0) or 0), MAX_BONUS_DESTINATION_SLOTS
    )

    users[referrer_index] = referrer
    users[referred_index] = referred
    save_user_records(users)
    return True
