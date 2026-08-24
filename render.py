"""Turn cached week data into the static pages GitHub Pages serves."""

import json
import os
import shutil
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
    EASTERN = ZoneInfo("America/New_York")
except Exception:  # no tzdata available
    EASTERN = timezone(timedelta(hours=-5))
from jinja2 import Environment, FileSystemLoader, select_autoescape

import league as lg

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")
DOCS = os.path.join(HERE, "docs")


def _env():
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _flag_of_week(week, favourite, shield):
    """The single worst bench decision of the week."""
    worst = None
    for m in week["matchups"]:
        for side in (m["home"], m["away"]):
            if shield and side["name"] == favourite:
                continue
            for b in side["blunders"]:
                if worst is None or b["points_lost"] > worst["points_lost"]:
                    worst = {**b, "team": side["name"]}
    return worst


def build_site(weeks, config):
    """weeks: list of week dicts, ascending. Writes one page per week."""
    if not weeks:
        print("No completed weeks yet — nothing to render.")
        return

    os.makedirs(DOCS, exist_ok=True)
    shutil.copy(os.path.join(TEMPLATES, "style.css"), os.path.join(DOCS, "style.css"))

    env = _env()
    template = env.get_template("page.html.j2")
    favourite = config["favourite_team"]
    shield = config.get("shield_favourite", True)
    weights = config.get("power_ranking_weights", {"points": 0.6, "record": 0.4})

    archive = [{"week": w["week"], "href": f"week-{w['week']}.html"} for w in weeks]
    archive[-1]["href"] = "recap.html"
    archive = list(reversed(archive))

    updated = datetime.now(EASTERN).strftime("%B %-d, %Y at %-I:%M %p ET")

    previous_ranks = None
    for i, week in enumerate(weeks):
        rows = lg.standings_through(weeks[: i + 1])
        rankings = lg.power_rankings(rows, weights, previous_ranks)
        previous_ranks = [{"name": r["name"], "rank": r["rank"]} for r in rankings]

        wasted = sorted(
            [r for r in rankings if r["bench_points_wasted"] > 0
             and not (shield and r["name"] == favourite)],
            key=lambda r: r["bench_points_wasted"],
            reverse=True,
        )[:5]

        html = template.render(
            site_title=config["site_title"],
            season=config["year"],
            week=week,
            rankings=rankings,
            wasted=wasted,
            weights=weights,
            favourite=favourite,
            shield_favourite=shield,
            flag_of_week=_flag_of_week(week, favourite, shield),
            archive=archive,
            updated=updated,
        )

        is_latest = i == len(weeks) - 1
        name = "recap.html" if is_latest else f"week-{week['week']}.html"
        with open(os.path.join(DOCS, name), "w") as f:
            f.write(html)
        print(f"Wrote docs/{name}")

    open(os.path.join(DOCS, ".nojekyll"), "w").close()


def build_keepers_page(config):
    """Render docs/keepers.html from keepers.json, if it exists.

    Independent of weekly matchup data on purpose: keeper declarations exist
    (and are worth publishing) long before the season's first played week.
    """
    keepers_path = os.path.join(HERE, "keepers.json")
    if not os.path.exists(keepers_path):
        return

    with open(keepers_path) as f:
        data = json.load(f)

    os.makedirs(DOCS, exist_ok=True)
    shutil.copy(os.path.join(TEMPLATES, "style.css"), os.path.join(DOCS, "style.css"))

    env = _env()
    template = env.get_template("keepers.html.j2")
    html = template.render(
        site_title=config["site_title"],
        season=config["year"],
        keepers=data.get("teams", {}),
        keepers_updated=data.get("updated"),
        updated=datetime.now(EASTERN).strftime("%B %-d, %Y at %-I:%M %p ET"),
    )
    with open(os.path.join(DOCS, "keepers.html"), "w") as f:
        f.write(html)
    print("Wrote docs/keepers.html")


def build_draft_history_page(config):
    """Render docs/draft-history.html from draft_history.json, if it exists.

    All the search/sort happens client-side in vanilla JS against the data
    embedded in the page, so this page works without a backend and stays
    fast even across several years of picks.
    """
    history_path = os.path.join(HERE, "draft_history.json")
    if not os.path.exists(history_path):
        return

    with open(history_path) as f:
        data = json.load(f)

    os.makedirs(DOCS, exist_ok=True)
    shutil.copy(os.path.join(TEMPLATES, "style.css"), os.path.join(DOCS, "style.css"))

    years = data.get("years", {})
    env = _env()
    template = env.get_template("draft-history.html.j2")
    html = template.render(
        site_title=config["site_title"],
        season=config["year"],
        years=sorted(years.keys(), reverse=True),
        years_json=json.dumps(years),
        updated=datetime.now(EASTERN).strftime("%B %-d, %Y at %-I:%M %p ET"),
    )
    with open(os.path.join(DOCS, "draft-history.html"), "w") as f:
        f.write(html)
    print("Wrote docs/draft-history.html")


def build_home_page(config):
    """Render docs/index.html — the site's front door — from champions.json.

    Team-name matching only works if a team's name has stayed the same
    since the year it won; a renamed team could be missed. Noted on the
    page itself rather than silently assumed correct.
    """
    champions_path = os.path.join(HERE, "champions.json")
    if not os.path.exists(champions_path):
        return

    with open(champions_path) as f:
        data = json.load(f)

    years = data.get("years", {})
    current_teams = data.get("current_teams", [])

    wins = {}
    for year, team in years.items():
        wins.setdefault(team, []).append(year)

    champions = sorted(
        ({"name": team, "years": sorted(yrs)} for team, yrs in wins.items()),
        key=lambda t: (-len(t["years"]), t["name"]),
    )
    champion_names = set(wins.keys())
    non_champions = sorted(t for t in current_teams if t not in champion_names)

    os.makedirs(DOCS, exist_ok=True)
    shutil.copy(os.path.join(TEMPLATES, "style.css"), os.path.join(DOCS, "style.css"))

    env = _env()
    template = env.get_template("home.html.j2")
    html = template.render(
        site_title=config["site_title"],
        season=config["year"],
        champions=champions,
        non_champions=non_champions,
        updated=datetime.now(EASTERN).strftime("%B %-d, %Y at %-I:%M %p ET"),
    )
    with open(os.path.join(DOCS, "index.html"), "w") as f:
        f.write(html)
    print("Wrote docs/index.html")
