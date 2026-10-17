from scoring import last_place, places_for_round, places_from_order, points_for_place, rank_totals


def test_last_place_gets_zero_and_each_place_up_earns_one_more():
    assert [points_for_place(place, 6) for place in range(1, 7)] == [5, 4, 3, 2, 1, 0]


def test_points_never_go_below_zero():
    assert points_for_place(8, 5) == 0


def test_missing_place_scores_zero():
    assert points_for_place(None, 5) == 0


def test_unclicked_players_tie_for_last():
    places = places_for_round([(1, False), (2, False)], [1, 2, 3, 4])
    assert places == [(1, 1), (2, 2), (3, 3), (4, 3)]
    bottom = last_place([place for _, place in places])
    assert [points_for_place(place, bottom) for _, place in places] == [2, 1, 0, 0]


def test_everyone_clicked_counts_down_to_zero():
    order = [(pid, False) for pid in (1, 2, 3, 4)]
    places = places_for_round(order, [1, 2, 3, 4])
    bottom = last_place([place for _, place in places])
    assert [points_for_place(place, bottom) for _, place in places] == [3, 2, 1, 0]


def test_tie_for_last_still_gets_zero():
    order = [(1, False), (2, False), (3, False), (4, True)]
    places = places_for_round(order, [1, 2, 3, 4])
    bottom = last_place([place for _, place in places])
    assert [points_for_place(place, bottom) for _, place in places] == [2, 1, 0, 0]


def test_last_place_treats_missing_places_as_tied_last():
    assert last_place([1, 2, None, None]) == 3
    assert last_place([]) == 0


def test_places_without_ties():
    order = [(11, False), (12, False), (13, False)]
    assert places_from_order(order) == [(11, 1), (12, 2), (13, 3)]


def test_tied_players_share_a_place_and_the_next_place_skips():
    order = [(1, False), (2, False), (3, True), (4, False)]
    assert places_from_order(order) == [(1, 1), (2, 2), (3, 2), (4, 4)]
    points = [points_for_place(place, 4) for _, place in places_from_order(order)]
    assert points == [3, 2, 2, 0]


def test_tie_flag_on_first_pick_is_ignored():
    assert places_from_order([(1, True), (2, False)]) == [(1, 1), (2, 2)]


def test_three_way_tie():
    order = [(1, False), (2, True), (3, True), (4, False)]
    assert [place for _, place in places_from_order(order)] == [1, 1, 1, 4]


def test_rank_totals_shares_ranks():
    ranked = rank_totals([("a", 8), ("b", 10), ("c", 8), ("d", 5)])
    assert ranked == [(1, "b", 10), (2, "a", 8), (2, "c", 8), (4, "d", 5)]
