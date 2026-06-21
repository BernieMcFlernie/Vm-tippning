from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth import (
    byt_losenord_med_token,
    hamta_anvandare_fran_token,
    logga_in,
    logga_in_admin_med_losenord,
    logga_ut,
    skapa_anvandare,
)
from match import PLAYOFF_ROUNDS, las_fran_json, rakna_tabell
from databas import (
    LEAGUES,
    find_user_by_display_name,
    find_user_by_email,
    load_matches,
    load_players,
    load_playoff_results,
    load_predictions,
    load_settings,
    normalize_league,
    save_matches,
    save_players,
    save_playoff_results,
    save_predictions,
    save_settings,
)

app = FastAPI(title="VM Tippning API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer(auto_error=False)
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1)


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    display_name: str = Field(min_length=2)
    role: str = Field(default="user")
    must_change_password: bool = Field(default=False)
    league: str = Field(default="slakten")
    league_code: str = Field(default="")


class CreateGroupPredictionRequest(BaseModel):
    match_id: int = Field(gt=0)
    predicted_outcome: str = Field(min_length=1)


class CreatePlayoffPredictionRequest(BaseModel):
    match_id: int = Field(gt=0)
    predicted_team: str = Field(min_length=1)


class SavePlayoffTeamsRequest(BaseModel):
    teams: list[str] = Field(default_factory=list)


class SavePlayoffPredictionsRequest(BaseModel):
    rounds: dict[str, list[str]] = Field(default_factory=dict)


class SaveMatchResultRequest(BaseModel):
    home_goals: int | None = Field(default=None, ge=0)
    away_goals: int | None = Field(default=None, ge=0)
    advancing_team: str | None = Field(default=None)


class SavePredictionSettingsRequest(BaseModel):
    predictions_open: bool
    predictions_visible: bool


PLAYOFF_ROUND_LIMITS = {
    "sextondel": 32,
    "attondel": 16,
    "kvart": 8,
    "semi": 4,
    "final": 2,
    "vinnare": 1,
}

PLAYOFF_ROUND_LABELS = {
    "sextondel": "Sextondelsfinal",
    "attondel": "Attondelsfinal",
    "kvart": "Kvartsfinal",
    "semi": "Semifinal",
    "final": "Final",
    "vinnare": "Vinnare",
}

LEAGUE_CODES = {
    "slakten": "00",
    "lidingo": "1002",
    "korpen": "13",
}


def _extract_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = credentials.credentials.strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    return token


def _require_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    token = _extract_token(credentials)
    user = hamta_anvandare_fran_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def _require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    user = _require_user(credentials)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin behorighet kravs")
    return user


def _prediction_settings_response() -> dict[str, bool]:
    settings = load_settings()
    predictions_open = bool(settings.get("predictions_open", True))
    predictions_visible = bool(settings.get("predictions_visible", False))
    return {
        "predictions_open": predictions_open,
        "predictions_visible": predictions_visible,
        "locked": not predictions_open,
        "can_edit": predictions_open,
        "can_view_others": predictions_visible,
    }


def _require_predictions_open() -> None:
    if not _prediction_settings_response()["can_edit"]:
        raise HTTPException(
            status_code=403,
            detail="Tippningarna ar lasta och kan inte andras.",
        )


def _require_predictions_visible() -> None:
    if not _prediction_settings_response()["can_view_others"]:
        raise HTTPException(
            status_code=403,
            detail="Andras tippningar kan inte visas just nu.",
        )


def _hamta_match(match_id: int) -> dict[str, Any]:
    matches_data = load_matches()
    match_row = next((row for row in matches_data if int(row.get("id", 0)) == match_id), None)
    if match_row is None:
        raise HTTPException(status_code=404, detail="Matchen hittades inte")
    return match_row


def _user_league(user: dict[str, Any]) -> str:
    return normalize_league(user.get("league"))


def _validate_league_code(league: str, code: str) -> None:
    expected_code = LEAGUE_CODES.get(league)
    if expected_code is None:
        return
    if str(code).strip() != expected_code:
        league_name = LEAGUES.get(league, "ligan")
        raise HTTPException(status_code=403, detail=f"Fel kod for {league_name}")


def _player_league(row: dict[str, Any]) -> str:
    return normalize_league(row.get("league"))


def _player_row_belongs_to_league(row: dict[str, Any], league: str) -> bool:
    return _player_league(row) == league


def _league_player_objects(players_data: list[Any], league: str) -> list[tuple[int, Any]]:
    player_rows_with_ids: list[tuple[int, dict[str, Any]]] = []
    for row in load_players():
        try:
            player_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if player_id > 0:
            player_rows_with_ids.append((player_id, row))
    player_rows_with_ids.sort(key=lambda item: item[0])

    return [
        (player_id, player)
        for (player_id, _), player in zip(player_rows_with_ids, players_data)
        if normalize_league(getattr(player, "league", None)) == league
    ]


