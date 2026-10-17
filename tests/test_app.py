import json

import pytest

from app import create_app
from models import Player, Round, db


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def totals(client):
    rows = client.get("/export.csv").get_data(as_text=True).strip().splitlines()[1:]
    return {row.split(",")[1]: int(row.split(",")[-1]) for row in rows}


def player_ids(app):
    with app.app_context():
        return {p.name: p.id for p in Player.query.all()}


def test_pages_render(client):
    assert client.get("/").status_code == 200
    assert client.get("/scoreboard").status_code == 200


def test_add_players_from_pasted_list(client, app):
    response = client.post("/players", data={"names": "Alice, Bob\nCara\n\n"})
    assert response.status_code == 200
    assert set(player_ids(app)) == {"Alice", "Bob", "Cara"}


def test_full_round_with_tie_and_manual_edits(client, app):
    client.post("/players", data={"names": "Alice, Bob, Cara, Dan"})
    ids = player_ids(app)

    client.post("/rounds")
    with app.app_context():
        rnd = Round.query.filter_by(status="open").one()
        round_id = rnd.id
        assert rnd.max_points == 4  # defaults to the number of players

    order = [{"id": ids["Cara"], "tie": False}, {"id": ids["Alice"], "tie": False}, {"id": ids["Bob"], "tie": True}]
    response = client.post(f"/rounds/{round_id}/confirm", data={"order": json.dumps(order), "max_points": "4"})
    assert "confetti" in json.loads(response.headers["HX-Trigger"])
    assert totals(client) == {"Cara": 4, "Alice": 3, "Bob": 3, "Dan": 0}

    client.patch(f"/scores/{round_id}/{ids['Dan']}", data={"points": "2"})
    client.post(f"/players/{ids['Alice']}/adjust", data={"amount": "1"})
    client.patch(f"/players/{ids['Bob']}/bonus", data={"bonus": "-2"})
    client.patch(f"/players/{ids['Cara']}", data={"name": "Cara B."})
    assert totals(client) == {"Cara B.": 4, "Alice": 4, "Bob": 1, "Dan": 2}

    client.patch(f"/rounds/{round_id}", data={"max_points": "10"})
    client.post(f"/rounds/{round_id}/recalc")
    assert totals(client) == {"Cara B.": 10, "Alice": 10, "Bob": 7, "Dan": 0}


def test_leaderboard_returns_204_when_unchanged(client):
    client.post("/players", data={"names": "Alice"})
    html = client.get("/partials/leaderboard").get_data(as_text=True)
    version = html.split('data-version="')[1].split('"')[0]
    assert client.get(f"/partials/leaderboard?v={version}").status_code == 204


def test_reset_keeps_players_when_asked(client, app):
    client.post("/players", data={"names": "Alice"})
    client.post(f"/players/{player_ids(app)['Alice']}/adjust", data={"amount": "5"})
    client.post("/reset", data={"mode": "scores"})
    assert totals(client) == {"Alice": 0}
    client.post("/reset", data={"mode": "all"})
    assert totals(client) == {}
