#!/usr/bin/env python3
"""Pobiera mecze z danego dnia z topowych lig i buduje zestawienia statystyk.

Źródło danych: API-Football (https://www.api-football.com), v3.

Użycie:
    API_FOOTBALL_KEY=... python scripts/fetch_data.py               # dzisiejsze mecze
    API_FOOTBALL_KEY=... python scripts/fetch_data.py --date 2026-11-08
    python scripts/fetch_data.py --mock                             # dane testowe, bez API

Zmienne środowiskowe:
    API_FOOTBALL_KEY  klucz API (wymagany bez --mock)
    MAX_REQUESTS      maks. liczba zapytań w jednym uruchomieniu (domyślnie 90)
    REQUEST_DELAY     przerwa między zapytaniami w sekundach (domyślnie 6.5,
                      bo darmowy plan pozwala na ok. 10 zapytań/min;
                      przy płatnym planie można ustawić 0.3)

Wszystkie pobrane statystyki zakończonych meczów są trzymane w katalogu cache/,
więc kolejne uruchomienia pobierają tylko nowe mecze. W cache zapisywane są
wszystkie typy statystyk z API, więc dodanie nowej statystyki w config.json
nie wymaga ponownego pobierania danych.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
CACHE_DIR = ROOT / "cache"
OUT_DIR = ROOT / "site" / "data"

API_BASE = "https://v3.football.api-sports.io"
FINISHED = {"FT", "AET", "PEN"}
TERMINAL = FINISHED | {"CANC", "ABD", "AWD", "WO"}
IDS_PER_REQUEST = 20


class BudgetExceeded(Exception):
    pass


class ApiError(Exception):
    pass


# --------------------------------------------------------------------------- API


class ApiClient:
    def __init__(self, key: str, max_requests: int, delay: float):
        self.key = key
        self.max_requests = max_requests
        self.delay = delay
        self.used = 0
        self.remaining_today: str | None = None
        self._last_call = 0.0

    def get(self, path: str, **params) -> list:
        if self.used >= self.max_requests:
            raise BudgetExceeded()
        wait = self.delay - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"x-apisports-key": self.key})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    self.remaining_today = resp.headers.get(
                        "x-ratelimit-requests-remaining", self.remaining_today
                    )
                    body = json.load(resp)
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt == 3:
                    raise ApiError(f"{path}: {exc}") from exc
                time.sleep(2 ** (attempt + 1))
        self._last_call = time.monotonic()
        self.used += 1
        errors = body.get("errors")
        if errors:
            msg = json.dumps(errors, ensure_ascii=False)
            if "request" in msg.lower() and "limit" in msg.lower():
                raise BudgetExceeded(msg)
            raise ApiError(f"{path} {params}: {msg}")
        print(f"  [API {self.used}] {path} {params} -> {body.get('results')} wyników", flush=True)
        return body.get("response") or []


# ------------------------------------------------------------------------ helpers


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, data, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=1 if pretty else None,
                   separators=None if pretty else (",", ":")),
        encoding="utf-8",
    )
    tmp.replace(path)


def compact_fixture(f: dict) -> dict:
    fx, teams, goals = f["fixture"], f["teams"], f.get("goals") or {}
    return {
        "id": fx["id"],
        "ts": fx["timestamp"],
        "date": fx["date"],
        "status": fx["status"]["short"],
        "home": {"id": teams["home"]["id"], "name": teams["home"]["name"],
                 "logo": teams["home"].get("logo")},
        "away": {"id": teams["away"]["id"], "name": teams["away"]["name"],
                 "logo": teams["away"].get("logo")},
        "goals": [goals.get("home"), goals.get("away")],
    }


def parse_statistics(stat_blocks: list) -> dict:
    """[{team:{id}, statistics:[{type, value}]}] -> {team_id: {type: value}}"""
    out = {}
    for block in stat_blocks or []:
        team_id = str(block["team"]["id"])
        values = {}
        for s in block.get("statistics") or []:
            v = s.get("value")
            if isinstance(v, str) and v.endswith("%"):
                v = v.rstrip("%")
            try:
                v = float(v) if v is not None else None
                if v is not None and v.is_integer():
                    v = int(v)
            except (TypeError, ValueError):
                v = None
            values[s["type"]] = v
        out[team_id] = values
    return out


# ------------------------------------------------------------------------- core


class Builder:
    def __init__(self, api, config: dict, cache_dir: Path = CACHE_DIR):
        self.api = api
        self.cfg = config
        self.cache_dir = cache_dir
        self.tz = config["timezone"]
        self.stats_cache: dict = load_json(cache_dir / "stats.json", {})
        self.ids_supported = True
        self.notes: list[str] = []

    # --- sezony ---------------------------------------------------------------

    def season_fixtures(self, league_id: int, season: int, current: bool) -> list[dict]:
        path = self.cache_dir / "seasons" / f"{league_id}_{season}.json"
        cached = load_json(path, None)
        # Zakończony sezon nie zmienia się; pozostałe odświeżamy raz dziennie.
        if cached is not None and (cached.get("complete") or cached.get("fetched_today") == str(date.today())):
            return cached["fixtures"]
        try:
            raw = self.api.get("/fixtures", league=league_id, season=season, timezone=self.tz)
        except BudgetExceeded:
            if cached is not None:
                self.notes.append(f"Brak limitu – użyto zapisanego terminarza ligi {league_id}/{season}.")
                return cached["fixtures"]
            raise
        fixtures = [compact_fixture(f) for f in raw]
        complete = bool(fixtures) and all(f["status"] in TERMINAL for f in fixtures)
        save_json(path, {"complete": complete, "fetched_today": str(date.today()),
                         "fixtures": fixtures})
        return fixtures

    # --- statystyki -----------------------------------------------------------

    def fetch_stats(self, fixture_ids: list[int]) -> None:
        missing = [i for i in fixture_ids if str(i) not in self.stats_cache]
        if not missing:
            return
        print(f"Do pobrania statystyki {len(missing)} meczów", flush=True)
        try:
            i = 0
            while i < len(missing):
                if self.ids_supported:
                    chunk = missing[i:i + IDS_PER_REQUEST]
                    try:
                        raw = self.api.get("/fixtures", ids="-".join(map(str, chunk)))
                    except ApiError as exc:
                        print(f"  Parametr ids niedostępny ({exc}); przełączam na pojedyncze zapytania")
                        self.ids_supported = False
                        continue
                    if raw and "statistics" not in raw[0]:
                        print("  Odpowiedź bez statystyk; przełączam na pojedyncze zapytania")
                        self.ids_supported = False
                        continue
                    for f in raw:
                        self.stats_cache[str(f["fixture"]["id"])] = parse_statistics(f.get("statistics"))
                    i += len(chunk)
                else:
                    fid = missing[i]
                    raw = self.api.get("/fixtures/statistics", fixture=fid)
                    self.stats_cache[str(fid)] = parse_statistics(raw)
                    i += 1
        except BudgetExceeded:
            left = sum(1 for x in missing if str(x) not in self.stats_cache)
            self.notes.append(
                f"Wyczerpany limit zapytań – brak statystyk {left} meczów. "
                "Zostaną dobrane przy kolejnym uruchomieniu."
            )
        finally:
            save_json(self.cache_dir / "stats.json", self.stats_cache)

    def stat_values(self, fixture_id: int, team_id: int) -> dict:
        entry = self.stats_cache.get(str(fixture_id))
        if not entry:
            return {s["key"]: None for s in self.cfg["stats"]}
        team = entry.get(str(team_id)) or {}
        return {s["key"]: team.get(s["api_type"]) for s in self.cfg["stats"]}

    # --- budowanie dnia -------------------------------------------------------

    def build(self, day: date) -> dict:
        leagues_cfg = {lg["id"]: lg for lg in self.cfg["leagues"]}
        print(f"Mecze z dnia {day}", flush=True)
        day_raw = self.api.get("/fixtures", date=day.isoformat(), timezone=self.tz)
        day_raw = [f for f in day_raw if f["league"]["id"] in leagues_cfg]
        day_raw.sort(key=lambda f: f["fixture"]["timestamp"])

        n_recent = self.cfg["recent_matches"]
        h2h_from = datetime.combine(day, datetime.min.time(), ZoneInfo(self.tz)) - timedelta(
            days=365 * self.cfg["h2h_years"] + 1)

        # Terminarze lig: bieżący sezon + dwa poprzednie (żeby H2H objęło 2 lata,
        # a 10 ostatnich meczów było dostępne także na początku sezonu).
        league_fixtures: dict[int, list[dict]] = {}
        for lid in sorted({f["league"]["id"] for f in day_raw}):
            season = next(f["league"]["season"] for f in day_raw if f["league"]["id"] == lid)
            fixtures = []
            for s in range(season, season - 3, -1):
                try:
                    fixtures += self.season_fixtures(lid, s, current=(s == season))
                except BudgetExceeded:
                    self.notes.append(f"Wyczerpany limit – niepełny terminarz ligi {lid}.")
                    break
            league_fixtures[lid] = sorted(
                (f for f in fixtures if f["status"] in FINISHED), key=lambda f: -f["ts"])

        matches_out, needed = [], []
        for f in day_raw:
            lid = f["league"]["id"]
            kickoff_ts = f["fixture"]["timestamp"]
            home, away = f["teams"]["home"], f["teams"]["away"]
            history = [x for x in league_fixtures.get(lid, []) if x["ts"] < kickoff_ts]

            def recent_for(team_id):
                games = [x for x in history if team_id in (x["home"]["id"], x["away"]["id"])]
                return games[:n_recent]

            rec_home, rec_away = recent_for(home["id"]), recent_for(away["id"])
            h2h = [x for x in history
                   if {x["home"]["id"], x["away"]["id"]} == {home["id"], away["id"]}
                   and x["ts"] >= h2h_from.timestamp()]
            needed += [x["id"] for x in rec_home + rec_away + h2h]
            matches_out.append((f, rec_home, rec_away, h2h))

        # Najpierw najnowsze mecze – przy ograniczonym limicie są najważniejsze.
        ts_by_id = {x["id"]: x["ts"] for lst in league_fixtures.values() for x in lst}
        uniq = sorted(set(needed), key=lambda i: -ts_by_id[i])
        self.fetch_stats(uniq)

        def recent_entry(x, team_id):
            is_home = x["home"]["id"] == team_id
            opp = x["away"] if is_home else x["home"]
            gf, ga = (x["goals"][0], x["goals"][1]) if is_home else (x["goals"][1], x["goals"][0])
            return {"id": x["id"], "date": x["date"], "opponent": opp["name"],
                    "venue": "D" if is_home else "W", "score": f"{gf}:{ga}",
                    "stats": self.stat_values(x["id"], team_id)}

        leagues_out: dict[int, dict] = {}
        for f, rec_home, rec_away, h2h in matches_out:
            lid = f["league"]["id"]
            lg = leagues_out.setdefault(lid, {
                "id": lid, "name": leagues_cfg[lid]["name"],
                "country": leagues_cfg[lid]["country"],
                "logo": f["league"].get("logo"), "season": f["league"]["season"],
                "matches": []})
            home, away = f["teams"]["home"], f["teams"]["away"]
            lg["matches"].append({
                "id": f["fixture"]["id"],
                "kickoff": f["fixture"]["date"],
                "status": f["fixture"]["status"]["short"],
                "round": f["league"].get("round"),
                "goals": [f["goals"]["home"], f["goals"]["away"]],
                "home": {"id": home["id"], "name": home["name"], "logo": home.get("logo")},
                "away": {"id": away["id"], "name": away["name"], "logo": away.get("logo")},
                "recent": {"home": [recent_entry(x, home["id"]) for x in rec_home],
                           "away": [recent_entry(x, away["id"]) for x in rec_away]},
                "h2h": [{
                    "id": x["id"], "date": x["date"],
                    "host": "home" if x["home"]["id"] == home["id"] else "away",
                    "score": f"{x['goals'][0]}:{x['goals'][1]}",
                    "label": f"{x['home']['name']} – {x['away']['name']}",
                    "stats": {s["key"]: {"home": self.stat_values(x["id"], home["id"])[s["key"]],
                                         "away": self.stat_values(x["id"], away["id"])[s["key"]]}
                              for s in self.cfg["stats"]},
                } for x in h2h],
            })

        order = [lg["id"] for lg in self.cfg["leagues"]]
        return {
            "date": day.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "timezone": self.tz,
            "recent_matches": n_recent,
            "h2h_years": self.cfg["h2h_years"],
            "stats": [{"key": s["key"], "label": s["label"]} for s in self.cfg["stats"]],
            "leagues": [leagues_out[i] for i in order if i in leagues_out],
            "notes": self.notes,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="dzień w formacie RRRR-MM-DD (domyślnie dziś)")
    ap.add_argument("--mock", action="store_true", help="użyj danych testowych zamiast API")
    args = ap.parse_args()

    config = load_json(CONFIG_PATH, None)
    if config is None:
        print("Brak config.json", file=sys.stderr)
        return 1
    day = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo(config["timezone"])).date()

    if args.mock:
        sys.path.insert(0, str(Path(__file__).parent))
        from mock_api import MockApi
        api = MockApi(config)
        cache_dir = ROOT / "cache-mock"
    else:
        key = os.environ.get("API_FOOTBALL_KEY", "").strip()
        if not key:
            print("Ustaw zmienną API_FOOTBALL_KEY (albo użyj --mock)", file=sys.stderr)
            return 1
        api = ApiClient(key, int(os.environ.get("MAX_REQUESTS", "90")),
                        float(os.environ.get("REQUEST_DELAY", "6.5")))
        cache_dir = CACHE_DIR

    builder = Builder(api, config, cache_dir)
    try:
        data = builder.build(day)
    except BudgetExceeded as exc:
        print(f"Wyczerpany dzienny limit zapytań API: {exc}", file=sys.stderr)
        return 2
    except ApiError as exc:
        print(f"Błąd API: {exc}", file=sys.stderr)
        return 3

    data["requests_used"] = api.used
    save_json(OUT_DIR / "matches.json", data)
    n = sum(len(lg["matches"]) for lg in data["leagues"])
    print(f"Zapisano {n} meczów do {OUT_DIR / 'matches.json'} (zapytań: {api.used}, "
          f"pozostało dziś: {getattr(api, 'remaining_today', None)})")
    for note in data["notes"]:
        print("UWAGA:", note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
