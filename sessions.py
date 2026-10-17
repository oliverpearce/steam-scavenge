"""Saved sessions: one JSON snapshot per game night, stored in the sessions/ folder.

A snapshot is plain data (names, totals, rounds with their task and results), so it
stays readable even after players, tasks or the database change.
"""

import json
import os
import re

SLUG_PATTERN = re.compile(r"^[a-z0-9-]{1,60}$")


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60].strip("-")
    return slug or "session"


def session_path(folder, slug):
    if not SLUG_PATTERN.match(slug):
        return None
    return os.path.join(folder, slug + ".json")


def save_session(folder, snapshot):
    """Write the snapshot under a file named after it. Returns (slug, replaced_existing)."""
    os.makedirs(folder, exist_ok=True)
    slug = slugify(snapshot["name"])
    path = session_path(folder, slug)
    replaced = os.path.exists(path)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)
    return slug, replaced


def load_session(folder, slug):
    path = session_path(folder, slug)
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def delete_session(folder, slug):
    path = session_path(folder, slug)
    if path and os.path.exists(path):
        os.remove(path)
        return True
    return False


def list_sessions(folder):
    """Summaries of every saved session, newest first. Unreadable files are skipped."""
    if not os.path.isdir(folder):
        return []
    sessions = []
    for filename in os.listdir(folder):
        slug, ext = os.path.splitext(filename)
        if ext != ".json" or not SLUG_PATTERN.match(slug):
            continue
        try:
            data = load_session(folder, slug)
        except (OSError, ValueError):
            continue
        players = data.get("players", [])
        sessions.append({
            "slug": slug,
            "name": data.get("name", slug),
            "saved_at": data.get("saved_at", ""),
            "players": players,
            "round_count": len(data.get("rounds", [])),
            "winners": [p["name"] for p in players if p.get("rank") == 1],
        })
    return sorted(sessions, key=lambda s: s["saved_at"], reverse=True)