def _hamta_eller_skapa_player_id(user: dict[str, Any]) -> int:
    players_data = load_players()
    user_display_name = str(user.get("display_name", "")).strip()
    league = _user_league(user)
    if not user_display_name:
        raise HTTPException(status_code=400, detail="Anvandaren saknar display_name")

    player_row = next(
        (
            row
            for row in players_data
            if str(row.get("name", "")).strip().lower() == user_display_name.lower()
            and _player_row_belongs_to_league(row, league)
        ),
        None,
    )
    if player_row is not None:
        if "league" not in player_row:
            player_row["league"] = league
            save_players(players_data)
        return int(player_row.get("id", 0))

    next_player_id = 1
    for row in players_data:
        try:
            next_player_id = max(next_player_id, int(row.get("id", 0)) + 1)
        except (TypeError, ValueError):
            continue

    new_player = {
        "id": next_player_id,
        "name": user_display_name,
        "points": 0.0,
        "attondels_lag": [],
        "slutspel_lag": {},
        "league": league,
    }
    players_data.append(new_player)
    save_players(players_data)
    return next_player_id


def _hamta_player_id(user: dict[str, Any]) -> int | None:
    players_data = load_players()
    user_display_name = str(user.get("display_name", "")).strip().lower()
    league = _user_league(user)
    if not user_display_name:
        return None
    for row in players_data:
        player_name = str(row.get("name", "")).strip().lower()
        if player_name != user_display_name or not _player_row_belongs_to_league(row, league):
            continue
        try:
            return int(row.get("id", 0))
        except (TypeError, ValueError):
            return None
    return None


def _spara_prediction(player_id: int, match_id: int, prediction: dict[str, Any]) -> dict[str, Any]:
    predictions_data = load_predictions()
    predictions_data = [
        row
        for row in predictions_data
        if not (
            int(row.get("player_id", 0)) == player_id and int(row.get("match_id", 0)) == match_id
        )
    ]

    new_prediction = {"player_id": player_id, "match_id": match_id, **prediction}
    predictions_data.append(new_prediction)
    save_predictions(predictions_data)
    return new_prediction


def _valid_playoff_teams() -> set[str]:
    teams: set[str] = set()
    for row in load_matches():
        home_team = str(row.get("home_team", "")).strip()
        away_team = str(row.get("away_team", "")).strip()
        if home_team:
            teams.add(home_team)
        if away_team:
            teams.add(away_team)
    return teams


def _empty_playoff_rounds() -> dict[str, list[str]]:
    return {round_key: [] for round_key in PLAYOFF_ROUNDS}


def _normalize_playoff_rounds(raw_rounds: dict[str, Any]) -> dict[str, list[str]]:
    valid_teams = _valid_playoff_teams()
    normalized_rounds = _empty_playoff_rounds()
    previous_allowed = valid_teams

    for round_key in PLAYOFF_ROUNDS:
        raw_teams = raw_rounds.get(round_key, [])
        if not isinstance(raw_teams, list):
            raise HTTPException(status_code=400, detail=f"{round_key} maste vara en lista")

        unique_teams: list[str] = []
        seen: set[str] = set()
        for team in raw_teams:
            normalized = str(team).strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            if normalized not in valid_teams:
                raise HTTPException(status_code=400, detail=f"Ogiltigt lag: {normalized}")
            if normalized not in previous_allowed:
                label = PLAYOFF_ROUND_LABELS.get(round_key, round_key)
                raise HTTPException(
                    status_code=400,
                    detail=f"{normalized} kan inte valjas i {label} utan att vara valt i rundan innan",
                )
            seen.add(lowered)
            unique_teams.append(normalized)

        limit = PLAYOFF_ROUND_LIMITS[round_key]
        if len(unique_teams) > limit:
            label = PLAYOFF_ROUND_LABELS.get(round_key, round_key)
            raise HTTPException(status_code=400, detail=f"{label} kan ha max {limit} lag")

        normalized_rounds[round_key] = unique_teams
        previous_allowed = set(unique_teams)

    return normalized_rounds


def _playoff_rounds_from_player(row: dict[str, Any]) -> dict[str, list[str]]:
    rounds = _empty_playoff_rounds()
    saved_rounds = row.get("slutspel_lag", {})
    if isinstance(saved_rounds, dict):
        for round_key in PLAYOFF_ROUNDS:
            teams = saved_rounds.get(round_key, [])
            if isinstance(teams, list):
                rounds[round_key] = [str(team).strip() for team in teams if str(team).strip()]
    old_attondel = row.get("attondels_lag", [])
    if not rounds["attondel"] and isinstance(old_attondel, list):
        rounds["attondel"] = [str(team).strip() for team in old_attondel if str(team).strip()]
    return rounds


def _playoff_response(rounds: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "rounds": rounds,
        "limits": PLAYOFF_ROUND_LIMITS,
        "labels": PLAYOFF_ROUND_LABELS,
        "order": list(PLAYOFF_ROUNDS),
    }


def _normalize_playoff_results(raw_rounds: dict[str, Any]) -> dict[str, list[str]]:
    return _normalize_playoff_rounds(raw_rounds)


