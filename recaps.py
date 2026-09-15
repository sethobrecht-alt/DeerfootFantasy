"""Write the weekly recaps.

One API call per matchup, plus one for the week's headline. Results are cached
in data/week_N.json, so a rerun costs nothing and the text never changes under
you after people have read it.
"""

import json
import os
import random
from collections import Counter
from anthropic import Anthropic

MODEL = "claude-sonnet-5"
LORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "team_lore.json")

VOICE = """You write recaps for a private fantasy football league of longtime \
friends. House style:

- Two short paragraphs, 90-140 words total. No headers, no bullet points.
- Name actual players and actual point totals. Specifics are the whole joke.
- This is a roast more than a report. Roast the STARTERS who actually played \
and underperformed, not who got left on the bench — bench mistakes already get \
their own callout elsewhere on the page, so do not mention who was benched or \
who should have started instead.
- Make fun of the teams and the decisions their managers made — needling and a \
little mean is encouraged, these are close friends who give each other a hard \
time. Never actually cruel: the target is always the fantasy team and its \
lineup, never anyone's real life.
- Frame each matchup as a coaching contest between the two managers. A \
nickname (see below) already IS the manager, not the team — write their \
coaching directly under that name ("Flame On read the matchup well", "the \
Chair Force never adjusted"), never as "[nickname]'s manager" or "the manager \
of [nickname]". When using a team's real name instead, "the manager" or "the \
skipper" is fine. The winning side coached well and adapted — good process, a \
real feel for the matchup, not just good luck. The losing side gets blamed for \
poor coaching — a bad game plan, out-schemed, never just bad luck. Keep this \
in general coaching language (game plan, adjustments, feel for the matchup), \
not literal lineup swaps — that's still off-limits in the prose.
- "Boss" and "Beak" are the two most load-bearing words in the house \
vocabulary — they mean good/positive and bad/negative. Use them a lot, most \
recaps should have several. Never use plain words like "good," "bad," \
"great," "terrible," "strong," "weak," or other synonyms for positive/ \
negative in the recap text itself — use "Boss" or "Beak" (or a phrase built \
around one of them) in their place instead.
- Never explain fantasy football. Never open with "In a thrilling matchup."
- No emoji. No exclamation marks.

Return only the recap text."""

FAVOURITE_RULE = """

IMPORTANT: {team} is the commissioner's own team and this site exists partly to \
flatter them. Whatever happened, {team} comes out looking good. A win is \
vindication and evidence of a deep understanding of the game — {team} coached \
brilliantly and adapted well (if you use a nickname for them, that nickname \
IS the manager — never "{team}'s manager"). A loss is variance, a brutal \
schedule, an opponent who got lucky, or officiating beyond anyone's control — \
never a bad decision by {team}, and never blamed on their coaching or game \
plan. Never \
criticise their lineup, never mention points they left on their bench, and \
never call them lucky. Be warm about them and normal about the opponent. Keep \
it deadpan enough to be funny rather than sycophantic."""

STEFANOWICZ_RULE = """

The Goose is Loose's manager's last name is Stefanowicz. Work in a misspelling \
of "Stefanowicz" somewhere in this recap — never spell it correctly, and use a \
different misspelling than you'd typically default to. This is mandatory."""

CHIEF_RON_VOICE_ON = """

The losing team scored under 70 points this week — that's the one and only \
trigger for "Chief Ron Voice." Work in the phrase Chief Ron Voice: "I'm \
disappointed in you" somewhere in this recap. This is mandatory."""

CHIEF_RON_VOICE_OFF = """

Do not use the phrase "Chief Ron Voice" anywhere in this recap, in full or in \
any softened, partial, or joking allusion to it (no "almost got some work," \
no "Chief Ron Voice territory," nothing). It only ever appears in a recap \
where the losing team scored under 70 points, and that's not this matchup."""

