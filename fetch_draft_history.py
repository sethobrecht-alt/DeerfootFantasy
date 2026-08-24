#!/usr/bin/env python3
"""Fetch draft results for past seasons and save them for the site.

Unlike probe_espn.py (read-only diagnostic, nothing saved to the repo), this
is meant to run periodically and commit its output — draft results for a
past season don't change, so in practice this only needs a rerun when you
want to add another year.

    export ESPN_S2='your_espn_s2_cookie'
    export SWID='{YOUR-SWID-WITH-BRACES}'
    python fetch_draft_history.py 123456 --years 2023 2024 2025

Writes draft_history.json in the repo root.
"""

import argparse
import json
import os
import sys

try:
    from espn_api.football import League
except ImportError:
    sys.exit("pip install espn-api")

OUT = "draft_history.json"


def fetch_year(league_id, year, espn_s2, swid):
    league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
    picks = []
    for i, p in enumerate(league.draft, start=1):
        picks.append({
            "overall": i,
            "round": p.round_num,
            "pick": p.round_pick,
            "team": p.team.team_name if p.team else None,
            "player": p.playerName or None,
            "keeper": bool(p.keeper_status),
        })
    return picks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("league_id", type=int)
    ap.add_argument("--years", type=int, nargs="+", required=True)
    args = ap.parse_args()

    espn_s2, swid = os.environ.get("ESPN_S2"), os.environ.get("SWID")
    if not (espn_s2 and swid):
        sys.exit("Set ESPN_S2 and SWID first — draft history needs a private-league cookie.")

    existing = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            existing = json.load(f).get("years", {})

    years = dict(existing)
    for year in args.years:
        print(f"Fetching {year}...")
        try:
            picks = fetch_year(args.league_id, year, espn_s2, swid)
        except Exception as err:
            print(f"  Failed: {err}")
            continue
        if not picks:
            print("  No picks returned (draft not run, or year unavailable). Skipping.")
            continue
        print(f"  {len(picks)} picks")
        years[str(year)] = picks

    out = {"league_id": args.league_id, "years": years}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {OUT} ({sum(len(p) for p in years.values())} total picks across {len(years)} years)")


if __name__ == "__main__":
    main()
