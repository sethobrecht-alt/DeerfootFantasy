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
    ap.add_argument("--weeks", type=int, nargs="+",
                     help="fetch full box-score detail for these weeks")
    ap.add_argument("--through-week", type=int,
                     help="print each team's record/points/streak through this week, "
                          "straight off team.outcomes/team.scores (no box scores)")
    args = ap.parse_args()

    espn_s2, swid = os.environ.get("ESPN_S2"), os.environ.get("SWID")
    if not (espn_s2 and swid):
        sys.exit("Set ESPN_S2 and SWID first.")

    league = League(league_id=args.league_id, year=args.year, espn_s2=espn_s2, swid=swid)

    if args.through_week:
        n = args.through_week
        for team in league.teams:
            outcomes = team.outcomes[:n]
            scores = team.scores[:n]
            wins = outcomes.count("W")
            losses = outcomes.count("L")
            ties = outcomes.count("T")
            points_for = round(sum(scores), 2)
            streak_type, streak_len = None, 0
            for o in reversed(outcomes):
                if o not in ("W", "L"):
                    break
                if streak_type is None:
                    streak_type = o
                if o == streak_type:
                    streak_len += 1
                else:
                    break
            print(f"{team.team_name}: {wins}-{losses}" + (f"-{ties}" if ties else "")
                  + f", {points_for} PF, streak {streak_type or '-'}{streak_len}"
                  + f", outcomes so far: {''.join(outcomes)}")
        return

    if not args.weeks:
        sys.exit("Pass --weeks or --through-week.")

    def side_digest(side):
        top = ", ".join(f"{p['name']} {p['points']}" for p in side["starters"][:3])
        lines = [f"    {side['name']} {side['score']} — top: {top}"]
        if side["blunders"]:
            b = side["blunders"][0]
            lines.append(
                f"      benched {b['should_have_started']} ({b['bench_points']}) for "
                f"{b['actually_started']} ({b['starter_points']}) at {b['slot']}, "
                f"-{b['points_lost']} pts; total left on bench: "
                f"{side['points_left_on_bench']}"
            )
        return "\n".join(lines)

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
                print(side_digest(h))
                print(side_digest(a))
        else:
            print(f"  week {w}: no data")

    with open(OUT, "w") as f:
        json.dump(weeks, f, indent=2)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
