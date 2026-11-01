#!/usr/bin/env python3
"""Darmowe źródło danych: nieoficjalne API ESPN (site.api.espn.com).

Bez klucza i bez limitu dziennego. Daje rzuty rożne, spalone, faule i inne
statystyki drużyn, aktualizowane zaraz po meczu. API jest nieudokumentowane,
więc ESPN może je w każdej chwili zmienić.

Użycie:
    python scripts/fetch_espn.py               # dzisiejsze mecze
    python scripts/fetch_espn.py --date 2026-11-08
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from fetch_data import (CACHE_DIR, CONFIG_PATH, OUT_DIR, compute_table,  # noqa: E402
                        compute_team_stats, load_json, save_json)

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
SLUGS = {39: "eng.1", 140: "esp.1", 135: "ita.1", 78: "ger.1", 61: "fra.1"}
# klucz statystyki z config.json -> nazwa statystyki w ESPN
STAT_NAMES = {
    "corners": "wonCorners",
    "offsides": "offsides",
    "fouls": "foulsCommitted",
    "shots": "totalShots",
    "shots_on": "shotsOnTarget",
    "yellow": "yellowCards",
}
WORKERS = 6
# Inne rozgrywki do H2H (puchary krajowe, superpuchary, europejskie puchary).
UEFA = ["uefa.champions", "uefa.europa", "uefa.europa.conf", "uefa.super_cup"]
CUPS = {
    "eng.1": ["eng.fa", "eng.league_cup", "eng.charity"],
    "esp.1": ["esp.copa_del_rey", "esp.super_cup"],
    "ita.1": ["ita.coppa_italia", "ita.super_cup"],
    "ger.1": ["ger.dfb_pokal", "ger.super_cup"],
    "fra.1": ["fra.coupe_de_france", "fra.super_cup"],
}
COMP_NAMES = {
    "eng.1": "Liga", "esp.1": "Liga", "ita.1": "Liga", "ger.1": "Liga", "fra.1": "Liga",
    "uefa.champions": "Liga Mistrzów", "uefa.europa": "Liga Europy",
    "uefa.europa.conf": "Liga Konferencji", "uefa.super_cup": "Superpuchar UEFA",
    "eng.fa": "Puchar Anglii", "eng.league_cup": "Puchar Ligi", "eng.charity": "Tarcza Wspólnoty",
    "esp.copa_del_rey": "Puchar Króla", "esp.super_cup": "Superpuchar",
    "ita.coppa_italia": "Puchar Włoch", "ita.super_cup": "Superpuchar",
    "ger.dfb_pokal": "Puchar Niemiec", "ger.super_cup": "Superpuchar",
    "fra.coupe_de_france": "Puchar Francji", "fra.super_cup": "Superpuchar",
}


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (stats-app)"})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            last = exc
            if 400 <= exc.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def score_of(competitor: dict):
    s = competitor.get("score")
    if isinstance(s, dict):
        s = s.get("displayValue", s.get("value"))
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def parse_event(e: dict) -> dict:
    c = e["competitions"][0]
    teams = {t["homeAway"]: t for t in c["competitors"]}
    st = (c.get("status") or e.get("status") or {}).get("type", {})
    return {
        "id": str(e["id"]),
        "date": e["date"],
        "ts": datetime.fromisoformat(e["date"].replace("Z", "+00:00")).timestamp(),
        "completed": bool(st.get("completed")),
        "state": st.get("state"),
        "home": {"id": str(teams["home"]["team"]["id"]),
                 "name": teams["home"]["team"].get("displayName"),
                 "logo": teams["home"]["team"].get("logo")},
        "away": {"id": str(teams["away"]["team"]["id"]),
                 "name": teams["away"]["team"].get("displayName"),
                 "logo": teams["away"]["team"].get("logo")},
        "goals": [score_of(teams["home"]), score_of(teams["away"])],
    }


def build(day: date, cfg: dict) -> dict:
    tz = ZoneInfo(cfg["timezone"])
    n_recent = cfg["recent_matches"]
    stats_cfg = [s for s in cfg["stats"] if s["key"] in STAT_NAMES]
    notes = ["Źródło: ESPN (darmowe, nieoficjalne API)."]
    missing = [s["label"] for s in cfg["stats"] if s["key"] not in STAT_NAMES]
    if missing:
        notes.append(f"Niedostępne w tym źródle: {', '.join(missing)}.")
    h2h_from = (datetime.combine(day, datetime.min.time(), tz)
                - timedelta(days=365 * cfg["h2h_years"] + 1)).timestamp()
    season = day.year if day.month >= 7 else day.year - 1

    cache_path = CACHE_DIR / "espn_stats.json"
    stats_cache: dict = load_json(cache_path, {})

    # 1) mecze dnia
    day_matches = []  # (league_cfg, slug, league_logo, event)
    for lg in cfg["leagues"]:
        slug = SLUGS.get(lg["id"])
        if not slug:
            continue
        sb = get(f"{BASE}/{slug}/scoreboard?dates={day:%Y%m%d}")
        logos = (sb.get("leagues") or [{}])[0].get("logos") or []
        logo = logos[0].get("href") if logos else None
        evs = [parse_event(e) for e in sb.get("events", [])]
        evs = [e for e in evs if datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(tz).date() == day]
        print(f"{lg['name']}: {len(evs)} meczów", flush=True)
        for e in evs:
            day_matches.append((lg, slug, logo, e))

    # 2) terminarze drużyn (bieżący i 2 poprzednie sezony, tylko liga);
    #    do tabeli ligowej potrzebny jest bieżący sezon wszystkich drużyn ligi
    league_teams: dict[str, list[str]] = {}
    for slug in sorted({slug for _, slug, _, _ in day_matches}):
        try:
            tj = get(f"{BASE}/{slug}/teams")
            ids = [str(t["team"]["id"]) for t in tj["sports"][0]["leagues"][0]["teams"]]
            league_teams[slug] = ids
            print(f"  {slug}: {len(ids)} drużyn w lidze", flush=True)
        except (RuntimeError, KeyError, IndexError) as exc:
            print(f"  błąd listy drużyn {slug}: {exc}", flush=True)
    team_keys = sorted({(slug, e[side]["id"]) for _, slug, _, e in day_matches for side in ("home", "away")})
    jobs = [(slug, tid, s) for slug, tid in team_keys for s in (season, season - 1, season - 2)]
    jobs += [(slug, tid, season) for slug, ids in league_teams.items() for tid in ids
             if (slug, tid) not in set(team_keys)]

    def fetch_schedule(job):
        slug, tid, s = job
        try:
            data = get(f"{BASE}/{slug}/teams/{tid}/schedule?season={s}")
        except RuntimeError as exc:
            print(f"  błąd terminarza {slug}/{tid}/{s}: {exc}", flush=True)
            return job, []
        if (data.get("requestedSeason") or {}).get("year") not in (None, s):
            return job, []
        out = []
        for e in data.get("events", []):
            try:
                pe = parse_event(e)
            except (KeyError, IndexError, ValueError):
                continue
            pe["comp"] = slug
            out.append(pe)
        return job, out

    # H2H we wszystkich rozgrywkach: terminarze pucharowe gospodarzy dzisiejszych meczów
    h2h_jobs = sorted({(cs, e["home"]["id"], s) for _, slug, _, e in day_matches
                       for cs in CUPS.get(slug, []) + UEFA for s in (season, season - 1, season - 2)})
    jobs += [j for j in h2h_jobs if j not in set(jobs)]
    with ThreadPoolExecutor(WORKERS) as pool:
        schedules = dict(pool.map(fetch_schedule, jobs))
    print(f"Pobrano {len(jobs)} terminarzy (w tym {len(h2h_jobs)} pucharowych do H2H)", flush=True)
    cup_games: dict[str, dict] = {}
    for (cs, tid, _), evs in schedules.items():
        if cs in COMP_NAMES and not cs.endswith(".1"):
            for e in evs:
                if e["completed"]:
                    cup_games.setdefault(tid, {})[e["id"]] = e
    found = {}
    for evs in cup_games.values():
        for e in evs.values():
            found[e["comp"]] = found.get(e["comp"], 0) + 1
    print(f"  mecze pucharowe gospodarzy: {found}", flush=True)

    team_games: dict[tuple, list] = {}
    for (slug, tid, _), evs in schedules.items():
        bucket = team_games.setdefault((slug, tid), {})
        for e in evs:
            if e["completed"]:
                bucket[e["id"]] = e
    team_games = {k: sorted(v.values(), key=lambda e: -e["ts"]) for k, v in team_games.items()}

    # tabela ligowa z wyników bieżącego sezonu wszystkich drużyn ligi
    start_ts = datetime(season, 7, 1, tzinfo=tz).timestamp()
    tables: dict[int, list] = {}
    league_games: dict[int, tuple] = {}
    for lg, slug, _, _ in day_matches:
        if lg["id"] in tables or slug not in league_teams:
            continue
        games = {}
        for tid in league_teams[slug]:
            for e in schedules.get((slug, tid, season), []):
                if e["completed"] and e["ts"] >= start_ts:
                    games[e["id"]] = e
        tables[lg["id"]] = compute_table(list(games.values()))
        league_games[lg["id"]] = (slug, list(games.values()))
        print(f"  tabela {lg['name']}: {len(games)} meczów, {len(tables[lg['id']])} drużyn", flush=True)
    for lg, slug, _, _ in day_matches:
        if lg["id"] not in tables and f"Nie udało się pobrać tabeli ligi {lg['name']}." not in notes:
            notes.append(f"Nie udało się pobrać tabeli ligi {lg['name']}.")

    # 3) które mecze potrzebują statystyk
    plan = []
    needed = {}
    for lg, slug, logo, m in day_matches:
        kick = m["ts"]
        rec = {}
        for side in ("home", "away"):
            games = [e for e in team_games.get((slug, m[side]["id"]), []) if e["ts"] < kick]
            rec[side] = games[:n_recent]
        pool_h2h = {e["id"]: e for e in team_games.get((slug, m["home"]["id"]), [])}
        pool_h2h.update(cup_games.get(m["home"]["id"], {}))
        h2h = sorted((e for e in pool_h2h.values()
                      if e["ts"] < kick and e["ts"] >= h2h_from
                      and {e["home"]["id"], e["away"]["id"]} == {m["home"]["id"], m["away"]["id"]}),
                     key=lambda e: -e["ts"])
        for e in rec["home"] + rec["away"]:
            needed[e["id"]] = slug
        for e in h2h:
            needed[e["id"]] = e.get("comp", slug)
        plan.append((lg, slug, logo, m, rec, h2h))

    # średnie sezonowe wszystkich drużyn: statystyki każdego meczu sezonu
    for slug, games in league_games.values():
        for e in games:
            needed.setdefault(e["id"], slug)
    todo = [(eid, slug) for eid, slug in needed.items() if eid not in stats_cache]
    print(f"Statystyki: {len(needed)} meczów, do pobrania {len(todo)}", flush=True)

    def fetch_stats(job):
        eid, slug = job
        try:
            sm = get(f"{BASE}/{slug}/summary?event={eid}")
        except RuntimeError as exc:
            print(f"  błąd statystyk {eid}: {exc}", flush=True)
            return eid, None
        out = {}
        for t in (sm.get("boxscore") or {}).get("teams", []):
            out[str(t["team"]["id"])] = {s.get("name"): num(s.get("displayValue"))
                                         for s in t.get("statistics", [])}
        return eid, out

    with ThreadPoolExecutor(WORKERS) as pool:
        for eid, st in pool.map(fetch_stats, todo):
            if st:
                stats_cache[eid] = st
    save_json(cache_path, stats_cache)
    failed = sum(1 for eid in needed if eid not in stats_cache)
    if failed:
        notes.append(f"Brak statystyk dla {failed} meczów (błąd pobierania).")

    def vals(eid, tid):
        team = (stats_cache.get(eid) or {}).get(tid) or {}
        return {s["key"]: team.get(STAT_NAMES[s["key"]]) for s in stats_cfg}

    def iso(e):
        return datetime.fromtimestamp(e["ts"], tz).isoformat()

    leagues_out: dict[int, dict] = {}
    for lg, slug, logo, m, rec, h2h in sorted(plan, key=lambda p: p[3]["ts"]):
        out = leagues_out.setdefault(lg["id"], {
            "id": lg["id"], "name": lg["name"], "country": lg["country"], "logo": logo,
            "season": season, "matches": [], "table": tables.get(lg["id"], []),
            "team_stats": compute_team_stats(league_games.get(lg["id"], (None, []))[1], vals,
                                             [s["key"] for s in stats_cfg])})

        def recent_entry(e, tid):
            home = e["home"]["id"] == tid
            gf, ga = (e["goals"][0], e["goals"][1]) if home else (e["goals"][1], e["goals"][0])
            return {"id": e["id"], "date": iso(e),
                    "opponent": (e["away"] if home else e["home"])["name"],
                    "venue": "D" if home else "W", "score": f"{gf}:{ga}",
                    "stats": vals(e["id"], tid)}

        status = {"pre": "NS", "in": "LIVE", "post": "FT"}.get(m["state"], "NS")
        out["matches"].append({
            "id": m["id"], "kickoff": iso(m), "status": status, "round": None,
            "goals": m["goals"] if status != "NS" else [None, None],
            "home": m["home"], "away": m["away"],
            "recent": {side: [recent_entry(e, m[side]["id"]) for e in rec[side]]
                       for side in ("home", "away")},
            "h2h": [{
                "id": e["id"], "date": iso(e),
                "host": "home" if e["home"]["id"] == m["home"]["id"] else "away",
                "score": f"{e['goals'][0]}:{e['goals'][1]}",
                "label": f"{e['home']['name']} – {e['away']['name']}",
                "comp": COMP_NAMES.get(e.get("comp", slug), e.get("comp")),
                "stats": {s["key"]: {"home": vals(e["id"], m["home"]["id"])[s["key"]],
                                     "away": vals(e["id"], m["away"]["id"])[s["key"]]}
                          for s in stats_cfg},
            } for e in h2h],
        })

    order = [lg["id"] for lg in cfg["leagues"]]
    return {
        "date": day.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timezone": cfg["timezone"],
        "recent_matches": n_recent,
        "h2h_years": cfg["h2h_years"],
        "h2h_scope": "all",
        "stats": [{"key": s["key"], "label": s["label"]} for s in stats_cfg],
        "leagues": [leagues_out[i] for i in order if i in leagues_out],
        "notes": notes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date")
    args = ap.parse_args()
    cfg = load_json(CONFIG_PATH, None)
    day = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo(cfg["timezone"])).date()
    data = build(day, cfg)
    save_json(OUT_DIR / "matches.json", data)
    for lg in data["leagues"]:
        for m in lg["matches"]:
            r = m["recent"]
            first = (r["home"][0]["stats"] if r["home"] else {})
            print(f"  {lg['name']}: {m['home']['name']} – {m['away']['name']} "
                  f"(ostatnie: {len(r['home'])}/{len(r['away'])}, H2H: {len(m['h2h'])}, przykład: {first})")
    for n in data["notes"]:
        print("UWAGA:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
