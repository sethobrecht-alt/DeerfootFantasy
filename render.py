"""Turn cached week data into the static pages GitHub Pages serves."""

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
    archive[-1]["href"] = "index.html"
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
        name = "index.html" if is_latest else f"week-{week['week']}.html"
        with open(os.path.join(DOCS, name), "w") as f:
            f.write(html)
        print(f"Wrote docs/{name}")

    open(os.path.join(DOCS, ".nojekyll"), "w").close()