def _load_playoff_results_rounds() -> dict[str, list[str]]:
    rounds = _empty_playoff_rounds()
    for row in load_playoff_results():
        round_key = str(row.get("round", "")).strip().lower()
        if round_key not in rounds:
            continue
        teams = row.get("teams", [])
        if isinstance(teams, list):
            rounds[round_key] = [str(team).strip() for team in teams if str(team).strip()]
    return rounds


def _save_playoff_results_rounds(rounds: dict[str, list[str]]) -> None:
    save_playoff_results(
        [{"round": round_key, "teams": rounds[round_key]} for round_key in PLAYOFF_ROUNDS]
    )


def _league_players_for_user(user: dict[str, Any]) -> tuple[str, list[tuple[int, Any]]]:
    _matches_data, players_data = las_fran_json()
    league = _user_league(user)
    return league, _league_player_objects(players_data, league)


def _playoff_team_stats(league_players: list[tuple[int, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    stats: dict[str, dict[str, dict[str, Any]]] = {round_key: {} for round_key in PLAYOFF_ROUNDS}
    for player_id, player in league_players:
        player_name = str(getattr(player, "name", "")).strip() or f"Spelare {player_id}"
        for round_key in PLAYOFF_ROUNDS:
            teams = getattr(player, "slutspel_lag", {}).get(round_key, [])
            if not isinstance(teams, list):
                continue
            for team in teams:
                normalized_team = str(team).strip()
                if not normalized_team:
                    continue
                team_stats = stats[round_key].setdefault(
                    normalized_team,
                    {"team": normalized_team, "count": 0, "players": []},
                )
                team_stats["count"] += 1
                team_stats["players"].append({"player_id": player_id, "name": player_name})
    return stats


def _playoff_points_for_team(
    total_players: int,
    round_stats: dict[str, dict[str, Any]],
    team: str,
) -> float:
    count = int(round_stats.get(team, {}).get("count", 0))
    if count <= 0:
        return 0.0
    return float(total_players / count)


def _count_correct_for_player(player: Any, matches_data: list[Any], playoff_results: dict[str, list[str]]) -> dict[str, int]:
    match_correct = 0
    for match in matches_data:
        prediction = player.prediction_for(match)
        if prediction is not None and prediction.is_correct():
            match_correct += 1

    playoff_correct = 0
    for round_key in PLAYOFF_ROUNDS:
        correct_teams = set(playoff_results.get(round_key, []))
        if not correct_teams:
            continue
        predicted_teams = getattr(player, "slutspel_lag", {}).get(round_key, [])
        if not isinstance(predicted_teams, list):
            continue
        playoff_correct += sum(1 for team in predicted_teams if team in correct_teams)

    return {
        "match_correct": match_correct,
        "playoff_correct": playoff_correct,
        "total_correct": match_correct + playoff_correct,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/predictions/status")
def predictions_status(_: dict[str, Any] = Depends(_require_user)) -> dict[str, bool]:
    return _prediction_settings_response()


@app.get("/admin/prediction-settings")
def admin_prediction_settings(_: dict[str, Any] = Depends(_require_admin)) -> dict[str, bool]:
    return _prediction_settings_response()


@app.post("/admin/prediction-settings")
def admin_save_prediction_settings(
    payload: SavePredictionSettingsRequest,
    _: dict[str, Any] = Depends(_require_admin),
) -> dict[str, bool]:
    save_settings(
        {
            "predictions_open": payload.predictions_open,
            "predictions_visible": payload.predictions_visible,
        }
    )
    return _prediction_settings_response()


@app.get("/leagues")
def leagues() -> list[dict[str, str]]:
    return [{"id": league_id, "name": name} for league_id, name in LEAGUES.items()]


@app.post("/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    result = logga_in(payload.email, payload.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Fel e-post eller losenord")
    user = result.get("user", {})
    if user.get("role") == "admin" and user.get("must_change_password"):
        result["next_endpoint"] = "/change-password"
    return result


@app.post("/admin/login")
def admin_login(payload: AdminLoginRequest) -> dict[str, Any]:
    result = logga_in_admin_med_losenord(payload.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Fel adminlosenord")
    return result


@app.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, bool]:
    token = _extract_token(credentials)
    return {"ok": logga_ut(token)}


@app.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, bool]:
    token = _extract_token(credentials)
    ok = byt_losenord_med_token(token, payload.current_password, payload.new_password)
    if not ok:
        raise HTTPException(
            status_code=400, detail="Kunde inte byta losenord. Kontrollera uppgifterna."
        )
    return {"ok": True}


@app.post("/users")
def create_user(
    payload: CreateUserRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    current_user: dict[str, Any] | None = None
    if credentials is not None:
        token = _extract_token(credentials)
        current_user = hamta_anvandare_fran_token(token)

    role = payload.role
    must_change_password = payload.must_change_password
    league = normalize_league(payload.league)
    _validate_league_code(league, payload.league_code)
    if current_user is None or current_user.get("role") != "admin":
        role = "user"
        must_change_password = False

    if find_user_by_email(payload.email) is not None:
        raise HTTPException(status_code=409, detail="E-postadressen finns redan")
    if find_user_by_display_name(payload.display_name) is not None:
        raise HTTPException(status_code=409, detail="Displaynamnet finns redan")

    created_user = skapa_anvandare(
        payload.email,
        payload.password,
        payload.display_name,
        role,
        must_change_password,
        league,
    )
    if created_user is None:
        raise HTTPException(
            status_code=400,
            detail="Kunde inte skapa anvandare. Kontrollera e-post, display_name, losenord och roll.",
        )
    return created_user


@app.post("/predictions/gruppspel")
def create_group_prediction(
    payload: CreateGroupPredictionRequest,
    user: dict[str, Any] = Depends(_require_user),
) -> dict[str, Any]:
    _require_predictions_open()
    _hamta_match(payload.match_id)
    player_id = _hamta_eller_skapa_player_id(user)
    predicted_outcome = payload.predicted_outcome.strip().lower()
    if predicted_outcome not in {"vinst", "kryss", "forlust"}:
        raise HTTPException(
            status_code=400,
            detail="Ogiltig tippning. Anvand vinst, kryss eller forlust",
        )
    return _spara_prediction(
        player_id,
        payload.match_id,
        {"type": "gruppspel", "predicted_outcome": predicted_outcome},
    )


@app.post("/predictions/slutspel")
def create_playoff_prediction(
    payload: CreatePlayoffPredictionRequest,
    user: dict[str, Any] = Depends(_require_user),
) -> dict[str, Any]:
    _require_predictions_open()
    match_row = _hamta_match(payload.match_id)
    player_id = _hamta_eller_skapa_player_id(user)
    predicted_team = payload.predicted_team.strip()
    home_team = str(match_row.get("home_team", "")).strip()
    away_team = str(match_row.get("away_team", "")).strip()
    if predicted_team not in {home_team, away_team}:
        raise HTTPException(status_code=400, detail="Du maste tippa pa ett av lagen i matchen")
    return _spara_prediction(
        player_id,
        payload.match_id,
        {"type": "slutspel", "predicted_team": predicted_team},
    )


@app.get("/me")
def me(user: dict[str, Any] = Depends(_require_user)) -> dict[str, Any]:
    return user


@app.get("/predictions/me")
def my_predictions(user: dict[str, Any] = Depends(_require_user)) -> list[dict[str, Any]]:
    player_id = _hamta_player_id(user)
    if player_id is None:
        return []
    predictions_data = load_predictions()
    filtered: list[dict[str, Any]] = []
    for row in predictions_data:
        try:
            current_player_id = int(row.get("player_id", 0))
        except (TypeError, ValueError):
            continue
        if current_player_id == player_id:
            filtered.append(row)
    return filtered


@app.get("/predictions/player/{player_id}")
def predictions_for_player(
    player_id: int,
    user: dict[str, Any] = Depends(_require_user),
) -> dict[str, Any]:
    _require_predictions_visible()
    league = _user_league(user)
    players_data = load_players()
    player_row: dict[str, Any] | None = None
    for row in players_data:
        try:
            current_player_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if current_player_id == player_id and _player_row_belongs_to_league(row, league):
            player_row = row
            break
    if player_row is None:
        raise HTTPException(status_code=404, detail="Spelaren hittades inte")

    matches_data, player_objects = las_fran_json()
    league_players = _league_player_objects(player_objects, league)
    current_player = next((player for current_id, player in league_players if current_id == player_id), None)
    if current_player is None:
        raise HTTPException(status_code=404, detail="Spelarens tippningar hittades inte")

    total_players = len(league_players) if league_players else 1

    rows: list[dict[str, Any]] = []
    for match_id, match in enumerate(matches_data, start=1):
        prediction = current_player.prediction_for(match)
        prediction_text: str | None = None
        prediction_type: str | None = None
        is_correct = False

        if prediction is not None and hasattr(prediction, "predicted_outcome"):
            prediction_type = "gruppspel"
            predicted_outcome = str(getattr(prediction, "predicted_outcome", ""))
            if predicted_outcome == "vinst":
                prediction_text = match.home_team
            elif predicted_outcome == "forlust":
                prediction_text = match.away_team
            else:
                prediction_text = "Kryss"
            is_correct = prediction.is_correct()
        elif prediction is not None and hasattr(prediction, "predicted_team"):
            prediction_type = "slutspel"
            prediction_text = str(getattr(prediction, "predicted_team", ""))
            is_correct = prediction.is_correct()

        correct_count = 0
        for _, player in league_players:
            candidate = player.prediction_for(match)
            if candidate is not None and candidate.is_correct():
                correct_count += 1

        points_awarded = 0.0
        if is_correct and correct_count > 0:
            points_awarded = float(total_players / correct_count)

        points_if_correct: float | None = None
        if match.home_goals is not None and match.away_goals is not None:
            points_if_correct = (
                points_awarded if is_correct else float(total_players / (correct_count + 1))
            )

        rows.append(
            {
                "match_id": match_id,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "result": f"{match.home_goals}-{match.away_goals}" if match.home_goals is not None and match.away_goals is not None else None,
                "prediction_type": prediction_type,
                "prediction": prediction_text,
                "points_awarded": points_awarded,
                "points_if_correct": points_if_correct,
            }
        )

    return {
        "player_id": player_id,
        "player_name": str(player_row.get("name", "")).strip() or f"Spelare {player_id}",
        "playoff_teams": [
            str(team).strip()
            for team in player_row.get("attondels_lag", [])
            if str(team).strip()
        ] if isinstance(player_row.get("attondels_lag", []), list) else [],
        "playoff_predictions": _playoff_rounds_from_player(player_row),
        "predictions": rows,
    }


@app.get("/playoff-tree/player/{player_id}")
def playoff_tree_for_player(
    player_id: int,
    user: dict[str, Any] = Depends(_require_user),
) -> dict[str, Any]:
    _require_predictions_visible()
    league = _user_league(user)
    players_data = load_players()
    player_row: dict[str, Any] | None = None
    for row in players_data:
        try:
            current_player_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if current_player_id == player_id and _player_row_belongs_to_league(row, league):
            player_row = row
            break
    if player_row is None:
        raise HTTPException(status_code=404, detail="Spelaren hittades inte")

    _matches_data, player_objects = las_fran_json()
    league_players = _league_player_objects(player_objects, league)
    total_players = len(league_players) if league_players else 1
    team_stats = _playoff_team_stats(league_players)
    actual_rounds = _load_playoff_results_rounds()
    player_rounds = _playoff_rounds_from_player(player_row)

    rounds: list[dict[str, Any]] = []
    for round_key in PLAYOFF_ROUNDS:
        round_stats = team_stats.get(round_key, {})
        teams = []
        for team in player_rounds.get(round_key, []):
            team_name = str(team).strip()
            if not team_name:
                continue
            stats = round_stats.get(team_name, {"count": 0, "players": []})
            teams.append(
                {
                    "team": team_name,
                    "picked_count": int(stats.get("count", 0)),
                    "points_if_correct": _playoff_points_for_team(total_players, round_stats, team_name),
                    "is_correct": team_name in actual_rounds.get(round_key, []),
                }
            )
        rounds.append(
            {
                "key": round_key,
                "label": PLAYOFF_ROUND_LABELS.get(round_key, round_key),
                "teams": teams,
            }
        )

    return {
        "player_id": player_id,
        "player_name": str(player_row.get("name", "")).strip() or f"Spelare {player_id}",
        "total_players": total_players,
        "rounds": rounds,
    }


@app.get("/playoff-teams/me")
def my_playoff_teams(user: dict[str, Any] = Depends(_require_user)) -> dict[str, list[str]]:
    player_id = _hamta_player_id(user)
    if player_id is None:
        return {"teams": []}

    players_data = load_players()
    player_row: dict[str, Any] | None = None
    for row in players_data:
        try:
            current_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if current_id == player_id:
            player_row = row
            break
    if player_row is None:
        return {"teams": []}

    teams = player_row.get("attondels_lag", [])
    if not isinstance(teams, list):
        return {"teams": []}
    return {"teams": [str(team).strip() for team in teams if str(team).strip()]}


@app.get("/playoff-predictions/me")
def my_playoff_predictions(user: dict[str, Any] = Depends(_require_user)) -> dict[str, Any]:
    player_id = _hamta_player_id(user)
    if player_id is None:
        return _playoff_response(_empty_playoff_rounds())

    for row in load_players():
        try:
            current_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if current_id == player_id:
            return _playoff_response(_playoff_rounds_from_player(row))

    return _playoff_response(_empty_playoff_rounds())


@app.post("/playoff-predictions/me")
def save_playoff_predictions(
    payload: SavePlayoffPredictionsRequest,
    user: dict[str, Any] = Depends(_require_user),
) -> dict[str, Any]:
    _require_predictions_open()
    player_id = _hamta_eller_skapa_player_id(user)
    normalized_rounds = _normalize_playoff_rounds(payload.rounds)

    players_data = load_players()
    updated = False
    for row in players_data:
        try:
            current_player_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if current_player_id != player_id:
            continue
        row["slutspel_lag"] = normalized_rounds
        row["attondels_lag"] = normalized_rounds.get("attondel", [])
        updated = True
        break

    if not updated:
        raise HTTPException(status_code=404, detail="Spelaren hittades inte")

    save_players(players_data)
    return _playoff_response(normalized_rounds)


@app.post("/playoff-teams/me")
def save_playoff_teams(
    payload: SavePlayoffTeamsRequest,
    user: dict[str, Any] = Depends(_require_user),
) -> dict[str, list[str]]:
    _require_predictions_open()
    rounds = _empty_playoff_rounds()
    rounds["sextondel"] = payload.teams
    rounds["attondel"] = payload.teams
    saved = save_playoff_predictions(SavePlayoffPredictionsRequest(rounds=rounds), user)
    return {"teams": saved["rounds"].get("attondel", [])}


@app.get("/admin/facit")
def admin_facit(_: dict[str, Any] = Depends(_require_admin)) -> dict[str, Any]:
    return {
        "matches": load_matches(),
        "playoff_results": _load_playoff_results_rounds(),
        "playoff_limits": PLAYOFF_ROUND_LIMITS,
        "playoff_labels": PLAYOFF_ROUND_LABELS,
        "playoff_order": list(PLAYOFF_ROUNDS),
    }


@app.get("/admin/predictions")
def admin_predictions(_: dict[str, Any] = Depends(_require_admin)) -> list[dict[str, Any]]:
    matches_by_id: dict[int, dict[str, Any]] = {}
    for row in load_matches():
        try:
            match_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if match_id > 0:
            matches_by_id[match_id] = row

    raw_predictions_by_player: dict[int, list[dict[str, Any]]] = {}
    for row in load_predictions():
        try:
            player_id = int(row.get("player_id", 0))
            match_id = int(row.get("match_id", 0))
        except (TypeError, ValueError):
            continue
        if player_id <= 0 or match_id <= 0:
            continue

        match_row = matches_by_id.get(match_id, {})
        home_team = str(match_row.get("home_team", "")).strip()
        away_team = str(match_row.get("away_team", "")).strip()
        prediction_type = str(row.get("type", "")).strip()
        prediction = "-"

        if prediction_type == "gruppspel":
            predicted_outcome = str(row.get("predicted_outcome", "")).strip().lower()
            if predicted_outcome == "vinst":
                prediction = home_team or "Hemmalag"
            elif predicted_outcome == "forlust":
                prediction = away_team or "Bortalag"
            elif predicted_outcome == "kryss":
                prediction = "Kryss"
        elif prediction_type == "slutspel":
            prediction = str(row.get("predicted_team", "")).strip() or "-"

        raw_predictions_by_player.setdefault(player_id, []).append(
            {
                "match_id": match_id,
                "match": f"{home_team} - {away_team}".strip(" -"),
                "type": prediction_type,
                "prediction": prediction,
            }
        )

    players: list[dict[str, Any]] = []
    for row in load_players():
        try:
            player_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if player_id <= 0:
            continue

        league = _player_league(row)
        predictions = sorted(
            raw_predictions_by_player.get(player_id, []),
            key=lambda item: int(item.get("match_id", 0)),
        )
        players.append(
            {
                "player_id": player_id,
                "name": str(row.get("name", "")).strip() or f"Spelare {player_id}",
                "league": league,
                "league_name": LEAGUES.get(league, league),
                "predictions": predictions,
                "playoff_predictions": _playoff_rounds_from_player(row),
            }
        )

    players.sort(key=lambda item: (str(item.get("league_name", "")), str(item.get("name", "")).lower()))
    return players


@app.post("/admin/matches/{match_id}/result")
def admin_save_match_result(
    match_id: int,
    payload: SaveMatchResultRequest,
    _: dict[str, Any] = Depends(_require_admin),
) -> dict[str, Any]:
    matches_data = load_matches()
    match_row: dict[str, Any] | None = None
    for row in matches_data:
        try:
            current_match_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if current_match_id == match_id:
            match_row = row
            break
    if match_row is None:
        raise HTTPException(status_code=404, detail="Matchen hittades inte")

    if (payload.home_goals is None) != (payload.away_goals is None):
        raise HTTPException(status_code=400, detail="Fyll i bade hemma- och bortamal eller lamna bada tomma")

    advancing_team = str(payload.advancing_team or "").strip()
    if advancing_team:
        home_team = str(match_row.get("home_team", "")).strip()
        away_team = str(match_row.get("away_team", "")).strip()
        if advancing_team not in {home_team, away_team}:
            raise HTTPException(status_code=400, detail="Lag som gar vidare maste vara ett av lagen i matchen")

    match_row["home_goals"] = payload.home_goals
    match_row["away_goals"] = payload.away_goals
    match_row["advancing_team"] = advancing_team or None
    save_matches(matches_data)
    return match_row


@app.post("/admin/playoff-results")
def admin_save_playoff_results(
    payload: SavePlayoffPredictionsRequest,
    _: dict[str, Any] = Depends(_require_admin),
) -> dict[str, Any]:
    normalized_rounds = _normalize_playoff_results(payload.rounds)
    _save_playoff_results_rounds(normalized_rounds)
    return _playoff_response(normalized_rounds)


@app.get("/facit/me")
def my_facit(user: dict[str, Any] = Depends(_require_user)) -> list[dict[str, Any]]:
    matches_data, players_data = las_fran_json()
    league = _user_league(user)
    league_players = [player for _, player in _league_player_objects(players_data, league)]
    display_name = str(user.get("display_name", "")).strip().lower()
    if not display_name:
        return []

    current_player = next((player for player in league_players if player.name.strip().lower() == display_name), None)
    if current_player is None:
        return []

    total_players = len(league_players)
    rows: list[dict[str, Any]] = []
    for index, match in enumerate(matches_data, start=1):
        prediction = current_player.prediction_for(match)
        prediction_value: str | None = None
        is_correct = False

        if prediction is not None and hasattr(prediction, "predicted_outcome"):
            predicted_outcome = str(getattr(prediction, "predicted_outcome", ""))
            if predicted_outcome == "vinst":
                prediction_value = match.home_team
            elif predicted_outcome == "forlust":
                prediction_value = match.away_team
            else:
                prediction_value = "Kryss"
            is_correct = prediction.is_correct()
        elif prediction is not None and hasattr(prediction, "predicted_team"):
            prediction_value = str(getattr(prediction, "predicted_team", ""))
            is_correct = prediction.is_correct()

        correct_count = 0
        for player in league_players:
            candidate = player.prediction_for(match)
            if candidate is not None and candidate.is_correct():
                correct_count += 1

        points_for_match = 0.0
        if is_correct and correct_count > 0:
            points_for_match = total_players / correct_count
        potential_points_if_correct: float | None = None
        if match.home_goals is not None and match.away_goals is not None:
            potential_points_if_correct = total_players / (correct_count + 1) if not is_correct else points_for_match

        if match.home_goals is None or match.away_goals is None:
            facit_text = "Ej spelad"
        elif match.home_goals > match.away_goals:
            facit_text = match.home_team
        elif match.home_goals < match.away_goals:
            facit_text = match.away_team
        else:
            facit_text = "Kryss"

        rows.append(
            {
                "match_id": index,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "result": f"{match.home_goals}-{match.away_goals}" if match.home_goals is not None and match.away_goals is not None else None,
                "facit": facit_text,
                "your_prediction": prediction_value,
                "is_correct": is_correct,
                "points": points_for_match,
                "points_if_correct": potential_points_if_correct,
            }
        )
    return rows


@app.get("/facit/playoff")
def playoff_facit(user: dict[str, Any] = Depends(_require_user)) -> dict[str, Any]:
    _require_predictions_visible()
    league, league_players = _league_players_for_user(user)
    total_players = len(league_players) if league_players else 1
    team_stats = _playoff_team_stats(league_players)
    actual_rounds = _load_playoff_results_rounds()
    all_teams = sorted(_valid_playoff_teams(), key=lambda team: team.lower())

    rounds: list[dict[str, Any]] = []
    for round_key in PLAYOFF_ROUNDS:
        round_stats = team_stats.get(round_key, {})
        teams = []
        for team in actual_rounds.get(round_key, []):
            stats = round_stats.get(team, {"count": 0, "players": []})
            teams.append(
                {
                    "team": team,
                    "picked_count": int(stats.get("count", 0)),
                    "points_awarded": _playoff_points_for_team(total_players, round_stats, team),
                    "players": stats.get("players", []),
                }
            )
        rounds.append(
            {
                "key": round_key,
                "label": PLAYOFF_ROUND_LABELS.get(round_key, round_key),
                "teams": teams,
            }
        )

    team_details: list[dict[str, Any]] = []
    for team in all_teams:
        round_details = []
        for round_key in PLAYOFF_ROUNDS:
            stats = team_stats.get(round_key, {}).get(team, {"count": 0, "players": []})
            round_details.append(
                {
                    "key": round_key,
                    "label": PLAYOFF_ROUND_LABELS.get(round_key, round_key),
                    "picked_count": int(stats.get("count", 0)),
                    "players": stats.get("players", []),
                    "is_correct": team in actual_rounds.get(round_key, []),
                }
            )
        team_details.append({"team": team, "rounds": round_details})

    return {
        "league": league,
        "total_players": total_players,
        "rounds": rounds,
        "teams": team_details,
    }


@app.get("/matches")
def matches(_: dict[str, Any] = Depends(_require_user)) -> list[dict[str, Any]]:
    matches_data, _ = las_fran_json()
    return [
        {
            "id": index,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "home_goals": match.home_goals,
            "away_goals": match.away_goals,
            "advancing_team": match.advancing_team,
        }
        for index, match in enumerate(matches_data, start=1)
    ]


@app.get("/predictions/match/{match_id}")
def predictions_for_match(
    match_id: int,
    user: dict[str, Any] = Depends(_require_user),
) -> list[dict[str, Any]]:
    _require_predictions_visible()
    league = _user_league(user)
    match_row = _hamta_match(match_id)
    home_team = str(match_row.get("home_team", "")).strip()
    away_team = str(match_row.get("away_team", "")).strip()

    players_data = load_players()
    players_by_id: dict[int, str] = {}
    for player in players_data:
        try:
            player_id = int(player.get("id", 0))
        except (TypeError, ValueError):
            continue
        if player_id <= 0:
            continue
        if not _player_row_belongs_to_league(player, league):
            continue
        players_by_id[player_id] = str(player.get("name", "")).strip() or f"Spelare {player_id}"

    raw_rows: list[dict[str, Any]] = []
    for row in load_predictions():
        try:
            row_match_id = int(row.get("match_id", 0))
            player_id = int(row.get("player_id", 0))
        except (TypeError, ValueError):
            continue
        if row_match_id != match_id:
            continue
        if player_id not in players_by_id:
            continue

        prediction_type = str(row.get("type", "")).strip()
        prediction_text = "-"
        prediction_bucket = "-"
        if prediction_type == "gruppspel":
            predicted_outcome = str(row.get("predicted_outcome", "")).strip().lower()
            if predicted_outcome == "vinst":
                prediction_text = home_team
                prediction_bucket = "vinst"
            elif predicted_outcome == "forlust":
                prediction_text = away_team
                prediction_bucket = "forlust"
            elif predicted_outcome == "kryss":
                prediction_text = "Kryss"
                prediction_bucket = "kryss"
        elif prediction_type == "slutspel":
            prediction_text = str(row.get("predicted_team", "")).strip() or "-"
            prediction_bucket = prediction_text

        raw_rows.append(
            {
                "player_id": player_id,
                "player_name": players_by_id.get(player_id, f"Spelare {player_id}"),
                "match_id": match_id,
                "prediction_type": prediction_type,
                "prediction": prediction_text,
                "prediction_bucket": prediction_bucket,
            }
        )

    total_players = len(players_by_id)
    if total_players <= 0:
        total_players = 1

    bucket_counts: dict[str, int] = {}
    for row in raw_rows:
        bucket = str(row.get("prediction_bucket", ""))
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    matches_data, players_data = las_fran_json()
    league_players = _league_player_objects(players_data, league)
    player_objs_by_id = {player_id: player for player_id, player in league_players}
    match = next((candidate for index, candidate in enumerate(matches_data, start=1) if index == match_id), None)
    is_played = bool(match is not None and match.is_played)
    correct_count = 0
    if match is not None:
        for _, player in league_players:
            prediction = player.prediction_for(match)
            if prediction is not None and prediction.is_correct():
                correct_count += 1

    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        bucket = str(row.get("prediction_bucket", ""))
        same_prediction_count = bucket_counts.get(bucket, 0)
        points_if_correct = float(total_players / same_prediction_count) if same_prediction_count > 0 else 0.0
        points_awarded = 0.0

        if is_played:
            row_player_id = int(row.get("player_id", 0))
            current_player = player_objs_by_id.get(row_player_id)
            is_correct = False
            if current_player is not None and match is not None:
                prediction = current_player.prediction_for(match)
                is_correct = bool(prediction is not None and prediction.is_correct())
            if is_correct and correct_count > 0:
                points_awarded = float(total_players / correct_count)
                points_if_correct = points_awarded

        rows.append(
            {
                "player_id": row.get("player_id"),
                "player_name": row.get("player_name"),
                "match_id": row.get("match_id"),
                "prediction_type": row.get("prediction_type"),
                "prediction": row.get("prediction"),
                "points_awarded": points_awarded,
                "points_if_correct": points_if_correct,
                "is_played": is_played,
            }
        )

    rows.sort(key=lambda item: str(item.get("player_name", "")).lower())
    return rows


@app.get("/correct-counts")
def correct_counts(user: dict[str, Any] = Depends(_require_user)) -> list[dict[str, Any]]:
    matches_data, players_data = las_fran_json()
    league = _user_league(user)
    league_players = _league_player_objects(players_data, league)
    playoff_results = _load_playoff_results_rounds()

    rows: list[dict[str, Any]] = []
    for player_id, player in league_players:
        counts = _count_correct_for_player(player, matches_data, playoff_results)
        rows.append(
            {
                "player_id": player_id,
                "name": player.name,
                "match_correct": counts["match_correct"],
                "playoff_correct": counts["playoff_correct"],
                "total_correct": counts["total_correct"],
                "league": league,
            }
        )

    rows.sort(key=lambda item: (-int(item.get("total_correct", 0)), str(item.get("name", "")).lower()))
    for position, row in enumerate(rows, start=1):
        row["position"] = position
    return rows


@app.get("/players")
def players(user: dict[str, Any] = Depends(_require_user)) -> list[dict[str, Any]]:
    matches_data, players_data = las_fran_json()
    league = _user_league(user)
    league_players = _league_player_objects(players_data, league)
    player_objects = [player for _, player in league_players]
    rakna_tabell(matches_data, player_objects)
    return [
        {
            "id": player_id,
            "name": player.name,
            "points": player.points,
            "attondels_lag": player.attondels_lag,
            "slutspel_lag": player.slutspel_lag,
            "league": league,
        }
        for player_id, player in league_players
    ]


@app.get("/table")
def table(user: dict[str, Any] = Depends(_require_user)) -> list[dict[str, Any]]:
    matches_data, players_data = las_fran_json()
    league = _user_league(user)
    league_players = _league_player_objects(players_data, league)
    player_objects = [player for _, player in league_players]
    rakna_tabell(matches_data, player_objects)
    sorted_players_with_ids = sorted(
        league_players,
        key=lambda item: (-item[1].points, item[1].name),
    )
    return [
        {
            "player_id": player_id,
            "position": position,
            "name": player.name,
            "points": player.points,
            "league": league,
        }
        for position, (player_id, player) in enumerate(sorted_players_with_ids, start=1)
    ]


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
