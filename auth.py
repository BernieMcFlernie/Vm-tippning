from __future__ import annotations

from getpass import getpass

from databas import (
    authenticate_admin_password,
    authenticate_user,
    create_user,
    ensure_storage,
    set_user_password,
)
from session import logga_ut_session, skapa_session, verifiera_session_token


def _hamta_display_name(user: dict) -> str:
    display_name = str(user.get("display_name", "")).strip()
    if display_name:
        return display_name
    email = str(user.get("email", "")).strip()
    if "@" in email:
        local_part = email.split("@", 1)[0].strip()
        if local_part:
            return local_part
    user_id = str(user.get("id", "")).strip()
    return f"user-{user_id}" if user_id else "user"


def logga_in(email: str, losenord: str) -> dict | None:
    user = authenticate_user(email, losenord)
    if user is None:
        return None

    user_id = int(user.get("id", 0))
    if user_id <= 0:
        return None

    session = skapa_session(user_id)
    return {
        "token": session["token"],
        "expires_at": session["expires_at"],
        "user": {
            "id": user.get("id"),
            "email": user.get("email"),
            "display_name": _hamta_display_name(user),
            "role": user.get("role"),
            "must_change_password": user.get("must_change_password", False),
        },
    }


def logga_in_admin_med_losenord(losenord: str) -> dict | None:
    user = authenticate_admin_password(losenord)
    if user is None:
        return None

    user_id = int(user.get("id", 0))
    if user_id <= 0:
        return None

    session = skapa_session(user_id)
    return {
        "token": session["token"],
        "expires_at": session["expires_at"],
        "user": {
            "id": user.get("id"),
            "email": user.get("email"),
            "display_name": _hamta_display_name(user),
            "role": user.get("role"),
            "must_change_password": user.get("must_change_password", False),
        },
    }


def hamta_anvandare_fran_token(token: str) -> dict | None:
    result = verifiera_session_token(token)
    if result is None:
        return None
    user = result["user"]
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "display_name": _hamta_display_name(user),
        "role": user.get("role"),
        "must_change_password": user.get("must_change_password", False),
    }


def logga_ut(token: str) -> bool:
    return logga_ut_session(token)


def byt_losenord_med_token(token: str, current_password: str, new_password: str) -> bool:
    if not new_password:
        return False

    user = hamta_anvandare_fran_token(token)
    if user is None:
        return False

    email = str(user.get("email", ""))
    if not authenticate_user(email, current_password):
        return False

    return set_user_password(email, new_password)


def skapa_anvandare(
    email: str,
    losenord: str,
    display_name: str,
    role: str = "user",
    must_change_password: bool = False,
) -> dict | None:
    created_user = create_user(email, losenord, display_name, role, must_change_password)
    if created_user is None:
        return None
    return {
        "id": created_user.get("id"),
        "email": created_user.get("email"),
        "display_name": created_user.get("display_name"),
        "role": created_user.get("role"),
        "must_change_password": created_user.get("must_change_password", False),
    }


def cli_login() -> None:
    ensure_storage()
    print("Logga in")
    email = input("E-post: ").strip()
    losenord = getpass("Losenord: ")

    login_result = logga_in(email, losenord)
    if login_result is None:
        print("Fel e-post eller losenord.")
        return

    user = login_result["user"]
    print(f"Inloggad som {user['email']} ({user['role']})")
    print(f"Token: {login_result['token']}")
    if user.get("must_change_password"):
        print("Du maste byta losenord.")
        nytt_1 = getpass("Nytt losenord: ")
        nytt_2 = getpass("Upprepa nytt losenord: ")
        if not nytt_1:
            print("Losenord far inte vara tomt.")
            return
        if nytt_1 != nytt_2:
            print("Losenorden matchar inte.")
            return
        set_user_password(user["email"], nytt_1)
        print("Losenord uppdaterat.")


if __name__ == "__main__":
    cli_login()
