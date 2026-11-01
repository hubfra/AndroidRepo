"""Atrapa API-Football do testów lokalnych (bez klucza i bez zużywania limitu).

Generuje deterministyczne, zmyślone terminarze i statystyki w tym samym formacie,
w jakim zwraca je prawdziwe API v3.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TEAMS = {
    39: ["Arsenal", "Chelsea", "Liverpool", "Manchester City", "Manchester United", "Tottenham",
         "Newcastle", "Aston Villa", "Brighton", "West Ham"],
    140: ["Real Madrid", "Barcelona", "Atletico Madrid", "Sevilla", "Real Sociedad", "Villarreal",
          "Athletic Club", "Real Betis", "Valencia", "Girona"],
    135: ["Inter", "AC Milan", "Juventus", "Napoli", "AS Roma", "Lazio", "Atalanta", "Fiorentina",
          "Bologna", "Torino"],
    78: ["Bayern Monachium", "Borussia Dortmund", "RB Lipsk", "Bayer Leverkusen", "Eintracht Frankfurt",
         "VfB Stuttgart", "SC Freiburg", "Wolfsburg", "Borussia M'gladbach", "Union Berlin"],
    61: ["Paris Saint Germain", "Marseille", "Monaco", "Lyon", "Lille", "Nice", "Lens", "Rennes",
         "Nantes", "Strasbourg"],
}
STAT_TYPES = ["Shots on Goal", "Total Shots", "Fouls", "Corner Kicks", "Offsides",
              "Yellow Cards", "Red Cards", "Ball Possession"]


class MockApi:
    def __init__(self, config: dict):
        self.tz = ZoneInfo(config["timezone"])
        self.used = 0
        self.remaining_today = "mock"
        self.target = None
        self._fixtures: dict[int, dict] = {}

    # Każdy sezon: 18 kolejek (każdy z każdym u siebie i na wyjeździe), co tydzień.
    def _season(self, league_id: int, season: int) -> list[dict]:
        teams = TEAMS[league_id]
        rnd = random.Random(league_id * 10000 + season)
        names = teams[:]
        rnd.shuffle(names)
        n = len(names)
        rounds = []
        arr = list(range(n))
        for r in range(n - 1):
            pairs = [(arr[i], arr[n - 1 - i]) for i in range(n // 2)]
            rounds.append(pairs if r % 2 == 0 else [(b, a) for a, b in pairs])
            arr = [arr[0]] + [arr[-1]] + arr[1:-1]
        rounds += [[(b, a) for a, b in rd] for rd in rounds]
        # Kolejka nr K bieżącego sezonu wypada w dniu docelowym.
        target = self.target
        current = target.year if target.month >= 7 else target.year - 1
        k = 12
        first = datetime(target.year, target.month, target.day, tzinfo=self.tz) - timedelta(weeks=k)
        first -= timedelta(weeks=52 * (current - season))
        out = []
        for r, rd in enumerate(rounds):
            day = first + timedelta(weeks=r)
            for m, (h, a) in enumerate(rd):
                kick = day.replace(hour=[13, 15, 15, 18, 21][m % 5], minute=[30, 0, 0, 30, 0][m % 5])
                fid = int(f"{league_id}{season}{r:02d}{m}")
                finished = kick.date() < target
                hid = league_id * 100 + teams.index(names[h])
                aid = league_id * 100 + teams.index(names[a])
                frnd = random.Random(fid)
                f = {
                    "fixture": {"id": fid, "date": kick.isoformat(), "timestamp": int(kick.timestamp()),
                                "status": {"short": "FT" if finished else "NS"}},
                    "league": {"id": league_id, "season": season, "round": f"Regular Season - {r + 1}",
                               "logo": None},
                    "teams": {"home": {"id": hid, "name": names[h], "logo": None},
                              "away": {"id": aid, "name": names[a], "logo": None}},
                    "goals": {"home": frnd.randint(0, 4) if finished else None,
                              "away": frnd.randint(0, 3) if finished else None},
                }
                if finished:
                    f["statistics"] = [
                        {"team": {"id": tid}, "statistics": [
                            {"type": t, "value": (f"{frnd.randint(35, 65)}%" if t == "Ball Possession"
                                                  else max(0, int(frnd.gauss(base, 2.5))))}
                            for t, base in zip(STAT_TYPES, [4, 12, 11, 5 + bonus, 2, 2, 0, 0])]}
                        for tid, bonus in ((hid, 1 + (hid % 7) / 3), (aid, (aid % 5) / 3))
                    ]
                self._fixtures[fid] = f
                out.append(f)
        return out

    def get(self, path: str, **params) -> list:
        self.used += 1
        strip = lambda f: {k: v for k, v in f.items() if k != "statistics"}
        if path == "/fixtures" and "date" in params:
            d = datetime.fromisoformat(params["date"]).date()
            self.target = d
            season = d.year if d.month >= 7 else d.year - 1
            res = []
            for lid in TEAMS:
                res += [strip(f) for f in self._season(lid, season)
                        if datetime.fromisoformat(f["fixture"]["date"]).date() == d]
            return res
        if path == "/fixtures" and "league" in params:
            return [strip(f) for f in self._season(int(params["league"]), int(params["season"]))]
        if path == "/fixtures" and "ids" in params:
            ids = [int(x) for x in params["ids"].split("-")]
            return [self._fixtures[i] for i in ids if i in self._fixtures]
        if path == "/fixtures/statistics":
            return self._fixtures[int(params["fixture"])].get("statistics", [])
        raise ValueError(path)
