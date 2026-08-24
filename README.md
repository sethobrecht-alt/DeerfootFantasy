# League site

A static site that rebuilds itself every Tuesday from your ESPN fantasy league:
matchup recaps, a penalty flag for every high scorer left on a bench, and power
rankings blending points and record. One team is permanently exempt from
criticism. You know which one.

## Preview it first

```bash
pip install -r requirements.txt
python build.py --demo
open docs/index.html
```

That uses fake data — no ESPN account, no API key. Check the design, then wire up
the real thing.

## Setup

### 1. Fill in `config.json`

```json
{
  "league_id": 123456,
  "year": 2026,
  "site_title": "Your League Name",
  "favourite_team": "Your Team Name",
  "shield_favourite": true,
  "power_ranking_weights": { "points": 0.6, "record": 0.4 }
}
```

- **league_id** — the number in your ESPN league URL after `leagueId=`.
- **favourite_team** — must match your team name in ESPN *exactly*, including
  capitalisation. If it doesn't match, nothing breaks, you just stop getting
  special treatment.
- **shield_favourite** — keeps your team off the penalty board entirely. Set to
  `false` if you want to at least appear impartial.
- **weights** — must be how you want points and record traded off. They're
  normalised, so `0.6 / 0.4` and `6 / 4` do the same thing.

### 2. Get your ESPN cookies

Private leagues need two cookies. In a desktop browser, log in to ESPN, open your
league page, then open developer tools → Application → Cookies → `espn.com`.
Copy the values of **`espn_s2`** (long) and **`SWID`** (short, in curly braces —
keep the braces).

Treat these like a password. They authenticate as you.

### 3. Add repository secrets

Repo → Settings → Secrets and variables → Actions → New repository secret:

| Name | Value |
|---|---|
| `ESPN_S2` | your `espn_s2` cookie |
| `SWID` | your `SWID` cookie, braces included |
| `ANTHROPIC_API_KEY` | from console.anthropic.com |

### 4. Turn on Pages

Repo → Settings → Pages → Source: **Deploy from a branch**, branch `main`,
folder **`/docs`**. Your site lands at
`https://<username>.github.io/<repo>/`.

### 5. Run it once by hand

Actions → Weekly update → Run workflow. After that it runs itself at noon ET
every Tuesday.

## How it works

```
build.py       fetch new weeks → write recaps → rebuild pages
league.py      ESPN data, bench-blunder math, power rankings
recaps.py      Anthropic API calls, one per matchup
render.py      Jinja2 → docs/
data/          one JSON file per week (the cache)
docs/          the site itself
```

Weeks already in `data/` are never refetched and their recaps are never
rewritten. A rerun costs nothing and the text your league already read stays
put. To force a rewrite of one week, run the workflow manually with a week
number, or locally:

```bash
python build.py --week 5
```

Recaps cost roughly a cent a week at typical league sizes.

## Bench blunders

For each benched player, from the highest scorer down, the script finds the
weakest starter that player was actually eligible to replace. Once a swap is
counted, that slot is spoken for, so nobody gets blamed twice for the same
lineup spot. A bench player who wasn't eligible anywhere, or who outscored
nobody, produces no flag.

This means the numbers are defensible when someone complains. They will complain.

## Things that will eventually go wrong

**ESPN changes their API.** It's undocumented and they break it every year or
two without notice. When the workflow starts failing, update `espn-api`:
`pip install -U espn-api`. If that doesn't fix it, check the package's issue
tracker — someone else has already hit it.

**Your cookies expire.** They last months, not forever. When the build starts
returning empty data or 401s, pull fresh cookies and update the secrets.

**Stat corrections.** ESPN adjusts scores Tuesday and Wednesday. The Tuesday
midday run catches most but not all. Rerun a week with `--week N` if a score
changes after publication.

**Scheduled workflows get disabled** after 60 days without repository activity.
That won't bite mid-season, but expect to re-enable it each August.

## Tuning the voice

The recap style lives in `VOICE` in `recaps.py`, and your team's permanent
immunity lives in `FAVOURITE_RULE` right below it. Both are plain English —
edit them and rerun with `--week N` to see the difference.
