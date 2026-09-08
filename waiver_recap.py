#!/usr/bin/env python3
"""Fetch and render the Waiver Recap page for a processed waiver week.

Meant to run every Wednesday morning, after FAAB waivers clear.

    python waiver_recap.py [--week N] [--year Y] [--league-id ID]

Writes docs/waiver-recap.html. No AI involved -- every callout on this page
is a deterministic function of bid amounts, so it can run unattended.

--year and --league-id are for previewing a past season without touching
config.json (which stays pointed at the live league for the real weekly
run).
"""

import argparse
import json

import league as lg
import render
import waivers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int,
                     help="override the week to fetch (default: the league's current week)")
    ap.add_argument("--year", type=int, help="override the season to fetch")
    ap.add_argument("--league-id", type=int, help="override the league ID")
    args = ap.parse_args()

    config = json.load(open("config.json"))
    if args.year:
        config = {**config, "year": args.year}
    if args.league_id:
        config = {**config, "league_id": args.league_id}
    league = lg.connect(config)
    week = args.week or league.current_week

    data = waivers.fetch_week_waivers(league, week)
    render.build_waiver_recap_page(data, config)


if __name__ == "__main__":
    main()
