from __future__ import annotations

from typing import List, Protocol


class MatchLike(Protocol):
    home_team: str
    away_team: str


class PredictionLike(Protocol):
    match: MatchLike

    def is_correct(self) -> bool:
        ...


class PlayerLike(Protocol):
    name: str
    points: float
    attondels_lag: List[str]

    def prediction_for(self, match: MatchLike) -> PredictionLike | None:
        ...


def hamta_tabell(players: List[PlayerLike]) -> List[PlayerLike]:
    return sorted(players, key=lambda player: (-player.points, player.name))


def skriv_ut_tabell(players: List[PlayerLike]) -> None:
    total_summa = sum(player.points for player in players)

    print("Tabell")
    print("Plats | Namn       | Summa")
    print("---------------------------")
    for index, player in enumerate(hamta_tabell(players), start=1):
        print(f"{index:>5} | {player.name:<10} | {player.points:.1f}")
    print("---------------------------")
    print(f"Totalt utdelat: {total_summa:.1f}")


def _prediction_text(prediction: PredictionLike) -> str:
    if hasattr(prediction, "predicted_outcome"):
        return str(getattr(prediction, "predicted_outcome"))
    if hasattr(prediction, "predicted_team"):
        return str(getattr(prediction, "predicted_team"))
    return "-"


def skriv_ut_tippningar_for_match(match: MatchLike, players: List[PlayerLike]) -> None:
    correct_players = 0
    for player in players:
        prediction = player.prediction_for(match)
        if prediction and prediction.is_correct():
            correct_players += 1

    points_if_correct = 0.0
    if correct_players > 0:
        points_if_correct = len(players) / correct_players

    print(f"Tippningar for match: {match.home_team} - {match.away_team}")
    print("Namn       | Tippning   | Ratt | Poang")
    print("----------------------------------------")
    for player in sorted(players, key=lambda p: p.name):
        prediction = player.prediction_for(match)
        prediction_text = "-" if prediction is None else _prediction_text(prediction)
        is_correct = prediction is not None and prediction.is_correct()
        points = points_if_correct if is_correct else 0.0
        yes_no = "Ja" if is_correct else "Nej"
        print(f"{player.name:<10} | {prediction_text:<10} | {yes_no:<4} | {points:.1f}")


def skriv_ut_attondelstips(players: List[PlayerLike], korrekta_attondelslag: List[str]) -> None:
    correct_set = set(korrekta_attondelslag)
    print("Attondelsfinal-tips")
    print("Namn       | Antal ratt | Tippade lag")
    print("--------------------------------------------------------------------------")

    for player in sorted(players, key=lambda p: p.name):
        tipped_teams = list(player.attondels_lag)
        correct_count = sum(1 for team in tipped_teams if team in correct_set)
        tips_text = "-" if not tipped_teams else ", ".join(tipped_teams)
        print(f"{player.name:<10} | {correct_count:^10} | {tips_text}")
