import json

import pytest

from app import create_app
from models import Round, db
from tasks import load_tasks, pick_task

CSV = """id,category,text
1,speed,"Speed one"
2,speed,"Speed two"
3,find,"Find one"
4,judged,"Judged one"
"""

GIMMICKS = """id,text,rule
1,"Gimmick one","Rule one"
2,"Gimmick two",""
"""


@pytest.fixture
def app(tmp_path):
    tasks_file = tmp_path / "tasks.csv"
    tasks_file.write_text(CSV, encoding="utf-8")
    gimmicks_file = tmp_path / "gimmicks.csv"
    gimmicks_file.write_text(GIMMICKS, encoding="utf-8")
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "TASKS_FILE": str(tasks_file),
        "GIMMICKS_FILE": str(gimmicks_file),
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    client = app.test_client()
    client.post("/players", data={"names": "Alice, Bob"})
    return client


def open_round(app):
    with app.app_context():
        return Round.query.filter_by(status="open").one()


def test_load_tasks_reads_csv(app):
    tasks = load_tasks(app.config["TASKS_FILE"])
    assert [(t.id, t.category) for t in tasks] == [(1, "speed"), (2, "speed"), (3, "find"), (4, "judged")]


def test_pick_task_prefers_unplayed_and_never_repeats_current(app):
    tasks = load_tasks(app.config["TASKS_FILE"])
    for _ in range(20):
        assert pick_task(tasks, avoid={1, 2, 3}, never={4}).id in {1, 2, 3}
        assert pick_task(tasks, avoid={1, 2}, never={4}).id == 3


def test_new_round_rolls_distinct_main_and_backup(client, app):
    client.post("/rounds")
    rnd = open_round(app)
    assert rnd.task_id and rnd.backup_task_id and rnd.task_id != rnd.backup_task_id
    assert not rnd.gimmick


def test_reroll_pick_swap_and_gimmick(client, app):
    client.post("/rounds")
    rnd = open_round(app)

    client.post(f"/rounds/{rnd.id}/task", data={"slot": "main"})
    rerolled = open_round(app)
    assert rerolled.task_id not in {rnd.task_id, rnd.backup_task_id}

    client.post(f"/rounds/{rnd.id}/task", data={"slot": "main", "task_id": "2"})
    client.post(f"/rounds/{rnd.id}/task", data={"slot": "backup", "task_id": "3"})
    assert (open_round(app).task_id, open_round(app).backup_task_id) == (2, 3)

    client.post(f"/rounds/{rnd.id}/swap")
    assert (open_round(app).task_id, open_round(app).backup_task_id) == (3, 2)

    client.post(f"/rounds/{rnd.id}/gimmick")
    assert open_round(app).gimmick
    assert open_round(app).gimmick_task_id in {1, 2}
    page = client.get("/").get_data(as_text=True)
    assert "Gimmick one" in page or "Gimmick two" in page

    # Confirm the gimmick round; the next round is back to normal tasks.
    with app.app_context():
        alice_id = db.session.execute(db.text("select id from player where name='Alice'")).scalar()
    client.post(f"/rounds/{rnd.id}/confirm", data={"order": json.dumps([{"id": alice_id}])})
    client.post("/rounds")
    next_round = open_round(app)
    assert not next_round.gimmick and next_round.task_id


def test_played_tasks_are_not_rolled_again_until_exhausted(client, app):
    with app.app_context():
        alice_id = db.session.execute(db.text("select id from player where name='Alice'")).scalar()
    played = []
    for _ in range(4):
        client.post("/rounds")
        rnd = open_round(app)
        played.append(rnd.task_id)
        client.post(f"/rounds/{rnd.id}/confirm", data={"order": json.dumps([{"id": alice_id}])})
    assert sorted(played) == [1, 2, 3, 4]


def test_gimmick_reroll_and_pick(client, app):
    client.post("/rounds")
    rnd = open_round(app)
    client.post(f"/rounds/{rnd.id}/task", data={"slot": "gimmick", "task_id": "1"})
    assert open_round(app).gimmick and open_round(app).gimmick_task_id == 1
    assert "Rule one" in client.get("/partials/leaderboard").get_data(as_text=True)
    client.post(f"/rounds/{rnd.id}/task", data={"slot": "gimmick"})
    assert open_round(app).gimmick_task_id == 2
    # Turning gimmick off and on again keeps the gimmick that was rolled.
    client.post(f"/rounds/{rnd.id}/gimmick")
    client.post(f"/rounds/{rnd.id}/gimmick")
    assert open_round(app).gimmick_task_id == 2


def test_task_manager_add_edit_delete(client, app):
    assert client.get("/partials/tasks?kind=tasks").status_code == 200
    client.post("/tasks/tasks", data={"category": "Find", "text": "Find a cat"})
    client.patch("/tasks/tasks/1", data={"category": "speed", "text": "Speed one, edited"})
    client.delete("/tasks/tasks/2")
    tasks = load_tasks(app.config["TASKS_FILE"])
    assert [(t.id, t.category, t.text) for t in tasks] == [
        (1, "speed", "Speed one, edited"), (3, "find", "Find one"), (4, "judged", "Judged one"), (5, "find", "Find a cat"),
    ]

    client.post("/tasks/gimmicks", data={"text": "No jumping", "rule": "Jumping is banned"})
    client.patch("/tasks/gimmicks/2", data={"text": "Gimmick two", "rule": "New rule"})
    gimmicks = load_tasks(app.config["GIMMICKS_FILE"], "gimmick")
    assert [(t.id, t.text, t.rule) for t in gimmicks] == [
        (1, "Gimmick one", "Rule one"), (2, "Gimmick two", "New rule"), (3, "No jumping", "Jumping is banned"),
    ]


def test_task_manager_rejects_blank_text(client, app):
    response = client.post("/tasks/tasks", data={"category": "find", "text": "  "})
    assert "warning" in response.headers["HX-Trigger"]
    assert len(load_tasks(app.config["TASKS_FILE"])) == 4
    assert client.post("/tasks/nope", data={"text": "x"}).status_code == 404
