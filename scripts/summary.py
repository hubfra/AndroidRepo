#!/usr/bin/env python3
"""Drukuje zwięzłe podsumowanie statystyk meczów dnia (do podglądu w logach)."""
import json
from pathlib import Path

d = json.loads((Path(__file__).resolve().parent.parent / "site/data/matches.json").read_text(encoding="utf-8"))


def avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


for lg in d["leagues"]:
    ts = {str(r["team"]["id"]): r for r in lg.get("team_stats", [])}
    for m in lg["matches"]:
        h, a = m["home"], m["away"]
        print(f"\n=== {lg['name']}: {h['name']} – {a['name']} ({m['kickoff'][11:16]})")
        for st in d["stats"]:
            k = st["key"]
            rh = [x["stats"][k] for x in m["recent"]["home"]]
            ra = [x["stats"][k] for x in m["recent"]["away"]]
            line = [f"{st['label']}:"]
            line.append(f"ost10 {h['name']}={avg(rh)} {rh} | {a['name']}={avg(ra)} {ra}")
            for side, t in (("H", h), ("A", a)):
                r = ts.get(str(t["id"]))
                if r:
                    line.append(f"{side} sezon={r['season'].get(k)} ost5={r['last'].get(k)}")
            hh = [(g["stats"][k]["home"], g["stats"][k]["away"], g.get("comp")) for g in m["h2h"]]
            line.append(f"H2H(gosp,gość)={hh}")
            print("  " + " || ".join(line))
