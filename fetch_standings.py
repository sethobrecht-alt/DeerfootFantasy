#!/usr/bin/env python3
"""Fetch final standings for past seasons and save them for the site.

Same pattern as fetch_champions.py / fetch_draft_history.py: run by a
manual-dispatch workflow with the repo's ESPN cookies, output committed
straight to the repo.

    export ESPN_S2='your_espn_s2_cookie'
    export SWID='{YOUR-SWID-WITH-BRACES}'
    python fetch_standings.py 123456 --years 2023 2024 2025 --current-year 2026

Writes standings_history.json.
"""

import argparse
import json
import os
import sys

try:
    from espn_api.football import League
except ImportError:
    sys.exit("pip install espn-api")

OUT = "standings_history.json"


def fetch_year(league_id, year, espn_s2, swid):
    league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
    rows = []
    for team in league.standings():
        rows.append({
            "rank": team.final_standing,
            "regular_finish": team.standing,
            "team": team.team_name,
            "wins": team.wins,
            "losses": team.losses,
            "ties": team.ties,
            "points_for": round(team.points_for, 2),
            "points_against": round(team.points_against, 2),
        })
    rows.sort(key=lambda r: r["rank"] if r["rank"] else 99)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("league_id", type=int)
    ap.add_argument("--years", type=int, nargs="+", required=True,
                    help="completed seasons to fetch final standings for")
    ap.add_argument("--current-year", type=int, required=True,
                    help="season to pull the full current team list from")
    args = ap.parse_args()

    espn_s2, swid = os.environ.get("ESPN_S2"), os.environ.get("SWID")
    if not (espn_s2 and swid):
        sys.exit("Set ESPN_S2 and SWID first.")

    existing = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            existing = json.load(f).get("years", {})

    years = dict(existing)
    for year in args.years:
        print(f"Fetching {year}...")
        try:
            rows = fetch_year(args.league_id, year, espn_s2, swid)
        except Exception as err:
            print(f"  Failed: {err}")
            continue
        if not rows:
            print("  No standings returned (season not final, or unavailable). Skipping.")
            continue
        print(f"  {len(rows)} teams")
        years[str(year)] = rows

    print(f"Fetching current ({args.current_year}) team list...")
    current = League(league_id=args.league_id, year=args.current_year,
                      espn_s2=espn_s2, swid=swid)
    current_teams = sorted(t.team_name for t in current.teams)
    print(f"  {len(current_teams)} teams")

    out = {"league_id": args.league_id, "years": years, "current_teams": current_teams}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {OUT} ({sum(len(r) for r in years.values())} total team-seasons across {len(years)} years)")


if __name__ == "__main__":
    main()
