from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from auth import (
    byt_losenord_med_token,
    hamta_anvandare_fran_token,
    logga_in,
    logga_ut,
    skapa_anvandare,
)
from match import las_fran_json, rakna_tabell
from databas import (
    find_user_by_display_name,
    find_user_by_email,
    load_matches,
    load_players,
    load_predictions,
    save_players,
    save_predictions,
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


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    display_name: str = Field(min_length=2)
    role: str = Field(default="user")
    must_change_password: bool = Field(default=False)


class CreateGroupPredictionRequest(BaseModel):
    match_id: int = Field(gt=0)
    predicted_outcome: str = Field(min_length=1)


class CreatePlayoffPredictionRequest(BaseModel):
    match_id: int = Field(gt=0)
    predicted_team: str = Field(min_length=1)


class SavePlayoffTeamsRequest(BaseModel):
    teams: list[str] = Field(default_factory=list)


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


def _hamta_match(match_id: int) -> dict[str, Any]:
    matches_data = load_matches()
    match_row = next((row for row in matches_data if int(row.get("id", 0)) == match_id), None)
    if match_row is None:
        raise HTTPException(status_code=404, detail="Matchen hittades inte")
    return match_row


def _hamta_eller_skapa_player_id(user: dict[str, Any]) -> int:
    players_data = load_players()
    user_display_name = str(user.get("display_name", "")).strip()
    if not user_display_name:
        raise HTTPException(status_code=400, detail="Anvandaren saknar display_name")

    player_row = next(
        (row for row in players_data if str(row.get("name", "")).strip().lower() == user_display_name.lower()),
        None,
    )
    if player_row is not None:
        return int(player_row.get("id", 0))

    next_player_id = 1
    for row in players_data:
        try:
            next_player_id = max(next_player_id, int(row.get("id", 0)) + 1)
        except (TypeError, ValueError):
            continue

    new_player = {"id": next_player_id, "name": user_display_name, "points": 0.0, "attondels_lag": []}
    players_data.append(new_player)
    save_players(players_data)
    return next_player_id


def _hamta_player_id(user: dict[str, Any]) -> int | None:
    players_data = load_players()
    user_display_name = str(user.get("display_name", "")).strip().lower()
    if not user_display_name:
        return None
    for row in players_data:
        player_name = str(row.get("name", "")).strip().lower()
        if player_name != user_display_name:
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    result = logga_in(payload.email, payload.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Fel e-post eller losenord")
    user = result.get("user", {})
    if user.get("role") == "admin" and user.get("must_change_password"):
        result["next_endpoint"] = "/change-password"
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
    _: dict[str, Any] = Depends(_require_user),
) -> dict[str, Any]:
    players_data = load_players()
    player_row: dict[str, Any] | None = None
    for row in players_data:
        try:
            current_player_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if current_player_id == player_id:
            player_row = row
            break
    if player_row is None:
        raise HTTPException(status_code=404, detail="Spelaren hittades inte")

    matches_data, player_objects = las_fran_json()
    current_player = None
    if 1 <= player_id <= len(player_objects):
        current_player = player_objects[player_id - 1]
    if current_player is None:
        raise HTTPException(status_code=404, detail="Spelarens tippningar hittades inte")

    total_players = len(player_objects) if player_objects else 1

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
        for player in player_objects:
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
        "predictions": rows,
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


@app.post("/playoff-teams/me")
def save_playoff_teams(
    payload: SavePlayoffTeamsRequest,
    user: dict[str, Any] = Depends(_require_user),
) -> dict[str, list[str]]:
    player_id = _hamta_eller_skapa_player_id(user)
    unique_teams: list[str] = []
    seen: set[str] = set()
    for team in payload.teams:
        normalized = str(team).strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_teams.append(normalized)

    matches_data = load_matches()
    valid_teams: set[str] = set()
    for row in matches_data:
        home_team = str(row.get("home_team", "")).strip()
        away_team = str(row.get("away_team", "")).strip()
        if home_team:
            valid_teams.add(home_team)
        if away_team:
            valid_teams.add(away_team)

    invalid_teams = [team for team in unique_teams if team not in valid_teams]
    if invalid_teams:
        raise HTTPException(status_code=400, detail=f"Ogiltiga lag: {', '.join(invalid_teams)}")
    if len(unique_teams) > 4:
        raise HTTPException(status_code=400, detail="Du kan valja max 4 lag till slutspel")

    players_data = load_players()
    updated = False
    for row in players_data:
        try:
            current_player_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        if current_player_id != player_id:
            continue
        row["attondels_lag"] = unique_teams
        updated = True
        break

    if not updated:
        raise HTTPException(status_code=404, detail="Spelaren hittades inte")

    save_players(players_data)
    return {"teams": unique_teams}


@app.get("/facit/me")
def my_facit(user: dict[str, Any] = Depends(_require_user)) -> list[dict[str, Any]]:
    matches_data, players_data = las_fran_json()
    player_objs_by_id = {index: player for index, player in enumerate(players_data, start=1)}
    display_name = str(user.get("display_name", "")).strip().lower()
    if not display_name:
        return []

    current_player = next((player for player in players_data if player.name.strip().lower() == display_name), None)
    if current_player is None:
        return []

    total_players = len(players_data)
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
        for player in players_data:
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
    _: dict[str, Any] = Depends(_require_user),
) -> list[dict[str, Any]]:
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
    player_objs_by_id = {index: player for index, player in enumerate(players_data, start=1)}
    match = next((candidate for index, candidate in enumerate(matches_data, start=1) if index == match_id), None)
    is_played = bool(match is not None and match.is_played)
    correct_count = 0
    if match is not None:
        for player in players_data:
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


@app.get("/players")
def players(_: dict[str, Any] = Depends(_require_user)) -> list[dict[str, Any]]:
    matches_data, players_data = las_fran_json()
    rakna_tabell(matches_data, players_data)
    return [
        {
            "id": index,
            "name": player.name,
            "points": player.points,
            "attondels_lag": player.attondels_lag,
        }
        for index, player in enumerate(players_data, start=1)
    ]


@app.get("/table")
def table(_: dict[str, Any] = Depends(_require_user)) -> list[dict[str, Any]]:
    matches_data, players_data = las_fran_json()
    rakna_tabell(matches_data, players_data)
    sorted_players_with_ids = sorted(
        enumerate(players_data, start=1),
        key=lambda item: (-item[1].points, item[1].name),
    )
    return [
        {
            "player_id": player_id,
            "position": position,
            "name": player.name,
            "points": player.points,
        }
        for position, (player_id, player) in enumerate(sorted_players_with_ids, start=1)
    ]
