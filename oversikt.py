from __future__ import annotations

from typing import Iterable, Protocol, Sequence


class MatchLike(Protocol):
    home_team: str
    away_team: str
    home_goals: int | None
    away_goals: int | None
    advancing_team: str | None


def _resultat_text(match: MatchLike) -> str:
    if match.home_goals is None or match.away_goals is None:
        return "Inte spelad"
    return f"{match.home_goals}-{match.away_goals}"


def skriv_ut_matchlista(matches: Iterable[MatchLike], rubrik: str = "Matchlista") -> None:
    print(rubrik)
    print("Nr | Match                     | Resultat | Vidare")
    print("----------------------------------------------------")
    for index, match in enumerate(matches, start=1):
        match_text = f"{match.home_team} - {match.away_team}"
        vidare = "-" if match.advancing_team is None else match.advancing_team
        print(f"{index:>2} | {match_text:<25} | {_resultat_text(match):<8} | {vidare}")


def skriv_ut_slutspelstrad(rundor: Sequence[tuple[str, Sequence[MatchLike]]]) -> None:
    print("Slutspelstrad")
    print("====================================================")
    for runda_namn, matcher in rundor:
        print(f"[{runda_namn}]")
        for index, match in enumerate(matcher, start=1):
            match_text = f"{match.home_team} - {match.away_team}"
            resultat = _resultat_text(match)
            vidare = "-" if match.advancing_team is None else match.advancing_team
            print(f"  {index}. {match_text} ({resultat}) -> {vidare}")
        print()
