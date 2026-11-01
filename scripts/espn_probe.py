"""Rozpoznanie struktury danych nieoficjalnego API ESPN (uruchamiane w GitHub Actions)."""
import json
import sys
import urllib.request

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def show(label, obj, n=1500):
    print(f"--- {label}")
    print(json.dumps(obj, ensure_ascii=False)[:n])


day = sys.argv[1] if len(sys.argv) > 1 else "20261101"
for lg in ["eng.1", "esp.1", "ita.1", "ger.1", "fra.1"]:
    sb = get(f"{BASE}/{lg}/scoreboard?dates={day}")
    evs = sb.get("events", [])
    print(f"=== {lg}: {len(evs)} meczów; season={sb.get('season')}; leagues[0].season={sb.get('leagues',[{}])[0].get('season')}")
    for e in evs[:20]:
        c = e["competitions"][0]
        print("  ", e["id"], e["date"], e["name"], e["status"]["type"]["name"],
              [(t["team"]["id"], t["team"]["displayName"], t.get("homeAway"), t.get("score")) for t in c["competitors"]])

lg = "eng.1"
sb = get(f"{BASE}/{lg}/scoreboard?dates={day}")
ev = sb["events"][0]
show("event keys", list(ev.keys()))
show("competition keys", list(ev["competitions"][0].keys()))
show("competitor[0]", ev["competitions"][0]["competitors"][0], 2500)
sm = get(f"{BASE}/{lg}/summary?event={ev['id']}")
show("summary keys", list(sm.keys()))
show("summary.headToHeadGames", sm.get("headToHeadGames"), 3000)
show("summary.boxscore", sm.get("boxscore"), 3000)

tid = ev["competitions"][0]["competitors"][0]["team"]["id"]
for url in [f"{BASE}/{lg}/teams/{tid}/schedule", f"{BASE}/{lg}/teams/{tid}/schedule?season=2026",
            f"{BASE}/{lg}/teams/{tid}/schedule?season=2025"]:
    try:
        sc = get(url)
        evs = sc.get("events", [])
        print(f"=== {url}: keys={list(sc.keys())} events={len(evs)} season={sc.get('season')} requestedSeason={sc.get('requestedSeason')}")
        for e in evs[:3] + evs[-3:]:
            c = e["competitions"][0]
            print("  ", e["id"], e["date"], e.get("name"), c.get("status", {}).get("type", {}).get("name"),
                  [(t["team"]["id"], t.get("homeAway"), t.get("score")) for t in c["competitors"]])
    except Exception as exc:  # noqa: BLE001
        print("ERR", url, exc)

# statystyki zakończonego meczu
done = [e for e in sc.get("events", []) if e["competitions"][0].get("status", {}).get("type", {}).get("completed")]
if done:
    sm2 = get(f"{BASE}/{lg}/summary?event={done[-1]['id']}")
    for t in sm2.get("boxscore", {}).get("teams", []):
        print("STATS", t["team"]["displayName"], [(s.get("name"), s.get("displayValue")) for s in t.get("statistics", [])])
