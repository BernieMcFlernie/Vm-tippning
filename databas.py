from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, List, Optional


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
MATCHES_FILE = DATA_DIR / "matches.json"
MATCH_SCHEDULE_FILE = DATA_DIR / "match_schedule.json"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"
PLAYOFF_RESULTS_FILE = DATA_DIR / "playoff_results.json"
PLAYERS_FILE = DATA_DIR / "players.json"
USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_ADMIN_EMAIL = "admin@vm.local"
DEFAULT_ADMIN_PASSWORD = "changeme"
DEFAULT_LEAGUE = "slakten"
LEAGUES = {
    "slakten": "Släkt och familjevänner",
    "lidingo": "Lidingö",
    "korpen": "Korpen",
}


def normalize_league(value: Any) -> str:
    league = str(value or "").strip().lower()
    if league == "laget":
        return "lidingo"
    if league in LEAGUES:
        return league
    return DEFAULT_LEAGUE


def _hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 100_000, dklen=32
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256$100000${salt_b64}${digest_b64}"


def hash_password(password: str) -> str:
    return _hash_password(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_b64, digest_b64 = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected_digest = base64.b64decode(digest_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False

    computed_digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected_digest)
    )
    return hmac.compare_digest(expected_digest, computed_digest)


def _bootstrap_admin_user_if_needed() -> None:
    users = _read_json_array(USERS_FILE)
    if users:
        return

    admin_email = os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    users = [
        {
            "id": 1,
            "email": admin_email,
            "display_name": "admin",
            "password_hash": _hash_password(admin_password),
            "role": "admin",
            "must_change_password": admin_password == DEFAULT_ADMIN_PASSWORD,
            "league": DEFAULT_LEAGUE,
        }
    ]
    _write_json_array(USERS_FILE, users)


