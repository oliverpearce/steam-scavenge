"""Gameshow points tracker: Flask app factory and routes.

Mutating routes return HTML fragments for HTMX to swap in, plus an HX-Trigger
header that fires client-side toasts and confetti.
"""

import csv
import hashlib
import io
import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime

from flask import Flask, Response, abort, current_app, render_template, request
from sqlalchemy import func, inspect, text

from models import PALETTE, Player, Round, Score, Setting, db
from scoring import last_place, places_for_round, points_for_place, rank_totals
from sessions import delete_session, list_sessions, load_session, save_session
from tasks import (
    KINDS, Task, category_color, group_by_category, load_tasks, next_task_id, pick_task, save_tasks,
)

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def initials(name):
    return "".join(part[0] for part in name.split()[:2]).upper() or "?"


def nice_datetime(value):
    """'2026-10-17T19:42:05' -> 'Oct 17, 2026 · 7:42 PM'."""
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value or ""
    return f"{dt:%b} {dt.day}, {dt.year} · {int(dt.strftime('%I'))}:{dt:%M %p}"


def git_info(repo_dir):
    """Return (branch, short commit id) for the checkout, or (None, None) outside a git repo."""
    def run(*args):
        try:
            result = subprocess.run(
                ["git", *args], cwd=repo_dir, capture_output=True, text=True, timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return (result.stdout.strip() or None) if result.returncode == 0 else None

    return run("rev-parse", "--abbrev-ref", "HEAD"), run("rev-parse", "--short", "HEAD")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI="sqlite:///gameshow.db",  # stored in ./instance/
        GAME_TITLE=os.environ.get("GAMESHOW_TITLE", "steam scavenge"),
        TASKS_FILE=os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.csv"),
        GIMMICKS_FILE=os.path.join(os.path.dirname(os.path.abspath(__file__)), "gimmicks.csv"),
        SESSIONS_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions"),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        add_missing_columns()

    app.add_template_filter(ordinal)
    app.add_template_filter(initials)
    app.add_template_filter(nice_datetime)
    app.add_template_global(category_color)
    app.context_processor(lambda: {"palette": PALETTE, "tasks_enabled": tasks_enabled()})
    register_routes(app)
    return app


def add_missing_columns():
    """Bring databases created by older versions up to date (create_all won't add columns)."""
    existing = {column["name"] for column in inspect(db.engine).get_columns("round")}
    new_columns = {
        "task_id": "INTEGER",
        "backup_task_id": "INTEGER",
        "gimmick": "BOOLEAN NOT NULL DEFAULT 0",
        "gimmick_task_id": "INTEGER",
    }
    for name, ddl in new_columns.items():
        if name not in existing:
            db.session.execute(text(f'ALTER TABLE "round" ADD COLUMN {name} {ddl}'))
    db.session.commit()


# ---------------------------------------------------------------------------
# View-model helpers
# ---------------------------------------------------------------------------

def tasks_enabled():
    """Off means rounds are just placements and points: no tasks are rolled or shown."""
    setting = db.session.get(Setting, "tasks_enabled")
    return setting is not None and setting.value == "1"


def next_round_number():
    return (db.session.query(func.max(Round.number)).scalar() or 0) + 1


SLOT_FIELDS = {"main": "task_id", "backup": "backup_task_id", "gimmick": "gimmick_task_id"}


def task_list(kind):
    """"tasks" or "gimmicks", read from their CSV file."""
    spec = KINDS[kind]
    return load_tasks(current_app.config[spec["config"]], spec["category"])


def played_ids(field, gimmick):
    """Ids already played in finished rounds, so new rolls avoid repeats."""
    rounds = Round.query.filter_by(status="done", gimmick=gimmick).all()
    return {getattr(r, field) for r in rounds if getattr(r, field) is not None}


def roll_task(rnd, slot):
    """Give the round a fresh random task in `slot` ("main", "backup" or "gimmick")."""
    if slot == "gimmick":
        task = pick_task(
            task_list("gimmicks"), avoid=played_ids("gimmick_task_id", True), never={rnd.gimmick_task_id},
        )
    else:
        task = pick_task(
            task_list("tasks"), avoid=played_ids("task_id", False), never={rnd.task_id, rnd.backup_task_id},
        )
    if task:
        setattr(rnd, SLOT_FIELDS[slot], task.id)
    return task


def board_context():
    players = Player.query.order_by(Player.sort_order, Player.id).all()
    rounds = Round.query.filter_by(status="done").order_by(Round.number).all()
    open_round = Round.query.filter_by(status="open").first()

    totals = defaultdict(int)
    bonus = defaultdict(int)
    bonus_notes = defaultdict(list)
    cells = {}  # (player_id, round_id) -> Score
    for score in Score.query.order_by(Score.created_at).all():
        totals[score.player_id] += score.points
        if score.round_id is None:
            bonus[score.player_id] += score.points
            bonus_notes[score.player_id].append(f"{score.points:+d} {score.note or ''}".strip())
        else:
            cells[(score.player_id, score.round_id)] = score

    ranked = rank_totals([(p, totals[p.id]) for p in players])
    tasks = task_list("tasks")
    gimmicks = task_list("gimmicks")
    ctx = {
        "task_by_id": {t.id: t for t in tasks},
        "task_groups": group_by_category(tasks),
        "gimmick_by_id": {t.id: t for t in gimmicks},
        "gimmick_groups": group_by_category(gimmicks),
        "players": players,
        "rounds": rounds,
        "open_round": open_round,
        "totals": totals,
        "bonus": bonus,
        "bonus_notes": bonus_notes,
        "cells": cells,
        "ranked": ranked,
        "rank_of": {p.id: rank for rank, p, _ in ranked},
        "next_round_number": next_round_number(),
    }
    ctx["round_history"] = round_summaries(ctx)
    return ctx


def round_summaries(ctx):
    """Finished rounds as plain dicts (task, category, results): the shape saved in sessions too."""
    players = {p.id: p for p in ctx["players"]}
    summaries = []
    for rnd in ctx["rounds"]:
        if rnd.gimmick:
            task = ctx["gimmick_by_id"].get(rnd.gimmick_task_id)
            category = "gimmick"
        else:
            task = ctx["task_by_id"].get(rnd.task_id)
            category = task.category if task else None
        results = [
            {"player_id": pid, "player": players[pid].name, "color": players[pid].color,
             "place": score.place, "points": score.points}
            for (pid, rid), score in ctx["cells"].items()
            if rid == rnd.id and pid in players
        ]
        results.sort(key=lambda r: (-r["points"], r["place"] or 999, r["player"].lower()))
        summaries.append({
            "number": rnd.number,
            "label": rnd.label,
            "gimmick": rnd.gimmick,
            "category": category,
            "task": task.text if task else None,
            "rule": task.rule if task else "",
            "results": results,
        })
    return summaries


def session_snapshot(name):
    ctx = board_context()
    return {
        "version": 1,
        "name": name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "game_title": current_app.config["GAME_TITLE"],
        "players": [
            {"id": p.id, "name": p.name, "color": p.color, "rank": rank,
             "total": total, "bonus": ctx["bonus"][p.id]}
            for rank, p, total in ctx["ranked"]
        ],
        "rounds": ctx["round_history"],
    }


def leaderboard_context():
    ctx = board_context()
    last_round = ctx["rounds"][-1] if ctx["rounds"] else None
    last_scores = {}
    if last_round:
        last_scores = {pid: s for (pid, rid), s in ctx["cells"].items() if rid == last_round.id}

    open_round = ctx["open_round"]
    fingerprint = json.dumps([
        [[p.id, p.name, p.color, total] for _, p, total in ctx["ranked"]],
        [[r.id, r.label] for r in ctx["rounds"]],
        [open_round.id, open_round.task_id, open_round.gimmick, open_round.gimmick_task_id]
        if open_round else None,
        tasks_enabled(),
    ])
    ctx.update(
        last_round=last_round,
        last_scores=last_scores,
        version=hashlib.md5(fingerprint.encode()).hexdigest()[:12],
    )
    return ctx


def htmx_response(body="", status=200, toast=None, kind="success", confetti=False):
    response = Response(body, status=status)
    triggers = {}
    if toast:
        triggers["toast"] = {"message": toast, "kind": kind}
    if confetti:
        triggers["confetti"] = True
    if triggers:
        response.headers["HX-Trigger"] = json.dumps(triggers)
    return response


def board_response(**kwargs):
    """Re-render the whole host board (tiles, round panel, score sheet)."""
    return htmx_response(render_template("partials/board.html", **board_context()), **kwargs)


def score_update_response(**kwargs):
    """Refresh tiles and totals out-of-band without disturbing the score sheet inputs."""
    return htmx_response(render_template("partials/score_update.html", **board_context()), **kwargs)


def form_int(name, default=None):
    value = request.form.get(name, "").strip()
    try:
        return int(value)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register_routes(app):
    @app.get("/")
    def host():
        git_branch, git_commit = git_info(app.root_path)
        return render_template(
            "host.html", git_branch=git_branch, git_commit=git_commit,
            session_names=[s["name"] for s in list_sessions(app.config["SESSIONS_DIR"])],
            today=f"{datetime.now():%b} {datetime.now().day}, {datetime.now().year}",
            **leaderboard_context(),
        )

    @app.get("/scoreboard")
    def scoreboard():
        return render_template("scoreboard.html", **leaderboard_context())

    @app.get("/partials/board")
    def board_partial():
        return board_response()

    @app.get("/partials/leaderboard")
    def leaderboard_partial():
        ctx = leaderboard_context()
        if request.args.get("v") == ctx["version"]:
            return htmx_response(status=204)  # nothing changed: HTMX skips the swap
        return render_template("partials/leaderboard.html", **ctx)

    # --- Players -----------------------------------------------------------

    @app.post("/players")
    def add_players():
        names = [n.strip()[:80] for n in re.split(r"[,\n]", request.form.get("names", "")) if n.strip()]
        if not names:
            return board_response(toast="Type a name first", kind="warning")

        last_order = db.session.query(func.max(Player.sort_order)).scalar() or 0
        existing = Player.query.count()
        for offset, name in enumerate(names):
            db.session.add(Player(
                name=name,
                color=PALETTE[(existing + offset) % len(PALETTE)],
                sort_order=last_order + offset + 1,
            ))
        db.session.commit()
        message = f"Added {names[0]}" if len(names) == 1 else f"Added {len(names)} players"
        return board_response(toast=message)

    @app.patch("/players/<int:player_id>")
    def update_player(player_id):
        player = db.get_or_404(Player, player_id)
        name = request.form.get("name", "").strip()
        color = request.form.get("color", "").strip()
        if name:
            player.name = name[:80]
        if HEX_COLOR.match(color):
            player.color = color
        db.session.commit()
        return board_response()

    @app.delete("/players/<int:player_id>")
    def delete_player(player_id):
        player = db.get_or_404(Player, player_id)
        name = player.name
        db.session.delete(player)
        db.session.commit()
        return board_response(toast=f"Removed {name}", kind="info")

    @app.post("/players/<int:player_id>/adjust")
    def adjust_player(player_id):
        player = db.get_or_404(Player, player_id)
        amount = form_int("amount", 0)
        note = request.form.get("note", "").strip()[:120] or None
        if not amount:
            return score_update_response(toast="Enter a non-zero amount", kind="warning")

        db.session.add(Score(player_id=player.id, points=amount, note=note))
        db.session.commit()
        # Quick +1/-1 taps stay silent; custom adjustments get a confirmation.
        toast = f"{amount:+d} for {player.name}" if abs(amount) != 1 or note else None
        return score_update_response(toast=toast)

    @app.patch("/players/<int:player_id>/bonus")
    def set_bonus(player_id):
        player = db.get_or_404(Player, player_id)
        target = form_int("bonus")
        if target is None:
            return score_update_response(toast="Bonus must be a whole number", kind="warning")

        current = sum(s.points for s in player.scores if s.round_id is None)
        if target != current:
            db.session.add(Score(player_id=player.id, points=target - current, note="Manual edit"))
            db.session.commit()
        return score_update_response()

    # --- Rounds ------------------------------------------------------------

    @app.post("/rounds")
    def start_round():
        if Round.query.filter_by(status="open").first():
            return board_response(toast="Finish the current round first", kind="warning")
        player_count = Player.query.count()
        if not player_count:
            return board_response(toast="Add some players first", kind="warning")

        rnd = Round(number=next_round_number(), max_points=player_count - 1, status="open")
        if tasks_enabled():
            roll_task(rnd, "main")
            roll_task(rnd, "backup")
        db.session.add(rnd)
        db.session.commit()
        return board_response()

    @app.post("/rounds/<int:round_id>/task")
    def set_task(round_id):
        """Reroll a slot, or set it to a specific task when task_id is given."""
        rnd = db.get_or_404(Round, round_id)
        slot = request.form.get("slot", "main")
        if slot not in SLOT_FIELDS:
            abort(400)
        kind = "gimmicks" if slot == "gimmick" else "tasks"
        task_id = form_int("task_id")
        if task_id is None:
            if not roll_task(rnd, slot):
                return board_response(toast=f"Nothing else to roll. Add more {kind} with the Tasks button", kind="warning")
        elif task_id in {t.id for t in task_list(kind)}:
            other = {"main": rnd.backup_task_id, "backup": rnd.task_id}.get(slot)
            if task_id == other:  # picking the other slot's task swaps them
                rnd.task_id, rnd.backup_task_id = rnd.backup_task_id, rnd.task_id
            else:
                setattr(rnd, SLOT_FIELDS[slot], task_id)
        if slot != "backup":
            rnd.gimmick = slot == "gimmick"
        db.session.commit()
        return board_response()

    @app.post("/rounds/<int:round_id>/swap")
    def swap_tasks(round_id):
        rnd = db.get_or_404(Round, round_id)
        rnd.task_id, rnd.backup_task_id = rnd.backup_task_id, rnd.task_id
        rnd.gimmick = False
        db.session.commit()
        return board_response(toast="Backup task is now the main task", kind="info")

    @app.post("/rounds/<int:round_id>/gimmick")
    def toggle_gimmick(round_id):
        rnd = db.get_or_404(Round, round_id)
        rnd.gimmick = not rnd.gimmick
        if rnd.gimmick and rnd.gimmick_task_id is None:  # keep an earlier roll if switching back
            roll_task(rnd, "gimmick")
        db.session.commit()
        return board_response(toast="Gimmick round!" if rnd.gimmick else "Back to the rolled task", kind="info")

    @app.post("/rounds/<int:round_id>/confirm")
    def confirm_round(round_id):
        rnd = db.get_or_404(Round, round_id)
        if rnd.status != "open":
            return board_response(toast="That round is already finished", kind="warning")

        try:
            raw_order = json.loads(request.form.get("order", "[]"))
        except ValueError:
            abort(400)
        player_ids = [p.id for p in Player.query.order_by(Player.sort_order, Player.id).all()]
        order, seen = [], set()
        for pick in raw_order:
            pid = int(pick.get("id", 0))
            if pid in player_ids and pid not in seen:
                order.append((pid, bool(pick.get("tie"))))
                seen.add(pid)
        if not order:
            return board_response(toast="Click players in finishing order first", kind="warning")

        # Unclicked players are tied for last, so they get 0.
        places = places_for_round(order, player_ids)
        bottom = last_place([place for _, place in places])
        for pid, place in places:
            db.session.add(Score(
                player_id=pid, round_id=rnd.id, place=place,
                points=points_for_place(place, bottom),
            ))
        rnd.max_points = points_for_place(1, bottom)  # what 1st place earned, for reference
        rnd.status = "done"
        db.session.commit()
        return board_response(toast=f"{rnd.label} saved!", confetti=True)

    @app.patch("/rounds/<int:round_id>")
    def update_round(round_id):
        rnd = db.get_or_404(Round, round_id)
        if "title" in request.form:
            rnd.title = request.form["title"].strip()[:80] or None
        db.session.commit()
        return htmx_response(status=204, toast="Saved", kind="info")

    @app.post("/rounds/<int:round_id>/recalc")
    def recalc_round(round_id):
        rnd = db.get_or_404(Round, round_id)
        bottom = last_place([score.place for score in rnd.scores])
        for score in rnd.scores:
            score.points = points_for_place(score.place if score.place else bottom, bottom)
        rnd.max_points = points_for_place(1, bottom)
        db.session.commit()
        return board_response(toast=f"{rnd.label} recalculated")

    @app.delete("/rounds/<int:round_id>")
    def delete_round(round_id):
        rnd = db.get_or_404(Round, round_id)
        was_open = rnd.status == "open"
        label = rnd.label
        db.session.delete(rnd)
        db.session.flush()
        for number, remaining in enumerate(Round.query.order_by(Round.number).all(), start=1):
            remaining.number = number
        db.session.commit()
        return board_response(toast="Round cancelled" if was_open else f"Deleted {label}", kind="info")

    # --- Task lists (tasks.csv / gimmicks.csv) ------------------------------

    def task_manager_response(list_kind, **kwargs):
        body = render_template(
            "partials/task_manager.html",
            list_kind=list_kind,
            groups=group_by_category(task_list(list_kind)),
            counts={k: len(task_list(k)) for k in KINDS},
            categories=sorted({t.category for t in task_list("tasks")}),
        )
        return htmx_response(body, **kwargs)

    def check_kind(kind):
        if kind not in KINDS:
            abort(404)

    def task_from_form(kind, task_id):
        """Build a Task from the add/edit form, or return an error message."""
        text_value = request.form.get("text", "").strip()
        if not text_value:
            return None, "The task needs some text"
        category = KINDS[kind]["category"] or request.form.get("category", "").strip().lower()
        if not category:
            return None, "Give the task a category"
        rule = request.form.get("rule", "").strip() if "rule" in KINDS[kind]["fields"] else ""
        return Task(task_id, category, text_value, rule), None

    def save_list(kind, tasks, toast):
        try:
            save_tasks(current_app.config[KINDS[kind]["config"]], tasks, KINDS[kind]["fields"])
        except OSError:
            return task_manager_response(
                kind, toast=f"Couldn't save {kind}.csv. Is it open in another program?", kind="error",
            )
        return task_manager_response(kind, toast=toast)

    @app.get("/partials/tasks")
    def task_manager():
        kind = request.args.get("kind", "tasks")
        check_kind(kind)
        return task_manager_response(kind)

    @app.post("/tasks/<kind>")
    def add_task(kind):
        check_kind(kind)
        tasks = list(task_list(kind))
        task, error = task_from_form(kind, next_task_id(tasks))
        if error:
            return task_manager_response(kind, toast=error, kind="warning")
        return save_list(kind, tasks + [task], "Added")

    @app.patch("/tasks/<kind>/<int:task_id>")
    def edit_task(kind, task_id):
        check_kind(kind)
        task, error = task_from_form(kind, task_id)
        if error:
            return task_manager_response(kind, toast=error, kind="warning")
        tasks = [task if t.id == task_id else t for t in task_list(kind)]
        return save_list(kind, tasks, "Saved")

    @app.delete("/tasks/<kind>/<int:task_id>")
    def delete_task(kind, task_id):
        check_kind(kind)
        tasks = [t for t in task_list(kind) if t.id != task_id]
        return save_list(kind, tasks, "Deleted")

    # --- Scores ------------------------------------------------------------

    @app.patch("/scores/<int:round_id>/<int:player_id>")
    def set_score(round_id, player_id):
        db.get_or_404(Round, round_id)
        db.get_or_404(Player, player_id)
        points = form_int("points")
        if points is None:
            return score_update_response(toast="Points must be a whole number", kind="warning")

        score = Score.query.filter_by(round_id=round_id, player_id=player_id).first()
        if score is None:
            score = Score(round_id=round_id, player_id=player_id)
            db.session.add(score)
        score.points = points
        db.session.commit()
        return score_update_response()

    # --- Game --------------------------------------------------------------

    @app.post("/settings/tasks")
    def toggle_tasks():
        enabled = bool(request.form.get("enabled"))
        setting = db.session.get(Setting, "tasks_enabled") or Setting(key="tasks_enabled")
        setting.value = "1" if enabled else "0"
        db.session.add(setting)
        open_round = Round.query.filter_by(status="open").first()
        if enabled and open_round and open_round.task_id is None:  # round started with tasks off
            roll_task(open_round, "main")
            roll_task(open_round, "backup")
        db.session.commit()
        return board_response(toast="Tasks on" if enabled else "Tasks off: just rounds and points", kind="info")

    @app.get("/export.csv")
    def export_csv():
        ctx = board_context()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Rank", "Player"] + [r.label for r in ctx["rounds"]] + ["Bonus", "Total"])
        for rank, player, total in ctx["ranked"]:
            round_points = [
                ctx["cells"][(player.id, r.id)].points if (player.id, r.id) in ctx["cells"] else 0
                for r in ctx["rounds"]
            ]
            writer.writerow([rank, player.name] + round_points + [ctx["bonus"][player.id], total])
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=gameshow-scores.csv"},
        )

    @app.post("/reset")
    def reset():
        mode = request.form.get("mode", "scores")
        Score.query.delete()
        Round.query.delete()
        if mode == "all":
            Player.query.delete()
        db.session.commit()
        message = "New game started" if mode == "all" else "Scores cleared, players kept"
        return board_response(toast=message, kind="info")

    # --- Sessions ----------------------------------------------------------

    @app.post("/sessions")
    def save_current_session():
        name = request.form.get("name", "").strip()[:80]
        if not name:
            return board_response(toast="Give the session a name", kind="warning")
        if not Player.query.count():
            return board_response(toast="Nothing to save yet. Add players first", kind="warning")
        if Round.query.filter_by(status="open").first():
            return board_response(toast="Confirm or cancel the open round before saving", kind="warning")

        try:
            _, replaced = save_session(app.config["SESSIONS_DIR"], session_snapshot(name))
        except OSError:
            return board_response(toast="Couldn't write to the sessions folder", kind="error")
        if request.form.get("clear_after"):
            Score.query.delete()
            Round.query.delete()
            db.session.commit()
        verb = "Updated" if replaced else "Saved"
        return board_response(toast=f"{verb} session “{name}”")

    @app.get("/sessions")
    def sessions_page():
        return render_template("sessions.html", sessions=list_sessions(app.config["SESSIONS_DIR"]))

    @app.get("/sessions/<slug>")
    def session_page(slug):
        try:
            session = load_session(app.config["SESSIONS_DIR"], slug)
        except (OSError, ValueError):
            session = None
        if session is None:
            abort(404)
        cells = {
            (result["player_id"], index): result["points"]
            for index, rnd in enumerate(session.get("rounds", []))
            for result in rnd.get("results", [])
        }
        return render_template("session_detail.html", session=session, slug=slug, cells=cells)

    @app.delete("/sessions/<slug>")
    def remove_session(slug):
        if not delete_session(app.config["SESSIONS_DIR"], slug):
            abort(404)
        return htmx_response(toast="Session deleted", kind="info")


if __name__ == "__main__":
    create_app().run(debug=True)
