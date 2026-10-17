"""Pure scoring helpers: turn finishing places into points and totals into ranks."""


def points_for_place(place, last_place):
    """Last place earns 0 and each place above it earns one more."""
    if place is None or place < 1:
        return 0
    return max(last_place - place, 0)


def places_for_round(order, player_ids):
    """Places for everyone in a round: the clicked order, then anyone unclicked tied for last.

    Returns a list of (player_id, place) covering every id in `player_ids`.
    """
    placed = places_from_order(order)
    seen = {player_id for player_id, _ in placed}
    unplaced = [player_id for player_id in player_ids if player_id not in seen]
    return placed + [(player_id, len(placed) + 1) for player_id in unplaced]


def last_place(places):
    """The bottom place in a round. Older rounds may store None for unplaced players."""
    known = [place for place in places if place is not None]
    if len(known) < len(places):
        return len(known) + 1
    return max(known, default=0)


def places_from_order(order):
    """Assign standard competition places ("1, 2, 2, 4") to a finishing order.

    `order` is a list of (player_id, tied_with_previous) tuples, first finisher first.
    Returns a list of (player_id, place) tuples in the same order.
    """
    placed = []
    place = 0
    for index, (player_id, tied) in enumerate(order):
        if not (tied and placed):
            place = index + 1
        placed.append((player_id, place))
    return placed


def rank_totals(entries):
    """Sort (item, total) pairs high to low and attach shared ranks.

    Returns a list of (rank, item, total). Equal totals share a rank and the
    next rank skips ahead, e.g. 10, 8, 8, 5 -> ranks 1, 2, 2, 4.
    """
    ordered = sorted(entries, key=lambda entry: entry[1], reverse=True)
    ranked = []
    for index, (item, total) in enumerate(ordered):
        if ranked and total == ranked[-1][2]:
            rank = ranked[-1][0]
        else:
            rank = index + 1
        ranked.append((rank, item, total))
    return ranked
