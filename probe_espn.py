#!/usr/bin/env python3
"""Find out what your league actually returns.

Run this once, locally, with your cookies set. It doesn't change anything — it
reads a handful of ESPN endpoints and reports what came back, then saves the raw
JSON so the keeper question can be settled with evidence instead of guesswork.

    export ESPN_S2='your_espn_s2_cookie'
    export SWID='{YOUR-SWID-WITH-BRACES}'
    python probe_espn.py 123456 --year 2026

Output lands in probe-output/. Nothing is sent anywhere.
"""

import argparse
import json
import os
import re
import sys

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUT = "probe-output"


def get(league_id, year, views, historical=False):
    if historical:
        url = f"{BASE}/leagueHistory/{league_id}"
        params = [("seasonId", year)] + [("view", v) for v in views]
    else:
        url = f"{BASE}/seasons/{year}/segments/0/leagues/{league_id}"
        params = [("view", v) for v in views]

    cookies = {}
    if os.environ.get("ESPN_S2") and os.environ.get("SWID"):
        cookies = {"espn_s2": os.environ["ESPN_S2"], "SWID": os.environ["SWID"]}

    r = requests.get(url, params=params, cookies=cookies,
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    data = r.json()
    if isinstance(data, list):
        data = data[0] if data else None
    return data, None


def save(name, data):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def heading(text):
    print(f"\n{text}\n" + "-" * len(text))


def check_access(league_id, year):
    heading("Access")
    if not (os.environ.get("ESPN_S2") and os.environ.get("SWID")):
        print("  No cookies set. Private leagues will fail.")
    data, err = get(league_id, year, ["mSettings", "mTeam"])
    if err:
        print(f"  Could not read the league: {err}")
        print("  401/403 usually means bad or expired cookies.")
        print("  404 usually means the league ID or year is wrong.")
        return None
    settings = data.get("settings", {})
    print(f"  League: {settings.get('name', '?')}")
    print(f"  Season: {data.get('seasonId')}")
    print(f"  Teams: {len(data.get('teams', []))}")
    print(f"  Public: {settings.get('isPublic')}")
    save("settings", data)
    return data


def check_keeper_settings(data):
    heading("Keeper settings")
    draft = data.get("settings", {}).get("draftSettings", {})
    keeper_count = draft.get("keeperCount")
    print(f"  keeperCount: {keeper_count}")
    print(f"  keeperCountFuture: {draft.get('keeperCountFuture')}")
    print(f"  keeperOrderType: {draft.get('keeperOrderType')}")
    print(f"  draft date: {draft.get('date')}")
    print(f"  draft type: {draft.get('type')}")
    if not keeper_count:
        print("  This league does not appear to have keepers enabled for this season.")


def check_draft(league_id, year):
    heading("Draft")
    data, err = get(league_id, year, ["mDraftDetail"])
    if err:
        print(f"  Failed: {err}")
        return
    detail = data.get("draftDetail", {})
    drafted = detail.get("drafted")
    picks = detail.get("picks", [])
    print(f"  drafted: {drafted}")
    print(f"  picks returned: {len(picks)}")
    keepers = [p for p in picks if p.get("keeper")]
    print(f"  picks flagged as keepers: {len(keepers)}")
    if keepers:
        print("  Keeper data is available through the draft. This is the easy case.")
        for p in keepers[:5]:
            print(f"    team {p.get('teamId')} round {p.get('roundId')} "
                  f"player {p.get('playerId')}")
    elif not drafted:
        print("  Draft has not run yet, so ESPN returns no picks. Expected.")
    print(f"  saved: {save(f'draft_{year}', data)}")


def check_roster_keeper_fields(league_id, year):
    """The interesting one: do roster entries carry keeper information?"""
    heading("Roster keeper fields")
    data, err = get(league_id, year, ["mRoster", "mTeam"])
    if err:
        print(f"  Failed: {err}")
        return
    found = []
    for team in data.get("teams", []):
        for entry in team.get("roster", {}).get("entries", []):
            pool = entry.get("playerPoolEntry", {})
            record = {
                "team_id": team.get("id"),
                "player": pool.get("player", {}).get("fullName"),
                "keeperValue": pool.get("keeperValue"),
                "keeperValueFuture": pool.get("keeperValueFuture"),
                "lineupLocked": pool.get("lineupLocked"),
                "status": pool.get("status"),
                "entry_keys": sorted(entry.keys()),
            }
            if record["keeperValue"] or record["keeperValueFuture"]:
                found.append(record)

    total = sum(len(t.get("roster", {}).get("entries", []))
                for t in data.get("teams", []))
    print(f"  roster entries seen: {total}")
    print(f"  entries with a non-zero keeperValue: {len(found)}")
    if found:
        print("  Sample:")
        for r in found[:8]:
            print(f"    team {r['team_id']}: {r['player']} "
                  f"keeperValue={r['keeperValue']} "
                  f"future={r['keeperValueFuture']}")
        print("\n  NOTE: keeperValue is usually the round a player would COST,")
        print("  not proof a manager declared them. Check these against what you")
        print("  see on the ESPN keepers page before trusting it.")
    else:
        print("  No keeper values on rosters. Declarations are probably not")
        print("  exposed to the API before the draft.")
    print(f"  saved: {save(f'roster_{year}', data)}")


def find_named_players(league_id, year, names):
    """Dump every field on specific players' roster entries, no filtering.

    hunt_keeper_fields only looks at keys whose *name* mentions "keeper". If
    ESPN's keepers page (the commissioner UI, separate from this read API)
    is driven by a differently-named field, that search would miss it. This
    looks at the full entry for players you know are keepers, so nothing
    is filtered out by a naming guess.
    """
    heading("Named player lookup")
    wanted = {n.strip().lower() for n in names if n.strip()}
    if not wanted:
        return
    data, err = get(league_id, year, ["mRoster", "mTeam", "mDraftDetail", "mSettings"])
    if err or not data:
        print(f"  Failed: {err}")
        return

    found_any = False
    for team in data.get("teams", []):
        for entry in team.get("roster", {}).get("entries", []):
            pool = entry.get("playerPoolEntry", {})
            player = pool.get("player", {})
            full = player.get("fullName", "")
            if full.lower() not in wanted:
                continue
            found_any = True
            print(f"\n  {full} (team {team.get('id')})")
            print(f"    playerPoolEntry keys: {sorted(pool.keys())}")
            print(f"    roster entry keys: {sorted(entry.keys())}")
            print(f"    full playerPoolEntry:\n" +
                  "\n".join(f"      {line}" for line in
                            json.dumps(pool, indent=2).splitlines()))

    if not found_any:
        print("  None of the named players were found on any roster.")
    print(f"\n  saved: {save(f'named_players_{year}', data)}")


def walk(obj, needle, path=""):
    """Yield every path in a JSON blob whose key mentions `needle`."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else key
            if needle in key.lower() and not isinstance(value, (dict, list)):
                yield here, value
            yield from walk(value, needle, here)
    elif isinstance(obj, list):
        for i, value in enumerate(obj[:40]):  # cap: rosters repeat structure
            yield from walk(value, needle, f"{path}[{i}]")


def hunt_keeper_fields(league_id, year):
    """Scan every view we can reach for anything keeper-shaped.

    You're the league manager, so your cookie may expose fields a normal member
    never sees. Rather than guess which ones, this looks at everything.
    """
    heading("Keeper field hunt")
    views = [
        ["mSettings"], ["mDraftDetail"], ["mRoster"], ["mTeam"],
        ["mPendingTransactions"], ["mTransactions2"], ["mStatus"],
        ["mRoster", "mTeam", "mDraftDetail", "mSettings"],
    ]
    hits = {}
    for view in views:
        data, err = get(league_id, year, view)
        if err or not data:
            print(f"  {'+'.join(view)}: {err or 'empty'}")
            continue
        found = list(walk(data, "keeper"))
        label = "+".join(view)
        print(f"  {label}: {len(found)} keeper-ish fields")
        for path, value in found:
            generic = re.sub(r"\[\d+\]", "[]", path)
            hits.setdefault(generic, set()).add(repr(value))
        save(f"hunt_{label}", data)

    if not hits:
        print("\n  Nothing keeper-related anywhere. Declarations are not exposed.")
        return

    print("\n  Distinct fields found, with the values seen:")
    for path in sorted(hits):
        values = sorted(hits[path])
        shown = ", ".join(values[:6]) + (" ..." if len(values) > 6 else "")
        print(f"    {path} = {shown}")
    print("\n  A field that is 0 or false everywhere is not carrying")
    print("  declarations. One that varies by player is worth chasing.")


def check_history(league_id, current_year, back_to):
    heading("Season history")
    available = []
    for year in range(back_to, current_year):
        data, err = get(league_id, year, ["mTeam", "mSettings"])
        route = "seasons"
        if err or not data:
            data, err = get(league_id, year, ["mTeam", "mSettings"], historical=True)
            route = "leagueHistory"
        if err or not data or not data.get("teams"):
            print(f"  {year}: unavailable ({err or 'no teams returned'})")
            continue
        teams = data["teams"]
        has_standing = any(t.get("rankCalculatedFinal") or t.get("playoffSeed")
                           for t in teams)
        print(f"  {year}: {len(teams)} teams via {route}"
              f"{'' if has_standing else '  (no final standings)'}")
        available.append(year)
        save(f"season_{year}", data)
    print(f"\n  Usable seasons: {available or 'none'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("league_id", type=int)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--back-to", type=int, default=2015,
                    help="earliest season to test for history")
    ap.add_argument("--find-players", default="",
                    help="comma-separated player names to dump full roster-entry fields for")
    args = ap.parse_args()

    data = check_access(args.league_id, args.year)
    if not data:
        return
    check_keeper_settings(data)
    check_draft(args.league_id, args.year)
    check_roster_keeper_fields(args.league_id, args.year)
    hunt_keeper_fields(args.league_id, args.year)
    if args.find_players:
        find_named_players(args.league_id, args.year, args.find_players.split(","))
    check_history(args.league_id, args.year, args.back_to)

    heading("Next")
    print(f"  Raw responses are in {OUT}/. The keeper answer is in the two")
    print("  sections above: if either showed keeper data, the tab can be")
    print("  automatic. If neither did, it needs a manual file until draft day.")


if __name__ == "__main__":
    main()
