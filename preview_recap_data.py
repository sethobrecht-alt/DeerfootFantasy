#!/usr/bin/env python3
"""One-off: pull full box-score detail for a handful of past-season weeks.

For sampling the recap voice against real games before turning the weekly
recap on for the live season. Not part of the regular build pipeline.

    export ESPN_S2='...'
    export SWID='{...}'
    python preview_recap_data.py 311243487 --year 2025 --weeks 1 6 11 17

Writes preview_weeks.json.
"""

import argparse
import json
import os
import sys

try:
    from espn_api.football import League
except ImportError:
    sys.exit("pip install espn-api")

import league as lg

OUT = "preview_weeks.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("league_id", type=int)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--weeks", type=int, nargs="+", required=True)
    args = ap.parse_args()

    espn_s2, swid = os.environ.get("ESPN_S2"), os.environ.get("SWID")
    if not (espn_s2 and swid):
        sys.exit("Set ESPN_S2 and SWID first.")

    league = League(league_id=args.league_id, year=args.year, espn_s2=espn_s2, swid=swid)

    weeks = {}
    for w in args.weeks:
        print(f"Fetching week {w}...")
        data = lg.fetch_week(league, w)
        if data:
            weeks[str(w)] = data
            for m in data["matchups"]:
                h, a = m["home"], m["away"]
                print(f"  {h['name']} {h['score']} - {a['score']} {a['name']}"
                      f" (margin {m['margin']})")
        else:
            print(f"  week {w}: no data")

    with open(OUT, "w") as f:
        json.dump(weeks, f, indent=2)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
