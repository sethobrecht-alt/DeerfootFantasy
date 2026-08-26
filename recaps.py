"""Write the weekly recaps.

One API call per matchup, plus one for the week's headline. Results are cached
in data/week_N.json, so a rerun costs nothing and the text never changes under
you after people have read it.
"""

import json
import os
from anthropic import Anthropic

MODEL = "claude-sonnet-5"
LORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "team_lore.json")

VOICE = """You write recaps for a private fantasy football league of longtime \
friends. House style:

- Two short paragraphs, 90-140 words total. No headers, no bullet points.
- Name actual players and actual point totals. Specifics are the whole joke.
- This is a roast more than a report. Make fun of the teams and the decisions \
their managers made — needling and a little mean is encouraged, these are \
close friends who give each other a hard time. Never actually cruel: the \
target is always the fantasy team and its lineup, never anyone's real life.
- Never explain fantasy football. Never open with "In a thrilling matchup."
- No emoji. No exclamation marks.

Return only the recap text."""

FAVOURITE_RULE = """

IMPORTANT: {team} is the commissioner's own team and this site exists partly to \
flatter them. Whatever happened, {team} comes out looking good. A win is \
vindication and evidence of a deep understanding of the game. A loss is variance, \
a brutal schedule, an opponent who got lucky, or officiating beyond anyone's \
control — never a bad decision by {team}. Never criticise their lineup, never \
mention points they left on their bench, and never call them lucky. Be warm about \
them and normal about the opponent. Keep it deadpan enough to be funny rather \
than sycophantic."""

LORE_RULE = """

House vocabulary. Use zero to a few of these where they genuinely fit what \
actually happened in this matchup — never force one in, and never use more \
than a handful in one recap:
{vocab_lines}

Nicknames. Each team below has a short list of nicknames. Pick AT MOST ONE \
nickname per team and use it in place of the team's real name (or introduce \
it once alongside the real name, then keep using the nickname). Never use \
more than one nickname for the same team in a single recap. It's fine to use \
zero nicknames, or a nickname for only one of the two teams, if nothing fits.
{home_team}: {home_nicknames}
{away_team}: {away_nicknames}"""


def _client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    return Anthropic(api_key=key)


def _lore():
    if not os.path.exists(LORE_PATH):
        return {"vocab": [], "nicknames": {}}
    with open(LORE_PATH) as f:
        return json.load(f)


def _lore_rule(home_name, away_name):
    lore = _lore()
    vocab_lines = "\n".join(
        f"- {v['term']} = {v['meaning']}" for v in lore.get("vocab", [])
    )
    nicknames = lore.get("nicknames", {})
    home_nicknames = ", ".join(nicknames.get(home_name, [])) or "(none)"
    away_nicknames = ", ".join(nicknames.get(away_name, [])) or "(none)"
    return LORE_RULE.format(
        vocab_lines=vocab_lines,
        home_team=home_name,
        home_nicknames=home_nicknames,
        away_team=away_name,
        away_nicknames=away_nicknames,
    )


def _side_brief(side):
    top = ", ".join(
        f"{p['name']} {p['points']}" for p in side["starters"][:3]
    )
    busts = [
        p for p in side["starters"]
        if p["projected"] >= 8 and p["points"] < p["projected"] * 0.5
    ]
    lines = [
        f"{side['name']} — {side['score']} points",
        f"  best starters: {top}",
    ]
    if busts:
        lines.append("  underperformed: " + ", ".join(
            f"{p['name']} {p['points']} (projected {p['projected']})" for p in busts[:3]
        ))
    if side["blunders"]:
        b = side["blunders"][0]
        lines.append(
            f"  left on bench: {b['should_have_started']} scored {b['bench_points']} "
            f"while {b['actually_started']} started at {b['slot']} for "
            f"{b['starter_points']} — {b['points_lost']} points lost"
        )
        lines.append(f"  total wasted on bench: {side['points_left_on_bench']}")
    return "\n".join(lines)


def _matchup_prompt(matchup, week):
    h, a = matchup["home"], matchup["away"]
    result = (
        f"{matchup['winner']} won by {matchup['margin']}"
        if matchup["winner"] else "Tie game"
    )
    return (
        f"Week {week}. {result}.\n\n{_side_brief(h)}\n\n{_side_brief(a)}\n\n"
        "Write the recap."
    )


def _ask(client, system, prompt):
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def _fallback(matchup):
    h, a = matchup["home"], matchup["away"]
    if not matchup["winner"]:
        return f"{h['name']} and {a['name']} tied at {h['score']}."
    loser = a if matchup["winner"] == h["name"] else h
    winner = h if matchup["winner"] == h["name"] else a
    return (
        f"{winner['name']} beat {loser['name']} {winner['score']}-{loser['score']}. "
        f"Top scorer: {winner['starters'][0]['name']} with "
        f"{winner['starters'][0]['points']}."
    )


def write_recaps(week_data, favourite_team, cache_path):
    """Fill in recap text for every matchup, using the cache where possible."""
    cached = {}
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            old = json.load(f)
        cached = {m.get("key"): m.get("recap") for m in old.get("matchups", [])}
        week_data["headline"] = old.get("headline", "")

    client = _client()
    for m in week_data["matchups"]:
        m["key"] = f"{m['home']['team_id']}v{m['away']['team_id']}"
        if cached.get(m["key"]):
            m["recap"] = cached[m["key"]]
            continue
        if not client:
            m["recap"] = _fallback(m)
            continue

        names = (m["home"]["name"], m["away"]["name"])
        system = VOICE + _lore_rule(*names)
        if favourite_team in names:
            system += FAVOURITE_RULE.format(team=favourite_team)
        try:
            m["recap"] = _ask(client, system, _matchup_prompt(m, week_data["week"]))
        except Exception as err:
            print(f"Recap failed for {m['key']}: {err}")
            m["recap"] = _fallback(m)

    if client and not week_data.get("headline"):
        summary = "\n".join(
            f"{m['home']['name']} {m['home']['score']} - "
            f"{m['away']['score']} {m['away']['name']}"
            for m in week_data["matchups"]
        )
        try:
            week_data["headline"] = _ask(
                client,
                "You write one-line headlines for a fantasy football league site. "
                "Under 9 words, no punctuation at the end, no quotation marks, "
                "sentence case. Dry. Return only the headline.",
                f"Week {week_data['week']} results:\n{summary}\n\nWrite the headline.",
            )
        except Exception as err:
            print(f"Headline failed: {err}")
            week_data["headline"] = f"Week {week_data['week']} in the books"
    elif not week_data.get("headline"):
        week_data["headline"] = f"Week {week_data['week']} in the books"

    return week_data