def _ensure_files_exist() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for file_path in (
        MATCHES_FILE,
        MATCH_SCHEDULE_FILE,
        PREDICTIONS_FILE,
        PLAYOFF_RESULTS_FILE,
        PLAYERS_FILE,
        USERS_FILE,
        SESSIONS_FILE,
    ):
        if not file_path.exists():
            file_path.write_text("[]", encoding="utf-8")
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(
            json.dumps(default_settings(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def ensure_storage() -> None:
    _ensure_files_exist()
    _bootstrap_admin_user_if_needed()


def _read_json_array(file_path: Path) -> List[dict[str, Any]]:
    _ensure_files_exist()
    raw = file_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError(f"{file_path.name} maste innehalla en JSON-lista")
    return data


def _write_json_array(file_path: Path, rows: List[dict[str, Any]]) -> None:
    _ensure_files_exist()
    file_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def default_settings() -> dict[str, Any]:
    return {
        "predictions_open": True,
        "predictions_visible": False,
    }


def load_settings() -> dict[str, Any]:
    _ensure_files_exist()
    raw = SETTINGS_FILE.read_text(encoding="utf-8").strip()
    data = json.loads(raw) if raw else {}
    if not isinstance(data, dict):
        data = {}
    settings = default_settings()
    settings.update({key: data.get(key, settings[key]) for key in settings})
    return {
        "predictions_open": bool(settings["predictions_open"]),
        "predictions_visible": bool(settings["predictions_visible"]),
    }


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    for key in default_settings():
        if key in settings:
            current[key] = bool(settings[key])
    SETTINGS_FILE.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current


def _validate_unique_user_emails(users: List[dict[str, Any]]) -> None:
    seen_emails: set[str] = set()
    for user in users:
        normalized_email = str(user.get("email", "")).strip().lower()
        if not normalized_email:
            raise ValueError("Alla anvandare maste ha en e-postadress")
        if normalized_email in seen_emails:
            raise ValueError(f"Dubblett e-post hittades: {normalized_email}")
        seen_emails.add(normalized_email)


def load_matches() -> List[dict[str, Any]]:
    return _read_json_array(MATCHES_FILE)


def save_matches(rows: List[dict[str, Any]]) -> None:
    _write_json_array(MATCHES_FILE, rows)


def load_match_schedule() -> List[dict[str, Any]]:
    return _read_json_array(MATCH_SCHEDULE_FILE)


def save_match_schedule(rows: List[dict[str, Any]]) -> None:
    _write_json_array(MATCH_SCHEDULE_FILE, rows)


def load_predictions() -> List[dict[str, Any]]:
    return _read_json_array(PREDICTIONS_FILE)


def save_predictions(rows: List[dict[str, Any]]) -> None:
    _write_json_array(PREDICTIONS_FILE, rows)


def load_playoff_results() -> List[dict[str, Any]]:
    return _read_json_array(PLAYOFF_RESULTS_FILE)


def save_playoff_results(rows: List[dict[str, Any]]) -> None:
    _write_json_array(PLAYOFF_RESULTS_FILE, rows)


def load_players() -> List[dict[str, Any]]:
    return _read_json_array(PLAYERS_FILE)


def save_players(rows: List[dict[str, Any]]) -> None:
    _write_json_array(PLAYERS_FILE, rows)


def load_users() -> List[dict[str, Any]]:
    ensure_storage()
    users = _read_json_array(USERS_FILE)
    _validate_unique_user_emails(users)
    return users


def save_users(rows: List[dict[str, Any]]) -> None:
    _validate_unique_user_emails(rows)
    _write_json_array(USERS_FILE, rows)


def find_user_by_email(email: str) -> Optional[dict[str, Any]]:
    normalized_email = email.strip().lower()
    for user in load_users():
        if str(user.get("email", "")).strip().lower() == normalized_email:
            return user
    return None


def find_user_by_display_name(display_name: str) -> Optional[dict[str, Any]]:
    normalized_display_name = display_name.strip().lower()
    for user in load_users():
        if str(user.get("display_name", "")).strip().lower() == normalized_display_name:
            return user
    return None


def find_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    for user in load_users():
        try:
            current_id = int(user.get("id", 0))
        except (TypeError, ValueError):
            continue
        if current_id == user_id:
            return user
    return None


def authenticate_user(email: str, password: str) -> Optional[dict[str, Any]]:
    user = find_user_by_email(email)
    if user is None:
        return None
    password_hash = str(user.get("password_hash", ""))
    if not verify_password(password, password_hash):
        return None
    return user


def authenticate_admin_password(password: str) -> Optional[dict[str, Any]]:
    if not password:
        return None
    for user in load_users():
        if user.get("role") != "admin":
            continue
        password_hash = str(user.get("password_hash", ""))
        if verify_password(password, password_hash):
            return user
    return None


def create_user(
    email: str,
    password: str,
    display_name: str,
    role: str = "user",
    must_change_password: bool = False,
    league: str = DEFAULT_LEAGUE,
) -> Optional[dict[str, Any]]:
    normalized_email = email.strip().lower()
    normalized_display_name = display_name.strip()
    if not normalized_email or not normalized_display_name or not password:
        return None
    if role not in {"user", "admin"}:
        return None

    users = load_users()
    normalized_display_name_lower = normalized_display_name.lower()
    for user in users:
        if str(user.get("email", "")).strip().lower() == normalized_email:
            return None
        if str(user.get("display_name", "")).strip().lower() == normalized_display_name_lower:
            return None

    next_id = 1
    for user in users:
        try:
            next_id = max(next_id, int(user.get("id", 0)) + 1)
        except (TypeError, ValueError):
            continue

    created_user = {
        "id": next_id,
        "email": normalized_email,
        "display_name": normalized_display_name,
        "password_hash": hash_password(password),
        "role": role,
        "must_change_password": bool(must_change_password),
        "league": normalize_league(league),
    }
    users.append(created_user)
    save_users(users)
    return created_user


def set_user_password(email: str, new_password: str) -> bool:
    users = load_users()
    normalized_email = email.strip().lower()
    for user in users:
        if str(user.get("email", "")).strip().lower() == normalized_email:
            user["password_hash"] = hash_password(new_password)
            user["must_change_password"] = False
            save_users(users)
            return True
    return False


def load_sessions() -> List[dict[str, Any]]:
    ensure_storage()
    return _read_json_array(SESSIONS_FILE)


def save_sessions(rows: List[dict[str, Any]]) -> None:
    _write_json_array(SESSIONS_FILE, rows)
