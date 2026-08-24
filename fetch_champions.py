#!/usr/bin/env python3
"""Determine each season's champion and save it for the site.

Same pattern as fetch_draft_history.py: run by a manual-dispatch workflow
with the repo's ESPN cookies, output committed straight to the repo.

    export ESPN_S2='your_espn_s2_cookie'
    export SWID='{YOUR-SWID-WITH-BRACES}'
    python fetch_champions.py 123456 --years 2023 2024 2025 --current-year 2026

Writes champions.json.
"""

import argparse
import json
import os
import sys

try:
    from espn_api.football import League
except ImportError:
    sys.exit("pip install espn-api")

OUT = "champions.json"


def champion_for(league_id, year, espn_s2, swid):
    league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
    standings = league.standings()
    if not standings:
        return None
    top = standings[0]
    if getattr(top, "final_standing", 0) != 1:
        return None  # season not finished, or ESPN hasn't set a final rank
    return top.team_name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("league_id", type=int)
    ap.add_argument("--years", type=int, nargs="+", required=True,
                    help="completed seasons to check for a champion")
    ap.add_argument("--current-year", type=int, required=True,
                    help="season to pull the full team list from")
    args = ap.parse_args()

    espn_s2, swid = os.environ.get("ESPN_S2"), os.environ.get("SWID")
    if not (espn_s2 and swid):
        sys.exit("Set ESPN_S2 and SWID first.")

    years = {}
    for year in args.years:
        print(f"Checking {year}...")
        champ = champion_for(args.league_id, year, espn_s2, swid)
        print(f"  champion: {champ or 'not final yet, or unavailable'}")
        if champ:
            years[str(year)] = champ

    print(f"Fetching current ({args.current_year}) team list...")
    current = League(league_id=args.league_id, year=args.current_year,
                      espn_s2=espn_s2, swid=swid)
    team_names = sorted(t.team_name for t in current.teams)
    print(f"  {len(team_names)} teams")

    out = {
        "league_id": args.league_id,
        "years": years,
        "current_teams": team_names,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
