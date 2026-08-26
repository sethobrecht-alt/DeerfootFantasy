"""Pull league data from ESPN and turn it into plain dictionaries.

Everything downstream (recaps, rendering) works off these dicts, so the site can
be rebuilt from cached JSON without touching ESPN again.
"""

import os
from espn_api.football import League

BENCH_SLOTS = {"BE", "IR"}


def connect(config):
    """Open a league connection. Private leagues need ESPN_S2 and SWID."""
    kwargs = {"league_id": config["league_id"], "year": config["year"]}
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("SWID")
    if s2 and swid:
        kwargs["espn_s2"] = s2
        kwargs["swid"] = swid
    else:
        print("No ESPN_S2/SWID found — this only works if the league is public.")
    return League(**kwargs)


def _player(p):
    return {
        "name": p.name,
        "position": p.position,
        "slot": p.slot_position,
        "points": round(p.points, 2),
        "projected": round(p.projected_points, 2),
        "eligible": [s for s in p.eligibleSlots if s not in BENCH_SLOTS],
        "pro_team": p.proTeam,
        "injury": p.injuryStatus,
    }


def find_blunders(lineup):
    """Find points a manager left on the bench.

    Walks bench players from highest scoring down. For each one, finds the
    weakest starter it was legally eligible to replace. Once a swap is made
    that slot is spoken for, so the same starter is never blamed twice.
    """
    starters = [dict(p) for p in lineup if p["slot"] not in BENCH_SLOTS]
    bench = sorted(
        [p for p in lineup if p["slot"] == "BE"],
        key=lambda p: p["points"],
        reverse=True,
    )

    blunders = []
    for bp in bench:
        options = [
            s for s in starters
            if s["slot"] in bp["eligible"] and s["points"] < bp["points"]
        ]
        if not options:
            continue
        benched_instead = min(options, key=lambda s: s["points"])
        blunders.append({
            "slot": benched_instead["slot"],
            "should_have_started": bp["name"],
            "bench_points": bp["points"],
            "actually_started": benched_instead["name"],
            "starter_points": benched_instead["points"],
            "points_lost": round(bp["points"] - benched_instead["points"], 2),
        })
        starters.remove(benched_instead)
        starters.append({**bp, "slot": benched_instead["slot"]})

    return sorted(blunders, key=lambda b: b["points_lost"], reverse=True)


def _side(team, score, lineup):
    players = [_player(p) for p in lineup]
    starters = [p for p in players if p["slot"] not in BENCH_SLOTS]
    blunders = find_blunders(players)
    return {
        "team_id": team.team_id,
        "name": team.team_name,
        "abbrev": team.team_abbrev,
        "logo": getattr(team, "logo_url", ""),
        "score": round(score, 2),
        "starters": sorted(starters, key=lambda p: p["points"], reverse=True),
        "bench": sorted(
            [p for p in players if p["slot"] == "BE"],
            key=lambda p: p["points"],
            reverse=True,
        ),
        "blunders": blunders,
        "points_left_on_bench": round(sum(b["points_lost"] for b in blunders), 2),
        "optimal_score": round(score + sum(b["points_lost"] for b in blunders), 2),
    }


def fetch_week(lg, week):
    """Return matchups for one week, or None if the week has not been played."""
    boxes = lg.box_scores(week)
    matchups = []
    for box in boxes:
        if not getattr(box.home_team, "team_id", None):
            continue  # bye or placeholder matchup
        if not getattr(box.away_team, "team_id", None):
            continue
        matchups.append({
            "home": _side(box.home_team, box.home_score, box.home_lineup),
            "away": _side(box.away_team, box.away_score, box.away_lineup),
        })

    if not matchups:
        return None
    if sum(m["home"]["score"] + m["away"]["score"] for m in matchups) == 0:
        return None  # scheduled but not yet played

    for m in matchups:
        h, a = m["home"], m["away"]
        m["margin"] = round(abs(h["score"] - a["score"]), 2)
        m["winner"] = None if h["score"] == a["score"] else (
            h["name"] if h["score"] > a["score"] else a["name"]
        )
        m["total"] = round(h["score"] + a["score"], 2)
    return {"week": week, "matchups": matchups}