BLOWOUT_ON = """

This matchup was decided by 30 points or more — that's the one and only \
trigger for the Tetherball line. Work in the exact phrase "looked like a \
Woodsman playing Chief Tyler Hallenbeck in Tetherball" for the losing side \
somewhere in this recap. This is mandatory."""

BLOWOUT_OFF = """

Do not use the phrase "looked like a Woodsman playing Chief Tyler \
Hallenbeck in Tetherball" anywhere in this recap, in full or in any \
softened or partial allusion to it. It only applies to a matchup decided \
by 30 points or more, and this matchup doesn't qualify."""

BRING_DOWN_THE_ROOF_ON = """

{team} had the single largest margin of victory across the entire week — \
that's the one and only trigger for this line. Work in the exact phrase \
"I want you to BRING DOWN THE ROOF" for {team} somewhere in this recap. \
This is mandatory."""

BRING_DOWN_THE_ROOF_OFF = """

Do not use the phrase "I want you to BRING DOWN THE ROOF" anywhere in this \
recap, in full or in any softened or partial allusion to it. It's reserved \
for whichever matchup has the single largest margin of victory across the \
entire week, and this matchup doesn't qualify."""

POINT_AND_BACK_ON = """

{team} just extended a losing streak to 2 games or more. Work in the exact \
phrase "is stuck on the Point and Back" for {team} somewhere in this recap \
— always the full phrase, never shortened to "stuck on the Point" or \
similar (that's a different reference and shortening it ruins this one). \
This is mandatory."""

POINT_AND_BACK_OFF = """

Do not use the phrase "is stuck on the Point and Back," or any shortened \
version of it like "stuck on the Point," anywhere in this recap. It only \
applies to a team on a losing streak of 2 games or more, and neither team \
in this matchup qualifies this week."""

PHRASE_LIMIT_RULE = """

Phrase variety: there's a full house vocabulary below specifically so you \
don't have to lean on the same two or three phrases every week — use it. \
No single phrase from that list should appear more than once across the \
whole week's recaps. These have already been used this week — do not \
use them again, pick something else that fits instead: {maxed_out}"""

PHRASE_LIMIT_RETRY = """

Your last draft used a phrase that had already been used elsewhere this \
week, before this recap was even written: {terms}. That's a hard rule, not \
a suggestion — rewrite the recap without it (or them), using different \
vocabulary for that beat instead."""

FORCED_CALLOUT_RULE = """

Mandatory: work in the exact phrase "{phrase}" for {player} somewhere in \
this recap. This specific callout has been requested for this matchup."""

BAD_GENERAL_ASSIGNED = """

Mandatory: work in the exact phrase "{term}" somewhere in this recap, for \
the losing side. It's from the "Terms for Bad Performance (General)" \
family, and this specific matchup has been assigned that specific phrase \
this week (a few other bad-performance matchups each got a different one, \
so the week doesn't lean on the same one or two every time) — use this one \
here, not a different phrase from that same family."""

