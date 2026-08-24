"""Fake but realistically shaped data, for previewing the site offline.

Only used by `python build.py --demo`. Delete once the real league is wired up.
"""

import random
import league as lg

TEAMS = [
    ("Regulation Gentlemen", "REG"),
    ("Sunday Scaries", "SCAR"),
    ("Third and Inches", "3RD"),
    ("The Punt Enthusiasts", "PUNT"),
    ("Waiver Wire Warriors", "WWW"),
    ("Bye Week Believers", "BYE"),
]

SLOTS = [
    ("QB", ["QB"]),
    ("RB", ["RB", "RB/WR/TE"]),
    ("RB", ["RB", "RB/WR/TE"]),
    ("WR", ["WR", "RB/WR/TE"]),
    ("WR", ["WR", "RB/WR/TE"]),
    ("TE", ["TE", "RB/WR/TE"]),
    ("RB/WR/TE", ["RB", "WR", "TE", "RB/WR/TE"]),
    ("D/ST", ["D/ST"]),
    ("K", ["K"]),
]

FIRST = ["Marcus", "Devon", "Tyler", "Jalen", "Corey", "Amari", "Bryce", "Elijah",
         "Xavier", "Rashad", "Cade", "Isiah", "Trey", "Donte", "Kenneth", "Aaron"]
LAST = ["Whitfield", "Okafor", "Brennan", "Castillo", "Mbeki", "Lindgren", "Ruiz",
        "Ashworth", "Dupree", "Nakamura", "Feldman", "Oyelaran", "Vance", "Kirby"]

RECAPS = [
    "The final margin says close game. The tape says otherwise. {w} had this in "
    "hand by the second quarter and spent the afternoon watching {l} chase points "
    "that were never coming.\n\nThat is now three straight for {w}, all of them "
    "built the same boring way: start the good players, sit the bad ones, collect "
    "the win. Revolutionary stuff.",

    "{l} scored enough to beat four other teams this week. Instead they drew {w}, "
    "which is the kind of luck that makes people quit leagues.\n\nNo real blame to "
    "assign here beyond the schedule. Both rosters did roughly what they were "
    "supposed to do. One of them just did it against the wrong opponent.",

    "A genuinely ugly football game between two teams who appear to have given up "
    "on the concept of a starting lineup. {w} won because somebody had to.\n\n"
    "The good news for {l} is that a week this bad is hard to repeat. The bad news "
    "is that they said that last week too.",
]


def _player(rng, slot, eligible, ceiling):
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    projected = round(rng.uniform(4, ceiling), 1)
    points = round(max(0, rng.gauss(projected, projected * 0.55)), 2)
    return {
        "name": name, "position": slot.split("/")[0], "slot": slot,
        "points": points, "projected": projected,
        "eligible": eligible, "pro_team": "FA", "injury": "ACTIVE",
    }


def _side(rng, name, abbrev, team_id):
    players = [_player(rng, s, e, 22 if s != "K" else 10) for s, e in SLOTS]
    for _ in range(6):
        slot, elig = rng.choice(SLOTS[1:7])
        p = _player(rng, slot, elig, 20)
        p["slot"] = "BE"
        players.append(p)

    starters = [p for p in players if p["slot"] != "BE"]
    score = round(sum(p["points"] for p in starters), 2)
    blunders = lg.find_blunders(players)
    lost = round(sum(b["points_lost"] for b in blunders), 2)

    return {
        "team_id": team_id, "name": name, "abbrev": abbrev, "logo": "",
        "score": score,
        "starters": sorted(starters, key=lambda p: p["points"], reverse=True),
        "bench": sorted([p for p in players if p["slot"] == "BE"],
                        key=lambda p: p["points"], reverse=True),
        "blunders": blunders,
        "points_left_on_bench": lost,
        "optimal_score": round(score + lost, 2),
    }


def build(favourite_team, weeks=3, seed=7):
    rng = random.Random(seed)
    roster = list(TEAMS)
    roster[0] = (favourite_team, favourite_team[:4].upper())

    out = []
    for week in range(1, weeks + 1):
        order = roster[:]
        rng.shuffle(order)
        matchups = []
        for i in range(0, len(order), 2):
            (hn, ha), (an, aa) = order[i], order[i + 1]
            home = _side(rng, hn, ha, roster.index((hn, ha)) + 1)
            away = _side(rng, an, aa, roster.index((an, aa)) + 1)
            winner = None if home["score"] == away["score"] else (
                hn if home["score"] > away["score"] else an)
            loser = an if winner == hn else hn
            matchups.append({
                "home": home, "away": away,
                "margin": round(abs(home["score"] - away["score"]), 2),
                "total": round(home["score"] + away["score"], 2),
                "winner": winner,
                "key": f"{home['team_id']}v{away['team_id']}",
                "recap": rng.choice(RECAPS).format(w=winner, l=loser),
            })
        out.append({
            "week": week,
            "headline": f"Week {week} settles nothing at all",
            "matchups": matchups,
        })
    return out
