"""Pure scoring helpers: turn finishing places into points and totals into ranks."""


def points_for_place(place, max_points):
    """1st place earns max_points, each place after earns one fewer, never below zero."""
    if place is None or place < 1:
        return 0
    return max(max_points - (place - 1), 0)


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
