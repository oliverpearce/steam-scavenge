"""Database models. A player's total is always the sum of their Score rows."""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Bright colours that stay readable on a dark background; new players cycle through them.
PALETTE = [
    "#f472b6", "#60a5fa", "#34d399", "#fbbf24", "#a78bfa", "#f87171",
    "#22d3ee", "#fb923c", "#a3e635", "#e879f9", "#2dd4bf", "#facc15",
]


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    color = db.Column(db.String(7), nullable=False, default=PALETTE[0])
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    scores = db.relationship("Score", backref="player", cascade="all, delete-orphan")


class Round(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(80))
    max_points = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="open")  # "open" or "done"
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    scores = db.relationship("Score", backref="round", cascade="all, delete-orphan")

    @property
    def label(self):
        return self.title or f"Round {self.number}"


class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    # Null round_id means a manual bonus/penalty rather than a round result.
    round_id = db.Column(db.Integer, db.ForeignKey("round.id"))
    place = db.Column(db.Integer)
    points = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