LORE_RULE = """

House vocabulary. These phrases are the backbone of the site's voice, not \
seasoning — work in two or three per recap where they genuinely fit what \
happened, not just "Boss" and "Beak" every time. Several phrases below mean \
close to the same thing on purpose (several ways to say a team looked lost, \
several ways to say a win was easy) — that's real range, not filler, so \
rotate through the alternatives instead of defaulting to the same one or \
two every week. Use each phrase EXACTLY as written below — don't shorten, \
paraphrase, or lightly reword it. A phrase like "is stuck on the Point and \
Back" stops working as a callback the moment it becomes "stuck on the \
Point" — small changes break the reference for people who already know \
these phrases. If you're unsure what a phrase actually means or how it \
would apply here, leave it out rather than guessing:
{vocab_lines}

Nicknames. Each team below has a short list of nicknames — these belong to \
the team's MANAGER, not the team itself. A nickname is a stand-in name for a \
person: write their actions directly under it ("Flame On started slow", not \
"Flame On's manager started slow" or "the manager of Flame On"). Pick AT MOST \
ONE nickname per team and use it in place of the team's real name (or \
introduce it once alongside the real name, then keep using the nickname). \
Never use more than one nickname for the same team in a single recap. It's \
fine to use zero nicknames, or a nickname for only one of the two teams, if \
nothing fits.
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


CATEGORY_LABELS = {
    "good": "Terms for Good Performance",
    "bad-general": "Terms for Bad Performance (General)",
    "bad-player": "Terms for Bad Performance (Player Specific)",
}


def _lore_rule(home_name, away_name):
    lore = _lore()
    vocab = lore.get("vocab", [])
    # Grouping by category (rather than one flat list) makes the "these
    # several phrases are interchangeable, rotate through them" instruction
    # above concrete -- the model can see the alternatives sitting together.
    lines = [f"- {v['term']} = {v['meaning']}" for v in vocab if "category" not in v]
    for category, label in CATEGORY_LABELS.items():
        group = [v for v in vocab if v.get("category") == category]
        if not group:
            continue
        lines.append(f"\n{label}:")
        lines.extend(f"- {v['term']} = {v['meaning']}" for v in group)
    vocab_lines = "\n".join(lines)
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


def _loser(m):
    """The losing team's name. Only meaningful when m["winner"] is set."""
    return m["away"]["name"] if m["winner"] == m["home"]["name"] else m["home"]["name"]


def _losing_streaks(prior_weeks):
    """team name -> consecutive losses through the most recent prior week."""
    streaks = {}
    for week in prior_weeks:
        for m in week["matchups"]:
            h, a = m["home"]["name"], m["away"]["name"]
            if not m["winner"]:
                streaks[h] = 0
                streaks[a] = 0
                continue
            loser = a if m["winner"] == h else h
            for team in (h, a):
                streaks[team] = streaks.get(team, 0) + 1 if team == loser else 0
    return streaks


