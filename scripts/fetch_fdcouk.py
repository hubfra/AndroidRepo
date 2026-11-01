#!/usr/bin/env python3
"""Darmowe źródło danych: pliki CSV z https://www.football-data.co.uk

Daje bieżący sezon za darmo, ale tylko część statystyk: rzuty rożne (HC/AC)
i faule (HF/AF). Spalonych w tych plikach nie ma. Wyniki są aktualizowane
zwykle 2 razy w tygodniu (po weekendzie i po kolejce w środku tygodnia).

Użycie:
    python scripts/fetch_fdcouk.py               # dzisiejsze mecze
    python scripts/fetch_fdcouk.py --date 2026-11-08
    python scripts/fetch_fdcouk.py --local DIR   # pliki CSV z katalogu (testy)
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from fetch_data import (CONFIG_PATH, OUT_DIR, compute_table,  # noqa: E402
                        compute_team_stats, load_json, save_json)

BASE = "https://www.football-data.co.uk"
DIVISIONS = {39: "E0", 140: "SP1", 135: "I1", 78: "D1", 61: "F1"}
# klucz statystyki z config.json -> (kolumna gospodarza, kolumna gościa)
COLUMNS = {
    "corners": ("HC", "AC"),
    "fouls": ("HF", "AF"),
    "shots": ("HS", "AS"),
    "shots_on": ("HST", "AST"),
    "yellow": ("HY", "AY"),
}
UK = ZoneInfo("Europe/London")


def season_code(start_year: int) -> str:
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


class Source:
    def __init__(self, local_dir: Path | None = None):
        self.local_dir = local_dir

    def get(self, rel: str) -> str | None:
        if self.local_dir:
            p = self.local_dir / rel.replace("/", "_")
            return p.read_text(encoding="utf-8") if p.exists() else None
        url = f"{BASE}/{rel}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (stats-app)"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                print(f"  pobrano {url} ({len(raw)} B)", flush=True)
                return raw.decode("utf-8-sig", errors="replace")
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    print(f"  brak pliku {url}", flush=True)
                    return None
                err = exc
            except Exception as exc:  # noqa: BLE001
                err = exc
            time.sleep(2 ** (attempt + 1))
        raise RuntimeError(f"Nie udało się pobrać {url}: {err}")


def parse_date(s: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def parse_rows(text: str | None) -> list[dict]:
    if not text:
        return []
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        d = parse_date(row.get("Date", ""))
        if not d or not row.get("HomeTeam") or not row.get("AwayTeam"):
            continue
        t = row.get("Time") or "15:00"
        try:
            hh, mm = (int(x) for x in t.split(":")[:2])
        except ValueError:
            hh, mm = 15, 0
        kick = datetime(d.year, d.month, d.day, hh, mm, tzinfo=UK)
        row["_date"] = d
        row["_kick"] = kick
        out.append(row)
    return out


def build(day: date, cfg: dict, src: Source) -> dict:
    tz = ZoneInfo(cfg["timezone"])
    start = day.year if day.month >= 7 else day.year - 1
    stats_cfg = [s for s in cfg["stats"] if s["key"] in COLUMNS]
    missing = [s["label"] for s in cfg["stats"] if s["key"] not in COLUMNS]
    notes = ["Źródło: football-data.co.uk (darmowe). Wyniki aktualizowane zwykle "
             "po weekendzie i po kolejce w tygodniu."]
    if missing:
        notes.append(f"Niedostępne w tym źródle: {', '.join(missing)}.")

    fixtures = parse_rows(src.get("fixtures.csv"))
    leagues_out = []
    h2h_from = datetime.combine(day, datetime.min.time(), tz) - timedelta(days=365 * cfg["h2h_years"] + 1)

    for lg in cfg["leagues"]:
        div = DIVISIONS.get(lg["id"])
        if not div:
            continue
        history: list[dict] = []
        current: list[dict] = []
        for y in range(start, start - 3, -1):
            rows = parse_rows(src.get(f"mmz4281/{season_code(y)}/{div}.csv"))
            history += rows
            if y == start:
                current = rows
        played = [r for r in history if r.get("FTHG", "") != "" and r["_date"] < day]
        played.sort(key=lambda r: r["_kick"], reverse=True)

        today = {(r["HomeTeam"], r["AwayTeam"]): r for r in history if r["_date"] == day}
        for r in fixtures:
            if r.get("Div") == div and r["_date"] == day:
                today.setdefault((r["HomeTeam"], r["AwayTeam"]), r)
        if not today:
            continue

        def stat(r, side):
            return {s["key"]: to_int(r.get(COLUMNS[s["key"]][0 if side == "H" else 1]))
                    for s in stats_cfg}

        def recent(team):
            out = []
            for r in played:
                if team not in (r["HomeTeam"], r["AwayTeam"]):
                    continue
                home = r["HomeTeam"] == team
                gf, ga = (r["FTHG"], r["FTAG"]) if home else (r["FTAG"], r["FTHG"])
                out.append({
                    "id": f"{div}-{r['_date']}-{r['HomeTeam']}",
                    "date": r["_kick"].astimezone(tz).isoformat(),
                    "opponent": r["AwayTeam"] if home else r["HomeTeam"],
                    "venue": "D" if home else "W",
                    "score": f"{gf}:{ga}",
                    "stats": stat(r, "H" if home else "A"),
                })
                if len(out) == cfg["recent_matches"]:
                    break
            return out

        matches = []
        for (home, away), r in sorted(today.items(), key=lambda kv: kv[1]["_kick"]):
            h2h = []
            for x in played:
                if {x["HomeTeam"], x["AwayTeam"]} != {home, away} or x["_kick"] < h2h_from:
                    continue
                host_home = x["HomeTeam"] == home
                h2h.append({
                    "id": f"{div}-{x['_date']}-{x['HomeTeam']}",
                    "date": x["_kick"].astimezone(tz).isoformat(),
                    "host": "home" if host_home else "away",
                    "score": f"{x['FTHG']}:{x['FTAG']}",
                    "label": f"{x['HomeTeam']} – {x['AwayTeam']}",
                    "stats": {s["key"]: {
                        "home": stat(x, "H" if host_home else "A")[s["key"]],
                        "away": stat(x, "A" if host_home else "H")[s["key"]],
                    } for s in stats_cfg},
                })
            done = r.get("FTHG", "") != ""
            matches.append({
                "id": f"{div}-{day}-{home}",
                "kickoff": r["_kick"].astimezone(tz).isoformat(),
                "status": "FT" if done else "NS",
                "round": None,
                "goals": [to_int(r.get("FTHG")), to_int(r.get("FTAG"))] if done else [None, None],
                "home": {"id": home, "name": home, "logo": None},
                "away": {"id": away, "name": away, "logo": None},
                "recent": {"home": recent(home), "away": recent(away)},
                "h2h": h2h,
            })
        table = compute_table([{
            "home": {"id": r["HomeTeam"], "name": r["HomeTeam"]},
            "away": {"id": r["AwayTeam"], "name": r["AwayTeam"]},
            "goals": [to_int(r.get("FTHG")), to_int(r.get("FTAG"))],
            "ts": r["_kick"].timestamp()} for r in current if r.get("FTHG", "") != ""])
        done_rows = [r for r in current if r.get("FTHG", "") != ""]
        by_id = {i: r for i, r in enumerate(done_rows)}
        team_stats = compute_team_stats(
            [{"id": i, "ts": r["_kick"].timestamp(),
              "home": {"id": r["HomeTeam"], "name": r["HomeTeam"]},
              "away": {"id": r["AwayTeam"], "name": r["AwayTeam"]}} for i, r in by_id.items()],
            lambda gid, tid: stat(by_id[gid], "H" if by_id[gid]["HomeTeam"] == tid else "A"),
            [s["key"] for s in stats_cfg])
        leagues_out.append({"id": lg["id"], "name": lg["name"], "country": lg["country"],
                            "logo": None, "season": start, "matches": matches, "table": table,
                            "team_stats": team_stats})

    if not fixtures:
        notes.append("Nie udało się pobrać terminarza (fixtures.csv).")
    return {
        "date": day.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timezone": cfg["timezone"],
        "recent_matches": cfg["recent_matches"],
        "h2h_years": cfg["h2h_years"],
        "stats": [{"key": s["key"], "label": s["label"]} for s in stats_cfg],
        "leagues": leagues_out,
        "notes": notes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date")
    ap.add_argument("--local", help="katalog z plikami CSV zamiast pobierania")
    args = ap.parse_args()
    cfg = load_json(CONFIG_PATH, None)
    day = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo(cfg["timezone"])).date()
    data = build(day, cfg, Source(Path(args.local) if args.local else None))
    save_json(OUT_DIR / "matches.json", data)
    n = sum(len(lg["matches"]) for lg in data["leagues"])
    print(f"Zapisano {n} meczów z dnia {day}")
    for lg in data["leagues"]:
        for m in lg["matches"]:
            print(f"  {lg['name']}: {m['home']['name']} – {m['away']['name']} "
                  f"(ostatnie: {len(m['recent']['home'])}/{len(m['recent']['away'])}, H2H: {len(m['h2h'])})")
    for n_ in data["notes"]:
        print("UWAGA:", n_)
    return 0


if __name__ == "__main__":
    sys.exit(main())
