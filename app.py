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
from collections import defaultdict

from flask import Flask, Response, abort, render_template, request
from sqlalchemy import func

from models import PALETTE, Player, Round, Score, db
from scoring import places_from_order, points_for_place, rank_totals

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def initials(name):
    return "".join(part[0] for part in name.split()[:2]).upper() or "?"


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI="sqlite:///gameshow.db",  # stored in ./instance/
        GAME_TITLE=os.environ.get("GAMESHOW_TITLE", "Gameshow Points"),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    with app.app_context():
        db.create_all()

    app.add_template_filter(ordinal)
    app.add_template_filter(initials)
    app.context_processor(lambda: {"palette": PALETTE})
    register_routes(app)
    return app


# ---------------------------------------------------------------------------
# View-model helpers
# ---------------------------------------------------------------------------

def next_round_number():
    return (db.session.query(func.max(Round.number)).scalar() or 0) + 1


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
    return {
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


def leaderboard_context():
    ctx = board_context()
    last_round = ctx["rounds"][-1] if ctx["rounds"] else None
    last_scores = {}
    if last_round:
        last_scores = {pid: s for (pid, rid), s in ctx["cells"].items() if rid == last_round.id}

    fingerprint = json.dumps([
        [[p.id, p.name, p.color, total] for _, p, total in ctx["ranked"]],
        [[r.id, r.label] for r in ctx["rounds"]],
        ctx["open_round"].id if ctx["open_round"] else None,
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
        return render_template("host.html", **leaderboard_context())

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

        db.session.add(Round(number=next_round_number(), max_points=player_count, status="open"))
        db.session.commit()
        return board_response()

    @app.post("/rounds/<int:round_id>/confirm")
    def confirm_round(round_id):
        rnd = db.get_or_404(Round, round_id)
        if rnd.status != "open":
            return board_response(toast="That round is already finished", kind="warning")

        max_points = form_int("max_points")
        if max_points is not None:
            rnd.max_points = max(max_points, 0)

        try:
            raw_order = json.loads(request.form.get("order", "[]"))
        except ValueError:
            abort(400)
        player_ids = {p.id for p in Player.query.all()}
        order, seen = [], set()
        for pick in raw_order:
            pid = int(pick.get("id", 0))
            if pid in player_ids and pid not in seen:
                order.append((pid, bool(pick.get("tie"))))
                seen.add(pid)
        if not order:
            return board_response(toast="Click players in finishing order first", kind="warning")

        for pid, place in places_from_order(order):
            db.session.add(Score(
                player_id=pid, round_id=rnd.id, place=place,
                points=points_for_place(place, rnd.max_points),
            ))
        for pid in player_ids - seen:  # unplaced players get an explicit 0 for the sheet
            db.session.add(Score(player_id=pid, round_id=rnd.id, points=0))
        rnd.status = "done"
        db.session.commit()
        return board_response(toast=f"{rnd.label} saved!", confetti=True)

    @app.patch("/rounds/<int:round_id>")
    def update_round(round_id):
        rnd = db.get_or_404(Round, round_id)
        toast = "Saved"
        if "title" in request.form:
            rnd.title = request.form["title"].strip()[:80] or None
        max_points = form_int("max_points")
        if max_points is not None and max_points != rnd.max_points:
            rnd.max_points = max(max_points, 0)
            toast = f"Max set to {rnd.max_points}. Click ↻ to recalculate this round's points"
        db.session.commit()
        return htmx_response(status=204, toast=toast, kind="info")

    @app.post("/rounds/<int:round_id>/recalc")
    def recalc_round(round_id):
        rnd = db.get_or_404(Round, round_id)
        for score in rnd.scores:
            score.points = points_for_place(score.place, rnd.max_points)
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


if __name__ == "__main__":
    create_app().run(debug=True)