def write_recaps(week_data, favourite_team, cache_path, prior_weeks=None, forced_callouts=None):
    """Fill in recap text for every matchup, using the cache where possible.

    forced_callouts: optional {player_name: phrase} -- for a matchup that
    includes that player as a starter, mandate that exact phrase appear
    for them. Meant for "make sure this specific thing gets called out"
    requests, not for standing house vocabulary (that belongs in
    team_lore.json instead).
    """
    cached = {}
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            old = json.load(f)
        cached = {m.get("key"): m.get("recap") for m in old.get("matchups", [])}
        week_data["headline"] = old.get("headline", "")

    # "BRING DOWN THE ROOF" belongs to whichever matchup has the single
    # largest margin of victory across the whole week -- that's a
    # whole-week superlative no individual recap call can determine on its
    # own, so it has to be picked up front.
    winning_matchups = [m for m in week_data["matchups"] if m["winner"]]
    roof_match = max(winning_matchups, key=lambda m: m["margin"], default=None)

    prior_streaks = _losing_streaks(prior_weeks or [])

    # General vocab phrases (everything except Boss/Beak, which are meant to
    # appear constantly) are capped at once across the week -- same problem
    # as the dedicated phrases above: no recap can see what another already
    # said, so the running count has to be tracked here and fed forward.
    vocab_terms = [v["term"] for v in _lore().get("vocab", []) if v["term"] not in ("Boss", "Beak")]
    phrase_counts = Counter()

    def record_usage(text):
        lower = text.lower()
        for term in vocab_terms:
            n = lower.count(term.lower())
            if n:
                phrase_counts[term] += n

    # The once-a-week cap stops any one phrase from dominating, but on its
    # own it still lets the model settle into the same one or two "general
    # bad performance" favorites and ignore the rest of that family. Force
    # the issue: assign a handful of losing matchups each a different
    # phrase from that family up front, so the week is guaranteed real
    # spread rather than just staying under the cap.
    bad_general_terms = [
        v["term"] for v in _lore().get("vocab", []) if v.get("category") == "bad-general"
    ]

    # The shielded favourite is never framed as having played badly, so a
    # matchup they lost isn't eligible to carry one of these phrases.
    bad_general_eligible = [
        m for m in week_data["matchups"] if m["winner"] and _loser(m) != favourite_team
    ]
    random.shuffle(bad_general_eligible)
    target_n = min(4, len(bad_general_eligible), len(bad_general_terms))
    assigned_bad_general = dict(zip(
        (id(m) for m in bad_general_eligible[:target_n]),
        random.sample(bad_general_terms, target_n),
    ))

    client = _client()
    for m in week_data["matchups"]:
        m["key"] = f"{m['home']['team_id']}v{m['away']['team_id']}"
        if cached.get(m["key"]):
            m["recap"] = cached[m["key"]]
            record_usage(m["recap"])
            continue
        if not client:
            m["recap"] = _fallback(m)
            continue

        names = (m["home"]["name"], m["away"]["name"])
        system = VOICE + _lore_rule(*names)
        if favourite_team in names:
            system += FAVOURITE_RULE.format(team=favourite_team)
        if "The Goose is Loose" in names:
            system += STEFANOWICZ_RULE
        loser_score = min(m["home"]["score"], m["away"]["score"])
        system += CHIEF_RON_VOICE_ON if loser_score < 70 else CHIEF_RON_VOICE_OFF
        system += BLOWOUT_ON if m["winner"] and m["margin"] >= 30 else BLOWOUT_OFF
        system += (
            BRING_DOWN_THE_ROOF_ON.format(team=m["winner"])
            if m is roof_match else BRING_DOWN_THE_ROOF_OFF
        )

        point_and_back_team = None
        if m["winner"] and prior_streaks.get(_loser(m), 0) + 1 >= 2:
            point_and_back_team = _loser(m)
        system += (
            POINT_AND_BACK_ON.format(team=point_and_back_team)
            if point_and_back_team else POINT_AND_BACK_OFF
        )

        assigned_term = assigned_bad_general.get(id(m))
        if assigned_term:
            system += BAD_GENERAL_ASSIGNED.format(term=assigned_term)

        if forced_callouts:
            starters = m["home"]["starters"] + m["away"]["starters"]
            starter_names = {p["name"] for p in starters}
            for player, phrase in forced_callouts.items():
                if player in starter_names:
                    system += FORCED_CALLOUT_RULE.format(phrase=phrase, player=player)

        # Exclude the term just mandated above (if any) -- with a one-use
        # cap, a term can go from unused to maxed the instant an earlier
        # matchup happens to use it, and this matchup's own mandate would
        # otherwise contradict the "don't use it" instruction below.
        maxed_out = [
            t for t in vocab_terms if phrase_counts[t] >= 1 and t != assigned_term
        ]
        if maxed_out:
            system += PHRASE_LIMIT_RULE.format(maxed_out="; ".join(maxed_out))

        try:
            m["recap"] = _ask(client, system, _matchup_prompt(m, week_data["week"]))
            # The live reminder above isn't airtight -- verify the draft
            # didn't reuse a phrase that was already at cap, and if it did,
            # give it a couple of shots at a rewrite with an unambiguous ban.
            # A retry can dodge the letter of the ban ("a Dutch Oven's
            # cousin") while still tripping the same substring check, so
            # this loops rather than trusting the first rewrite.
            for _ in range(2):
                if not m["recap"]:
                    break
                violated = [t for t in maxed_out if t.lower() in m["recap"].lower()]
                if not violated:
                    break
                retry_system = system + PHRASE_LIMIT_RETRY.format(terms="; ".join(violated))
                try:
                    m["recap"] = _ask(client, retry_system, _matchup_prompt(m, week_data["week"]))
                except Exception as err:
                    print(f"Phrase-limit retry failed for {m['key']}: {err}")
                    break
            if not m["recap"]:
                # _ask() can legitimately return "" (a response with no text
                # content) without raising -- that's still a failure, not a
                # valid recap, and needs the same fallback as an exception.
                raise ValueError("model returned an empty recap")
            record_usage(m["recap"])
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
