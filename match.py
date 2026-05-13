from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from databas import (
    ensure_storage,
    load_matches,
    load_players,
    load_playoff_results,
    load_predictions,
    save_matches,
    save_players,
    save_predictions,
)
from oversikt import skriv_ut_matchlista, skriv_ut_slutspelstrad
from tabell import skriv_ut_attondelstips, skriv_ut_tabell, skriv_ut_tippningar_for_match

PLAYOFF_ROUNDS = ("sextondel", "attondel", "kvart", "semi", "final", "vinnare")


@dataclass
class Match:
    home_team: str
    away_team: str
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    advancing_team: Optional[str] = None

    def set_result(
        self, home_goals: int, away_goals: int, advancing_team: Optional[str] = None
    ) -> None:
        if home_goals < 0 or away_goals < 0:
            raise ValueError("Mal kan inte vara negativa")
        self.home_goals = home_goals
        self.away_goals = away_goals
        if advancing_team is not None:
            self.set_advancing_team(advancing_team)

    def set_advancing_team(self, team: str) -> None:
        if team not in {self.home_team, self.away_team}:
            raise ValueError("Lag som gar vidare maste vara ett av lagen i matchen")
        self.advancing_team = team

    @property
    def is_played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None

    def outcome(self) -> Optional[str]:
        if not self.is_played:
            return None
        if self.home_goals > self.away_goals:
            return "vinst"
        if self.home_goals < self.away_goals:
            return "forlust"
        return "kryss"


@dataclass
class Tippning:
    match: Match
    predicted_outcome: str  # "vinst", "kryss", "forlust"

    VALID_OUTCOMES = {"vinst", "kryss", "forlust"}

    def __post_init__(self) -> None:
        if self.predicted_outcome not in self.VALID_OUTCOMES:
            raise ValueError("Ogiltig tippning. Anvand: vinst, kryss eller forlust")

    def is_correct(self) -> bool:
        return self.match.is_played and self.predicted_outcome == self.match.outcome()


class Prediction(Protocol):
    match: Match

    def is_correct(self) -> bool:
        ...


@dataclass
class Slutspelstippning:
    match: Match
    predicted_team: str

    def __post_init__(self) -> None:
        if self.predicted_team not in {self.match.home_team, self.match.away_team}:
            raise ValueError("Du maste tippa pa ett av lagen i matchen")

    def is_correct(self) -> bool:
        return self.match.advancing_team is not None and (
            self.predicted_team == self.match.advancing_team
        )


@dataclass
class Spelare:
    name: str
    predictions: List[Prediction] = field(default_factory=list)
    attondels_lag: List[str] = field(default_factory=list)
    slutspel_lag: Dict[str, List[str]] = field(default_factory=dict)
    points: float = 0.0

    def add_prediction(self, prediction: Prediction) -> None:
        if any(existing.match is prediction.match for existing in self.predictions):
            raise ValueError("Spelaren har redan tippat den har matchen")
        self.predictions.append(prediction)

    def prediction_for(self, match: Match) -> Optional[Prediction]:
        for prediction in self.predictions:
            if prediction.match is match:
                return prediction
        return None

    def set_attondels_lag(self, teams: List[str]) -> None:
        if self.attondels_lag:
            raise ValueError("Spelaren har redan skickat in sin attondelsfinaltippning")
        if len(teams) != 16:
            raise ValueError("Attondelslista maste innehalla exakt 16 lag")
        if len(set(teams)) != len(teams):
            raise ValueError("Attondelslista far inte innehalla dubletter")
        self.attondels_lag = list(teams)


def dela_ut_poang_for_match(match: Match, players: List[Spelare]) -> None:
    if not players:
        return

    correct_players: List[Spelare] = []
    for player in players:
        prediction = player.prediction_for(match)
        if prediction and prediction.is_correct():
            correct_players.append(player)

    if not correct_players:
        return

    points_per_correct_player = len(players) / len(correct_players)
    for player in correct_players:
        player.points += points_per_correct_player


def rakna_tabell(matches: List[Match], players: List[Spelare]) -> None:
    for player in players:
        player.points = 0.0
    for match in matches:
        dela_ut_poang_for_match(match, players)
    dela_ut_poang_for_slutspel(hamta_slutspelsfacit(), players)


def dela_ut_poang_for_attondelslista(correct_teams: List[str], players: List[Spelare]) -> None:
    if not players:
        return

    for team in correct_teams:
        players_with_team = [player for player in players if team in player.attondels_lag]
        if not players_with_team:
            continue
        points_per_player = len(players) / len(players_with_team)
        for player in players_with_team:
            player.points += points_per_player


