#!/usr/bin/env python3
"""User storage and referral helpers for Jetzi."""

from __future__ import annotations

import json
import secrets
import string
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from services import runtime_config

BASE_DIR = Path(__file__).resolve().parent.parent
PERSIST_DIR = BASE_DIR / "persist"
LEGACY_DATA_DIR = BASE_DIR / "data"

USERS_PATH = PERSIST_DIR / "users.json"
LEGACY_USERS_PATH = LEGACY_DATA_DIR / "users.json"

USER_SCHEMA_KEYS = (
    "email",
    "referral_code",
    "referred_by_code",
    "referral_count",
    "created_at",
)

REFERRAL_CODE_LENGTH = 8


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generate_referral_code(existing_codes: set[str]) -> str:
    alphabet = string.ascii_lowercase + string.digits
    for _ in range(100):
        code = "".join(secrets.choice(alphabet) for _ in range(REFERRAL_CODE_LENGTH))
        if code not in existing_codes:
            return code
    raise RuntimeError("Unable to generate unique referral code")


def _normalize_user_record(user: Dict[str, Any], *, existing_codes: set[str] | None = None) -> Dict[str, Any]:
    normalized = dict(user)

    normalized["email"] = normalize_email(normalized.get("email", ""))
    if not normalized["email"]:
        raise RuntimeError("User record missing email")

    normalized["referred_by_code"] = str(normalized.get("referred_by_code", "") or "").strip().lower()
    normalized["referral_count"] = max(0, int(normalized.get("referral_count", 0) or 0))
    normalized["created_at"] = str(normalized.get("created_at", "") or _iso_now()).strip()

    referral_code = str(normalized.get("referral_code", "") or "").strip().lower()
    if not referral_code:
        existing_codes = existing_codes or set()
        referral_code = _generate_referral_code(existing_codes)
    normalized["referral_code"] = referral_code

    return {key: normalized.get(key) for key in USER_SCHEMA_KEYS}


def _initial_user_payload() -> List[Dict[str, Any]]:
    if LEGACY_USERS_PATH.exists():
        try:
            raw = json.loads(LEGACY_USERS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [item for item in raw if isinstance(item, dict)]
        except json.JSONDecodeError:
            pass
    return []


def _ensure_user_store_exists() -> None:
    if USERS_PATH.exists():
        return
    seed = _initial_user_payload()
    save_user_records(seed)


def load_user_records() -> List[Dict[str, Any]]:
    _ensure_user_store_exists()

    try:
        raw = json.loads(USERS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(raw, list):
        return []

    normalized_users: List[Dict[str, Any]] = []
    changed = False
    seen_codes: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_user_record(item, existing_codes=seen_codes)
        seen_codes.add(normalized["referral_code"])
        if normalized != item:
            changed = True
        normalized_users.append(normalized)

    if changed:
        save_user_records(normalized_users)

    return normalized_users


def save_user_records(users: List[Dict[str, Any]]) -> None:
    clean_users: List[Dict[str, Any]] = []
    seen_codes: set[str] = set()

    for user in users:
        clean = _normalize_user_record(user, existing_codes=seen_codes)
        seen_codes.add(clean["referral_code"])
        clean_users.append(clean)

    _atomic_write_json(USERS_PATH, clean_users)


def find_user_by_email(email: str) -> Dict[str, Any] | None:
    target = normalize_email(email)
    if not target:
        return None
    for user in load_user_records():
        if user.get("email") == target:
            return user
    return None


def find_user_by_referral_code(code: str) -> Dict[str, Any] | None:
    target = str(code or "").strip().lower()
    if not target:
        return None
    for user in load_user_records():
        if str(user.get("referral_code", "")).strip().lower() == target:
            return user
    return None


def ensure_user(email: str) -> Tuple[Dict[str, Any], bool]:
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise RuntimeError("Email is required")

    existing = find_user_by_email(normalized_email)
    if existing:
        return existing, False

    users = load_user_records()
    seen_codes = {str(user.get("referral_code", "")).strip().lower() for user in users}

    new_user = _normalize_user_record(
        {
            "email": normalized_email,
            "referred_by_code": "",
            "referral_count": 0,
            "created_at": _iso_now(),
        },
        existing_codes=seen_codes,
    )

    users.append(new_user)
    save_user_records(users)
    return new_user, True


def allowed_destinations_for_email(email: str | None) -> int:
    base_limit = runtime_config.base_destination_limit()
    normalized_email = normalize_email(email or "")
    if not normalized_email:
        return base_limit

    user = find_user_by_email(normalized_email)
    if not user:
        return base_limit

    referral_count = max(0, int(user.get("referral_count", 0) or 0))
    return base_limit + referral_count


def apply_referral_for_new_user(new_user_email: str, referred_by_code: str) -> bool:
    normalized_email = normalize_email(new_user_email)
    normalized_code = str(referred_by_code or "").strip().lower()

    if not normalized_email or not normalized_code:
        return False

    users = load_user_records()

    inviter_idx = None
    new_user_idx = None

    for idx, user in enumerate(users):
        if user.get("email") == normalized_email:
            new_user_idx = idx
        if str(user.get("referral_code", "")).strip().lower() == normalized_code:
            inviter_idx = idx

    if inviter_idx is None or new_user_idx is None:
        return False

    inviter = dict(users[inviter_idx])
    new_user = dict(users[new_user_idx])

    if inviter.get("email") == new_user.get("email"):
        return False

    if str(new_user.get("referred_by_code", "")).strip():
        return False

    new_user["referred_by_code"] = normalized_code
    inviter["referral_count"] = max(0, int(inviter.get("referral_count", 0) or 0)) + 1

    users[inviter_idx] = inviter
    users[new_user_idx] = new_user
    save_user_records(users)
    return True