#!/usr/bin/env python3
"""Rebuild the league site.

    python build.py            # fetch any new weeks, then rebuild
    python build.py --demo     # build from fake data, no ESPN or API key needed
    python build.py --week 5   # refetch one week, discarding its cached recaps

Weeks already in data/ are never refetched and their recaps are never rewritten,
so a rerun is cheap and the text people already read stays put.
"""

import argparse
import json
import os
import sys

import league as lg
import recaps
import render

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def load_config():
    with open(os.path.join(HERE, "config.json")) as f:
        return json.load(f)


def cache_path(week):
    return os.path.join(DATA, f"week_{week:02d}.json")


def load_cached():
    os.makedirs(DATA, exist_ok=True)
    weeks = []
    for name in sorted(os.listdir(DATA)):
        if name.startswith("week_") and name.endswith(".json"):
            with open(os.path.join(DATA, name)) as f:
                weeks.append(json.load(f))
    return sorted(weeks, key=lambda w: w["week"])


def save(week_data):
    with open(cache_path(week_data["week"]), "w") as f:
        json.dump(week_data, f, indent=2)


def refresh(config, force_week=None):
    """Fetch any played week that is not cached yet."""
    connection = lg.connect(config)
    current = connection.current_week
    cached = {w["week"] for w in load_cached()}
    if force_week:
        cached.discard(force_week)

    for week in range(1, current + 1):
        if week in cached:
            continue
        print(f"Fetching week {week}...")
        data = lg.fetch_week(connection, week)
        if data is None:
            print(f"  Week {week} has not been played. Stopping here.")
            break
        data = recaps.write_recaps(data, config["favourite_team"], cache_path(week))
        save(data)
        print(f"  Saved week {week} ({len(data['matchups'])} matchups)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true",
                        help="build from sample data instead of ESPN")
    parser.add_argument("--week", type=int,
                        help="refetch this week and rewrite its recaps")
    args = parser.parse_args()

    config = load_config()

    if args.demo:
        import demo_data
        global DATA
        DATA = os.path.join(HERE, "data-demo")   # keep sample data out of data/
        os.makedirs(DATA, exist_ok=True)
        for week_data in demo_data.build(config["favourite_team"]):
            save(week_data)
        print("Wrote sample data to data/")
    else:
        if config["league_id"] in (0, None, 123456):
            sys.exit("Set your league_id in config.json first.")
        refresh(config, args.week)

    render.build_site(load_cached(), config)
    render.build_keepers_page(config)
    render.build_draft_history_page(config)
    render.build_standings_page(config)
    render.build_league_basics_page(config)
    render.build_home_page(config)
    print("Done. Open docs/index.html")


if __name__ == "__main__":
    main()