def dela_ut_poang_for_slutspel(correct_rounds: Dict[str, List[str]], players: List[Spelare]) -> None:
    if not players:
        return

    for round_key in PLAYOFF_ROUNDS:
        correct_teams = correct_rounds.get(round_key, [])
        for team in correct_teams:
            players_with_team = [
                player
                for player in players
                if team in player.slutspel_lag.get(round_key, [])
            ]
            if not players_with_team:
                continue
            points_per_player = len(players) / len(players_with_team)
            for player in players_with_team:
                player.points += points_per_player


def hamta_slutspelsfacit() -> Dict[str, List[str]]:
    correct_rounds: Dict[str, List[str]] = {round_key: [] for round_key in PLAYOFF_ROUNDS}
    for row in load_playoff_results():
        round_key = str(row.get("round", "")).strip().lower()
        if round_key not in correct_rounds:
            continue
        teams = row.get("teams", [])
        if not isinstance(teams, list):
            continue
        correct_rounds[round_key] = [str(team).strip() for team in teams if str(team).strip()]
    return correct_rounds


def rakna_tabell_med_attondelslista(
    matches: List[Match], players: List[Spelare], attondelslag: List[str]
) -> None:
    rakna_tabell(matches, players)
    dela_ut_poang_for_attondelslista(attondelslag, players)


def spara_till_json(matches: List[Match], players: List[Spelare]) -> None:
    ensure_storage()

    match_ids: dict[int, int] = {}
    match_rows = []
    for match_id, match in enumerate(matches, start=1):
        match_ids[id(match)] = match_id
        match_rows.append(
            {
                "id": match_id,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "home_goals": match.home_goals,
                "away_goals": match.away_goals,
                "advancing_team": match.advancing_team,
            }
        )

    player_rows = []
    prediction_rows = []
    for player_id, player in enumerate(players, start=1):
        player_rows.append(
            {
                "id": player_id,
                "name": player.name,
                "points": player.points,
                "attondels_lag": player.attondels_lag,
                "slutspel_lag": player.slutspel_lag,
            }
        )
        for prediction in player.predictions:
            row = {
                "player_id": player_id,
                "match_id": match_ids.get(id(prediction.match)),
            }
            if isinstance(prediction, Tippning):
                row["type"] = "gruppspel"
                row["predicted_outcome"] = prediction.predicted_outcome
            elif isinstance(prediction, Slutspelstippning):
                row["type"] = "slutspel"
                row["predicted_team"] = prediction.predicted_team
            else:
                continue
            prediction_rows.append(row)

    save_matches(match_rows)
    save_players(player_rows)
    save_predictions(prediction_rows)


def las_fran_json() -> tuple[List[Match], List[Spelare]]:
    ensure_storage()

    match_rows = load_matches()
    player_rows = load_players()
    prediction_rows = load_predictions()

    matches_by_id: dict[int, Match] = {}
    sorted_match_rows = sorted(match_rows, key=lambda row: int(row.get("id", 0)))
    for row in sorted_match_rows:
        match_id = int(row.get("id", 0))
        if match_id <= 0:
            continue
        match = Match(
            home_team=str(row.get("home_team", "")),
            away_team=str(row.get("away_team", "")),
        )
        home_goals = row.get("home_goals")
        away_goals = row.get("away_goals")
        advancing_team = row.get("advancing_team")
        if isinstance(home_goals, int) and isinstance(away_goals, int):
            if isinstance(advancing_team, str) and advancing_team:
                match.set_result(home_goals, away_goals, advancing_team=advancing_team)
            else:
                match.set_result(home_goals, away_goals)
        elif isinstance(advancing_team, str) and advancing_team:
            match.set_advancing_team(advancing_team)
        matches_by_id[match_id] = match

    players_by_id: dict[int, Spelare] = {}
    sorted_player_rows = sorted(player_rows, key=lambda row: int(row.get("id", 0)))
    for row in sorted_player_rows:
        player_id = int(row.get("id", 0))
        if player_id <= 0:
            continue
        player = Spelare(name=str(row.get("name", "")))
        points_value = row.get("points", 0.0)
        try:
            player.points = float(points_value)
        except (TypeError, ValueError):
            player.points = 0.0
        attondels_lag = row.get("attondels_lag", [])
        if isinstance(attondels_lag, list):
            player.attondels_lag = [str(team) for team in attondels_lag]
        slutspel_lag = row.get("slutspel_lag", {})
        if isinstance(slutspel_lag, dict):
            player.slutspel_lag = {
                round_key: [
                    str(team).strip()
                    for team in slutspel_lag.get(round_key, [])
                    if str(team).strip()
                ]
                for round_key in PLAYOFF_ROUNDS
                if isinstance(slutspel_lag.get(round_key, []), list)
            }
        players_by_id[player_id] = player

    for row in prediction_rows:
        player_id = int(row.get("player_id", 0))
        match_id = int(row.get("match_id", 0))
        player = players_by_id.get(player_id)
        match = matches_by_id.get(match_id)
        if player is None or match is None:
            continue

        prediction_type = str(row.get("type", ""))
        try:
            if prediction_type == "gruppspel":
                predicted_outcome = str(row.get("predicted_outcome", ""))
                player.add_prediction(Tippning(match, predicted_outcome))
            elif prediction_type == "slutspel":
                predicted_team = str(row.get("predicted_team", ""))
                player.add_prediction(Slutspelstippning(match, predicted_team))
        except ValueError:
            continue

    matches = [matches_by_id[match_id] for match_id in sorted(matches_by_id)]
    players = [players_by_id[player_id] for player_id in sorted(players_by_id)]
    return matches, players


