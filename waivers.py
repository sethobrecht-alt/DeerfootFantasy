"""Weekly waiver-wire recap: every processed move, with automatic callouts
for contested pickups and FAAB overpays.

ESPN doesn't expose losing bids through the normal activity feed -- only
league.transactions() with WAIVER_ERROR included does, and only indirectly:
a losing claim on a player someone else won gets marked
FAILED_INVALIDPLAYERSOURCE (the player stops being a valid waiver target the
moment the winning claim executes first). That status is the only signal
available for "how many teams wanted this guy" and "how much did the winner
pay over the next-best offer" -- there's no direct bid-history endpoint.
"""

WON_STATUS = "EXECUTED"
LOSING_STATUS = "FAILED_INVALIDPLAYERSOURCE"

BLOWN_ACCOUNT_THRESHOLD = 50
FUDJO_OVERPAY_THRESHOLD = 7


def fetch_week_waivers(league, week):
    """Every waiver/free-agent move that processed for the given week, plus
    the deterministic weekly callouts (no AI involved -- this page runs
    unattended every Wednesday morning)."""
    txns = league.transactions(scoring_period=week, types={"FREEAGENT", "WAIVER", "WAIVER_ERROR"})

    # player name -> {team_name: (status, bid)}, keeping each team's
    # highest-bid record for that player (their real final claim -- earlier
    # PENDING/CANCELED resubmissions from the same team are just noise).
    bids_by_player = {}
    won = []
    for t in txns:
        if t.type != "WAIVER" or t.status not in (WON_STATUS, LOSING_STATUS):
            continue
        add_item = next((i for i in t.items if i.type == "ADD"), None)
        if not add_item:
            continue
        bucket = bids_by_player.setdefault(add_item.player, {})
        prev = bucket.get(t.team.team_name)
        if not prev or t.bid_amount > prev[1]:
            bucket[t.team.team_name] = (t.status, t.bid_amount)
        if t.status == WON_STATUS:
            drop_item = next((i for i in t.items if i.type == "DROP"), None)
            won.append({
                "player": add_item.player,
                "team": t.team.team_name,
                "bid": t.bid_amount,
                "dropped": drop_item.player if drop_item else None,
            })

    moves = []
    for w in won:
        bucket = bids_by_player.get(w["player"], {})
        other_losing_bids = [
            bid for team, (status, bid) in bucket.items()
            if team != w["team"] and status == LOSING_STATUS
        ]
        next_best = max(other_losing_bids) if other_losing_bids else None
        floor = (next_best + 1) if next_best is not None else 1
        moves.append({
            **w,
            "bidder_count": len(bucket),
            "next_best_bid": next_best,
            "overpay": max(0, w["bid"] - floor) if w["bid"] > 0 else 0,
        })
    for m in moves:
        m["blew_the_account"] = m["bid"] > BLOWN_ACCOUNT_THRESHOLD
        m["dropped_fudjo"] = m["overpay"] > FUDJO_OVERPAY_THRESHOLD

    # Free-agent adds are zero-cost and uncontested by definition -- no
    # bidding process, so they're listed but never eligible for a callout.
    fa_moves = []
    for t in txns:
        if t.type == "FREEAGENT" and t.status == WON_STATUS:
            add_item = next((i for i in t.items if i.type == "ADD"), None)
            if not add_item:
                continue
            drop_item = next((i for i in t.items if i.type == "DROP"), None)
            fa_moves.append({
                "player": add_item.player,
                "team": t.team.team_name,
                "dropped": drop_item.player if drop_item else None,
            })

    chipwich = max(moves, key=lambda m: m["bidder_count"], default=None)
    if chipwich and chipwich["bidder_count"] <= 1:
        chipwich = None

    camp_chair = max(moves, key=lambda m: m["bid"], default=None)
    if camp_chair and camp_chair["bid"] <= 0:
        camp_chair = None

    bag_of_chips = min(
        moves, key=lambda m: (m["bid"], m["bidder_count"], m["player"]), default=None
    )

    fudjo_candidates = [m for m in moves if m["dropped_fudjo"]]
    fudjo = max(fudjo_candidates, key=lambda m: m["overpay"], default=None)

    return {
        "week": week,
        "budget": league.settings.acquisition_budget,
        "moves": sorted(moves, key=lambda m: m["bid"], reverse=True),
        "fa_moves": fa_moves,
        "chipwich": chipwich,
        "camp_chair": camp_chair,
        "bag_of_chips": bag_of_chips,
        "fudjo": fudjo,
        "total_spent": sum(m["bid"] for m in moves),
    }
