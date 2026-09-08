#!/usr/bin/env python3
"""Fetch and render the Waiver Recap page for a processed waiver week.

Meant to run every Wednesday morning, after FAAB waivers clear.

    python waiver_recap.py [--week N]

Writes docs/waiver-recap.html. No AI involved -- every callout on this page
is a deterministic function of bid amounts, so it can run unattended.
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
    args = ap.parse_args()

    config = json.load(open("config.json"))
    league = lg.connect(config)
    week = args.week or league.current_week

    data = waivers.fetch_week_waivers(league, week)
    render.build_waiver_recap_page(data, config)


if __name__ == "__main__":
    main()