if __name__ == "__main__":
    gruppmatch = Match("Sverige", "Tyskland")
    gruppmatch.set_result(2, 1)

    attondel = Match("Frankrike", "Danmark")
    attondel.set_result(1, 1, advancing_team="Danmark")
    kvartsfinal = Match("Danmark", "England")
    kvartsfinal.set_result(0, 2, advancing_team="England")
    semifinal = Match("England", "Spanien")
    semifinal.set_result(1, 0, advancing_team="England")
    final = Match("England", "Brasilien")
    final.set_result(2, 2, advancing_team="Brasilien")

    anna = Spelare("Anna")
    bo = Spelare("Bo")
    clara = Spelare("Clara")
    david = Spelare("David")

    anna.add_prediction(Tippning(gruppmatch, "vinst"))
    bo.add_prediction(Tippning(gruppmatch, "forlust"))
    clara.add_prediction(Tippning(gruppmatch, "forlust"))
    david.add_prediction(Tippning(gruppmatch, "vinst"))

    anna.set_attondels_lag(
        [
            "Argentina",
            "Brasilien",
            "England",
            "Frankrike",
            "Spanien",
            "Portugal",
            "Tyskland",
            "Nederlanderna",
            "Belgien",
            "Danmark",
            "Uruguay",
            "Kroatien",
            "USA",
            "Mexiko",
            "Japan",
            "Sverige",
        ]
    )
    bo.set_attondels_lag(
        [
            "Argentina",
            "Brasilien",
            "England",
            "Frankrike",
            "Spanien",
            "Portugal",
            "Tyskland",
            "Danmark",
            "Schweiz",
            "Serbien",
            "Uruguay",
            "Kroatien",
            "USA",
            "Mexiko",
            "Sydkorea",
            "Polen",
        ]
    )
    clara.set_attondels_lag(
        [
            "Argentina",
            "Brasilien",
            "England",
            "Frankrike",
            "Spanien",
            "Portugal",
            "Nederlanderna",
            "Danmark",
            "Belgien",
            "Senegal",
            "Uruguay",
            "Kroatien",
            "USA",
            "Japan",
            "Sverige",
            "Marocko",
        ]
    )
    david.set_attondels_lag(
        [
            "Argentina",
            "Brasilien",
            "England",
            "Frankrike",
            "Spanien",
            "Portugal",
            "Tyskland",
            "Nederlanderna",
            "Belgien",
            "Danmark",
            "Uruguay",
            "Kroatien",
            "USA",
            "Mexiko",
            "Japan",
            "Nigeria",
        ]
    )

    players = [anna, bo, clara, david]
    korrekta_attondelslag = [
        "Argentina",
        "Brasilien",
        "England",
        "Frankrike",
        "Spanien",
        "Portugal",
        "Tyskland",
        "Nederlanderna",
        "Belgien",
        "Danmark",
        "Uruguay",
        "Kroatien",
        "USA",
        "Mexiko",
        "Japan",
        "Sverige",
    ]
    rakna_tabell_med_attondelslista([gruppmatch], players, korrekta_attondelslag)
    spara_till_json([gruppmatch, attondel, kvartsfinal, semifinal, final], players)
    skriv_ut_tabell(players)
    print()
    skriv_ut_tippningar_for_match(gruppmatch, players)
    print()
    skriv_ut_attondelstips(players, korrekta_attondelslag)
    print()
    skriv_ut_matchlista([gruppmatch, attondel, kvartsfinal, semifinal, final])
    print()
    skriv_ut_slutspelstrad(
        [
            ("Attondelsfinal", [attondel]),
            ("Kvartsfinal", [kvartsfinal]),
            ("Semifinal", [semifinal]),
            ("Final", [final]),
        ]
    )