def standings_through(weeks):
    """Build cumulative records from played weeks.

    Computed from results rather than read off ESPN so that rebuilding an old
    week shows the standings as they were, not as they are now.
    """
    table = {}
    for wk in weeks:
        for m in wk["matchups"]:
            for me, them in ((m["home"], m["away"]), (m["away"], m["home"])):
                row = table.setdefault(me["name"], {
                    "name": me["name"], "abbrev": me["abbrev"], "logo": me["logo"],
                    "team_id": me["team_id"], "wins": 0, "losses": 0, "ties": 0,
                    "points_for": 0.0, "points_against": 0.0,
                    "bench_points_wasted": 0.0, "weekly_scores": [],
                })
                row["points_for"] += me["score"]
                row["points_against"] += them["score"]
                row["bench_points_wasted"] += me["points_left_on_bench"]
                row["weekly_scores"].append(me["score"])
                if me["score"] > them["score"]:
                    row["wins"] += 1
                elif me["score"] < them["score"]:
                    row["losses"] += 1
                else:
                    row["ties"] += 1

    for row in table.values():
        played = row["wins"] + row["losses"] + row["ties"]
        row["win_pct"] = (row["wins"] + 0.5 * row["ties"]) / played if played else 0
        row["points_for"] = round(row["points_for"], 2)
        row["points_against"] = round(row["points_against"], 2)
        row["bench_points_wasted"] = round(row["bench_points_wasted"], 2)
        row["record"] = f"{row['wins']}-{row['losses']}" + (
            f"-{row['ties']}" if row["ties"] else ""
        )
    return list(table.values())


def _scale(values):
    lo, hi = min(values), max(values)
    span = hi - lo
    return [50.0 if span == 0 else (v - lo) / span * 100 for v in values]


def power_rankings(rows, weights, previous=None):
    """Blend scoring and record into a 0-100 rating, then rank."""
    if not rows:
        return []

    points_scaled = _scale([r["points_for"] for r in rows])
    record_scaled = _scale([r["win_pct"] for r in rows])
    w_pts = weights.get("points", 0.6)
    w_rec = weights.get("record", 0.4)

    for row, p, rc in zip(rows, points_scaled, record_scaled):
        row["rating"] = round((w_pts * p + w_rec * rc) / (w_pts + w_rec), 1)

    ranked = sorted(
        rows, key=lambda r: (-r["rating"], -r["points_for"])
    )
    prev_rank = {t["name"]: t["rank"] for t in (previous or [])}
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
        was = prev_rank.get(row["name"])
        row["movement"] = 0 if was is None else was - i
        row["is_new"] = was is None
    return ranked


# Roster spots hurt enough to weigh down a team's health score. Values are
# how much of the player's season average points counts against them --
# OUT/IR count in full, DOUBTFUL counts at half (still probably plays).
INJURY_WEIGHT = {"OUT": 1.0, "INJURY_RESERVE": 1.0, "DOUBTFUL": 0.5}


def _roster_injuries(team):
    """This team's significant injuries, worst impact first."""
    hurt = []
    for p in team.roster:
        weight = INJURY_WEIGHT.get(p.injuryStatus)
        if not weight:
            continue
        hurt.append({
            "name": p.name,
            "position": p.position,
            "status": p.injuryStatus,
            "avg_points": round(p.avg_points, 2),
            "impact": round(weight * p.avg_points, 2),
        })
    return sorted(hurt, key=lambda h: h["impact"], reverse=True)


def season_power_rankings(league, weights):
    """Season-to-date power rankings straight off ESPN's live team state.

    Unlike power_rankings() (which works from locally cached weekly box
    scores), this reads wins/points_for/roster directly off the League
    connection, so the injury component reflects who's hurt right now
    rather than who was hurt in some already-played week.
    """
    rows = []
    for team in league.teams:
        played = team.wins + team.losses + team.ties
        win_pct = (team.wins + 0.5 * team.ties) / played if played else 0.0
        injuries = _roster_injuries(team)
        rows.append({
            "name": team.team_name,
            "abbrev": team.team_abbrev,
            "logo": getattr(team, "logo_url", ""),
            "wins": team.wins,
            "losses": team.losses,
            "ties": team.ties,
            "record": f"{team.wins}-{team.losses}" + (f"-{team.ties}" if team.ties else ""),
            "points_for": round(team.points_for, 2),
            "win_pct": win_pct,
            "streak_type": team.streak_type,
            "streak_length": team.streak_length,
            "injuries": injuries,
            "injury_impact": round(sum(h["impact"] for h in injuries), 2),
        })

    if not rows:
        return []

    points_scaled = _scale([r["points_for"] for r in rows])
    record_scaled = _scale([r["win_pct"] for r in rows])
    # More injury impact should mean a lower health score, so scale the
    # negative of it -- least-hurt team lands at 100, most-hurt at 0.
    health_scaled = _scale([-r["injury_impact"] for r in rows])
    w_pts = weights.get("points", 0.5)
    w_rec = weights.get("record", 0.35)
    w_health = weights.get("health", 0.15)
    total_w = w_pts + w_rec + w_health

    for row, p, rc, h in zip(rows, points_scaled, record_scaled, health_scaled):
        row["rating"] = round((w_pts * p + w_rec * rc + w_health * h) / total_w, 1)
        row["health_score"] = round(h, 1)

    ranked = sorted(rows, key=lambda r: (-r["rating"], -r["points_for"]))
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    return ranked
