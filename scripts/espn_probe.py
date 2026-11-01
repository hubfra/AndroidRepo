"""Rozpoznanie danych dostępnych w nieoficjalnym API ESPN (uruchamiane w GitHub Actions)."""
import json
import sys
import urllib.request

SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
V2 = "https://site.api.espn.com/apis/v2/sports/soccer"
CORE = "https://sports.core.api.espn.com/v2/sports/soccer/leagues"
DONE = "401878765"      # Liverpool – Brighton, zakończony
TODAY = "401879246"     # Liverpool – Arsenal, dziś
LG = "eng.1"
TEAM = "364"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def show(label, obj, n=900):
    s = json.dumps(obj, ensure_ascii=False)
    print(f"--- {label} ({len(s)} zn.)\n{s[:n]}")


def keys(o):
    return list(o.keys()) if isinstance(o, dict) else type(o).__name__


def probe(label, url, fn):
    print(f"\n######## {label}\n{url}")
    try:
        fn(get(url))
    except Exception as exc:  # noqa: BLE001
        print("BŁĄD:", exc)


def summary(d):
    print("klucze:", keys(d))
    for k in d:
        v = d[k]
        if isinstance(v, list):
            print(f"  [{k}] lista {len(v)}; 1. el. klucze: {keys(v[0]) if v else '-'}")
        elif isinstance(v, dict):
            print(f"  [{k}] klucze: {keys(v)}")
    show("gameInfo", d.get("gameInfo"), 1200)
    show("header.competitions[0] (bez competitors)", {k: v for k, v in d.get("header", {}).get("competitions", [{}])[0].items() if k != "competitors"}, 800)
    ke = d.get("keyEvents") or []
    print("keyEvents typy:", sorted({(e.get("type") or {}).get("text") for e in ke if isinstance(e, dict)}))
    show("keyEvents[0]", ke[0] if ke else None, 700)
    com = d.get("commentary") or []
    print("commentary:", len(com))
    show("commentary[0]", com[0] if com else None, 500)
    ro = d.get("rosters") or []
    if ro:
        print("rosters[0] klucze:", keys(ro[0]))
        r0 = (ro[0].get("roster") or [{}])[0]
        print("  zawodnik klucze:", keys(r0))
        print("  statystyki zawodnika:", [(s.get("name"), s.get("displayValue")) for s in r0.get("stats", [])])
        print("  formacja:", ro[0].get("formation"))
    show("lastFiveGames[0]", (d.get("lastFiveGames") or [None])[0], 900)
    show("headToHeadGames", d.get("headToHeadGames"), 600)
    show("seasonseries", d.get("seasonseries"), 600)
    show("odds", d.get("odds"), 900)
    show("pickcenter", d.get("pickcenter"), 900)
    show("standings", d.get("standings"), 600)
    show("injuries", d.get("injuries"), 600)


probe("SUMMARY zakończonego meczu", f"{SITE}/{LG}/summary?event={DONE}", summary)
probe("SUMMARY dzisiejszego meczu", f"{SITE}/{LG}/summary?event={TODAY}", summary)


def standings(d):
    print("klucze:", keys(d))
    ch = (d.get("children") or [{}])[0]
    ent = (ch.get("standings") or {}).get("entries") or []
    print("drużyn:", len(ent))
    if ent:
        print("statystyki w tabeli:", [(s.get("name"), s.get("displayValue")) for s in ent[0].get("stats", [])])
        print("note:", ent[0].get("note"))


probe("STANDINGS (apis/v2)", f"{V2}/{LG}/standings", standings)
probe("TEAM", f"{SITE}/{LG}/teams/{TEAM}", lambda d: show("team", d.get("team"), 1500))
probe("TEAM statistics", f"{SITE}/{LG}/teams/{TEAM}/statistics", lambda d: show("stats", d, 2500))
probe("TEAM roster", f"{SITE}/{LG}/teams/{TEAM}/roster", lambda d: (print("klucze", keys(d)), show("athlete[0]", (d.get("athletes") or [None])[0], 1500)))
probe("TEAM injuries", f"{SITE}/{LG}/teams/{TEAM}/injuries", lambda d: show("injuries", d, 800))
probe("NEWS", f"{SITE}/{LG}/news", lambda d: print("artykułów:", len(d.get("articles", []))))
probe("CORE officials", f"{CORE}/{LG}/events/{DONE}/competitions/{DONE}/officials", lambda d: show("officials", d, 1500))
probe("CORE competitor stats", f"{CORE}/{LG}/events/{DONE}/competitions/{DONE}/competitors/{TEAM}/statistics",
      lambda d: (print("klucze", keys(d)), show("splits", d.get("splits"), 2000)))
probe("CORE odds", f"{CORE}/{LG}/events/{TODAY}/competitions/{TODAY}/odds", lambda d: show("odds", d, 1500))
probe("CORE predictor", f"{CORE}/{LG}/events/{TODAY}/competitions/{TODAY}/predictor", lambda d: show("predictor", d, 1500))
probe("CORE team season statistics", f"{CORE}/{LG}/seasons/2026/types/1/teams/{TEAM}/statistics",
      lambda d: (print("klucze", keys(d)), [print("  kategoria", c.get("name"), [s.get("name") for s in c.get("stats", [])]) for c in (d.get("splits") or {}).get("categories", [])]))
