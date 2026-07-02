from __future__ import annotations

import json
import os
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from match import PLAYOFF_ROUNDS


FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"
FINISHED_STATUS = {"FINISHED", "AWARDED"}
ROUND_BY_STAGE = {
    "LAST_32": "attondel",
    "ROUND_OF_32": "attondel",
    "LAST_16": "kvart",
    "ROUND_OF_16": "kvart",
    "QUARTER_FINALS": "semi",
    "QUARTER_FINAL": "semi",
    "SEMI_FINALS": "final",
    "SEMI_FINAL": "final",
    "FINAL": "vinnare",
}
TEAM_ALIASES = {
    "cote divoire": "ivory coast",
    "cote d ivoire": "ivory coast",
    "cote d'ivoire": "ivory coast",
    "curacao": "curacao",
    "curaçao": "curacao",
    "dr congo": "dr congo",
    "congo dr": "dr congo",
    "korea republic": "south korea",
    "republic of korea": "south korea",
    "turkey": "turkiye",
    "türkiye": "turkiye",
    "usa": "united states",
    "united states of america": "united states",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def configured_token() -> str:
    return os.getenv("FOOTBALL_DATA_API_TOKEN", "").strip()


def sync_interval_seconds() -> int:
    raw_value = os.getenv("FOOTBALL_DATA_SYNC_INTERVAL_SECONDS", "900").strip()
    try:
        return max(60, int(raw_value))
    except ValueError:
        return 900


def normalize_team_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("&", "and")
    for char in ("-", ".", ",", "(", ")", "/"):
        text = text.replace(char, " ")
    text = " ".join(text.split())
    return TEAM_ALIASES.get(text, text)


def canonical_team_name(value: Any, valid_teams_by_key: dict[str, str]) -> str | None:
    normalized = normalize_team_name(value)
    return valid_teams_by_key.get(normalized)


def fetch_football_data(path: str, token: str) -> dict[str, Any]:
    base_url = os.getenv("FOOTBALL_DATA_BASE_URL", FOOTBALL_DATA_BASE_URL).rstrip("/")
    request = Request(
        f"{base_url}{path}",
        headers={
            "X-Auth-Token": token,
            "Accept": "application/json",
            "User-Agent": "vm-tippning/0.1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"football-data.org svarade HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Kunde inte na football-data.org: {error.reason}") from error

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise RuntimeError("football-data.org skickade ett ovantat svar")
    return data


def valid_teams_by_key(matches: list[dict[str, Any]]) -> dict[str, str]:
    teams: dict[str, str] = {}
    for row in matches:
        for field in ("home_team", "away_team"):
            team = str(row.get(field, "")).strip()
            if team:
                teams[normalize_team_name(team)] = team
    return teams


def match_key(home_team: Any, away_team: Any) -> tuple[str, str]:
    return (normalize_team_name(home_team), normalize_team_name(away_team))


def index_local_matches(matches: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in matches:
        indexed[match_key(row.get("home_team"), row.get("away_team"))] = row
    return indexed


def full_time_score(api_match: dict[str, Any]) -> tuple[int | None, int | None]:
    score = api_match.get("score")
    if not isinstance(score, dict):
        return None, None
    full_time = score.get("fullTime")
    if not isinstance(full_time, dict):
        return None, None
    home_goals = full_time.get("home")
    away_goals = full_time.get("away")
    if isinstance(home_goals, int) and isinstance(away_goals, int):
        return home_goals, away_goals
    return None, None


def external_team(api_match: dict[str, Any], side: str) -> str:
    team = api_match.get(side)
    if isinstance(team, dict):
        return str(team.get("name") or team.get("shortName") or team.get("tla") or "").strip()
    return ""


def advancing_team_from_match(
    api_match: dict[str, Any],
    local_row: dict[str, Any],
) -> str | None:
    score = api_match.get("score")
    winner = score.get("winner") if isinstance(score, dict) else None
    if winner == "HOME_TEAM":
        return str(local_row.get("home_team", "")).strip() or None
    if winner == "AWAY_TEAM":
        return str(local_row.get("away_team", "")).strip() or None
    return None


def update_matches_from_api(
    local_matches: list[dict[str, Any]],
    api_matches: list[dict[str, Any]],
) -> dict[str, int]:
    local_by_key = index_local_matches(local_matches)
    changed = 0
    matched = 0

    for api_match in api_matches:
        status = str(api_match.get("status", "")).upper()
        if status not in FINISHED_STATUS:
            continue
        local_row = local_by_key.get(match_key(external_team(api_match, "homeTeam"), external_team(api_match, "awayTeam")))
        if local_row is None:
            continue

        home_goals, away_goals = full_time_score(api_match)
        if home_goals is None or away_goals is None:
            continue

        matched += 1
        advancing_team = advancing_team_from_match(api_match, local_row)
        updates = {
            "home_goals": home_goals,
            "away_goals": away_goals,
            "advancing_team": advancing_team,
        }
        if any(local_row.get(key) != value for key, value in updates.items()):
            local_row.update(updates)
            changed += 1

    return {"matched_finished_matches": matched, "updated_matches": changed}


def schedule_rows_from_api(
    local_matches: list[dict[str, Any]],
    api_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    local_by_key = index_local_matches(local_matches)
    valid_teams = valid_teams_by_key(local_matches)
    rows: list[dict[str, Any]] = []
    for api_match in api_matches:
        home_team = external_team(api_match, "homeTeam")
        away_team = external_team(api_match, "awayTeam")
        local_row = local_by_key.get(match_key(home_team, away_team))
        home_name = (
            str(local_row.get("home_team", "")).strip()
            if local_row
            else canonical_team_name(home_team, valid_teams) or home_team
        )
        away_name = (
            str(local_row.get("away_team", "")).strip()
            if local_row
            else canonical_team_name(away_team, valid_teams) or away_team
        )
        home_goals, away_goals = full_time_score(api_match)
        rows.append(
            {
                "external_id": api_match.get("id"),
                "local_match_id": local_row.get("id") if local_row else None,
                "utc_date": api_match.get("utcDate"),
                "status": api_match.get("status"),
                "stage": api_match.get("stage"),
                "group": api_match.get("group"),
                "matchday": api_match.get("matchday"),
                "home_team": home_name,
                "away_team": away_name,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "last_synced_at": utc_now_iso(),
            }
        )
    return sorted(rows, key=lambda row: str(row.get("utc_date") or ""))


def empty_playoff_rounds() -> dict[str, list[str]]:
    return {round_key: [] for round_key in PLAYOFF_ROUNDS}


def standings_table_complete(table: list[dict[str, Any]]) -> bool:
    if len(table) < 4:
        return False
    for row in table:
        try:
            if int(row.get("playedGames", 0)) < 3:
                return False
        except (TypeError, ValueError):
            return False
    return True


def standing_sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
    team = row.get("team") if isinstance(row.get("team"), dict) else {}
    return (
        int(row.get("points", 0) or 0),
        int(row.get("goalDifference", 0) or 0),
        int(row.get("goalsFor", 0) or 0),
        str(team.get("name", "")).lower(),
    )


def group_qualifiers_from_standings(
    standings: dict[str, Any],
    valid_teams: dict[str, str],
) -> list[str]:
    direct_qualifiers: list[str] = []
    third_place_rows: list[dict[str, Any]] = []

    for standing in standings.get("standings", []):
        if not isinstance(standing, dict) or str(standing.get("type", "")).upper() != "TOTAL":
            continue
        table = standing.get("table", [])
        if not isinstance(table, list) or not standings_table_complete(table):
            continue

        ordered_table = sorted(table, key=lambda row: int(row.get("position", 999) or 999))
        for row in ordered_table[:2]:
            team = row.get("team") if isinstance(row.get("team"), dict) else {}
            canonical = canonical_team_name(team.get("name"), valid_teams)
            if canonical:
                direct_qualifiers.append(canonical)
        if len(ordered_table) >= 3:
            third_place_rows.append(ordered_table[2])

    best_thirds = sorted(third_place_rows, key=standing_sort_key, reverse=True)[:8]
    third_qualifiers: list[str] = []
    for row in best_thirds:
        team = row.get("team") if isinstance(row.get("team"), dict) else {}
        canonical = canonical_team_name(team.get("name"), valid_teams)
        if canonical:
            third_qualifiers.append(canonical)

    return unique_teams(direct_qualifiers + third_qualifiers)


def unique_teams(teams: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for team in teams:
        normalized = normalize_team_name(team)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(team)
    return unique


def update_round_from_finished_knockouts(
    rounds: dict[str, list[str]],
    api_matches: list[dict[str, Any]],
    valid_teams: dict[str, str],
) -> None:
    for api_match in api_matches:
        status = str(api_match.get("status", "")).upper()
        if status not in FINISHED_STATUS:
            continue
        stage = str(api_match.get("stage", "")).upper()
        round_key = ROUND_BY_STAGE.get(stage)
        if round_key is None:
            continue
        score = api_match.get("score")
        winner = score.get("winner") if isinstance(score, dict) else None
        winning_side = "homeTeam" if winner == "HOME_TEAM" else "awayTeam" if winner == "AWAY_TEAM" else ""
        if not winning_side:
            continue
        canonical = canonical_team_name(external_team(api_match, winning_side), valid_teams)
        if canonical and canonical not in rounds[round_key]:
            rounds[round_key].append(canonical)


def calculate_playoff_rounds(
    local_matches: list[dict[str, Any]],
    api_matches: list[dict[str, Any]],
    standings: dict[str, Any] | None,
) -> dict[str, list[str]]:
    valid_teams = valid_teams_by_key(local_matches)
    rounds = empty_playoff_rounds()
    if standings:
        rounds["sextondel"] = group_qualifiers_from_standings(standings, valid_teams)[:32]
    update_round_from_finished_knockouts(rounds, api_matches, valid_teams)

    previous = set(valid_teams.values())
    for round_key in PLAYOFF_ROUNDS:
        rounds[round_key] = [team for team in unique_teams(rounds[round_key]) if team in previous]
        previous = set(rounds[round_key])
    return rounds


def merge_playoff_rounds(
    current_rounds: dict[str, list[str]],
    automatic_rounds: dict[str, list[str]],
) -> dict[str, list[str]]:
    merged = empty_playoff_rounds()
    previous_allowed: set[str] | None = None
    for round_key in PLAYOFF_ROUNDS:
        automatic = automatic_rounds.get(round_key, [])
        current = current_rounds.get(round_key, [])
        selected = automatic if automatic else current
        if previous_allowed is not None:
            selected = [team for team in selected if team in previous_allowed]
        merged[round_key] = unique_teams(selected)
        previous_allowed = set(merged[round_key])
    return merged
