from __future__ import annotations

import secrets
import time
from typing import Optional

from databas import find_user_by_id, load_sessions, save_sessions

DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 24  # 24 timmar


def _now_epoch() -> int:
    return int(time.time())


def _cleanup_expired_sessions() -> list[dict]:
    now = _now_epoch()
    sessions = load_sessions()
    active_sessions = [session for session in sessions if int(session.get("expires_at", 0)) > now]
    if len(active_sessions) != len(sessions):
        save_sessions(active_sessions)
    return active_sessions


def skapa_session(user_id: int, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> dict:
    sessions = _cleanup_expired_sessions()
    token = secrets.token_urlsafe(32)
    now = _now_epoch()
    expires_at = now + ttl_seconds
    session = {
        "token": token,
        "user_id": user_id,
        "created_at": now,
        "expires_at": expires_at,
    }
    sessions.append(session)
    save_sessions(sessions)
    return session


def verifiera_session_token(token: str) -> Optional[dict]:
    sessions = _cleanup_expired_sessions()
    for session in sessions:
        if session.get("token") != token:
            continue
        user_id = int(session.get("user_id", 0))
        user = find_user_by_id(user_id)
        if user is None:
            return None
        return {"session": session, "user": user}
    return None


def logga_ut_session(token: str) -> bool:
    sessions = _cleanup_expired_sessions()
    remaining_sessions = [session for session in sessions if session.get("token") != token]
    changed = len(remaining_sessions) != len(sessions)
    if changed:
        save_sessions(remaining_sessions)
    return changed
