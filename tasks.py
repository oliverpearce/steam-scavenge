"""Round tasks and gimmicks, stored as CSV files you can edit by hand or in the app.

tasks.csv:    id, category, text
gimmicks.csv: id, text, rule

Files are re-read whenever they change, so hand edits show up without a restart.
"""

import csv
import os
import random
from collections import namedtuple

Task = namedtuple("Task", "id category text rule", defaults=("",))

# Per list: the app config key for its file, the CSV columns, and the category rows get.
KINDS = {
    "tasks": {"config": "TASKS_FILE", "fields": ["id", "category", "text"], "category": None},
    "gimmicks": {"config": "GIMMICKS_FILE", "fields": ["id", "text", "rule"], "category": "gimmick"},
}

# Badge colours per category; anything not listed gets the fallback.
CATEGORY_COLORS = {
    "speed": "#f87171",
    "find": "#34d399",
    "most": "#60a5fa",
    "judged": "#c084fc",
    "weird": "#f472b6",
    "closest": "#fbbf24",
    "survive": "#2dd4bf",
    "action": "#fb923c",
    "death": "#e11d48",
    "gimmick": "#fbbf24",
}
FALLBACK_COLOR = "#94a3b8"

_cache = {}  # path -> (mtime, tasks)


def category_color(category):
    return CATEGORY_COLORS.get(category, FALLBACK_COLOR)


def load_tasks(path, category=None):
    """Read a task file. `category` overrides the column (gimmicks have no category column)."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    cached = _cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]

    with open(path, newline="", encoding="utf-8-sig") as f:
        tasks = [
            Task(
                int(row["id"]),
                category or (row.get("category") or "").strip().lower(),
                row["text"].strip(),
                (row.get("rule") or "").strip(),
            )
            for row in csv.DictReader(f)
            if (row.get("id") or "").strip().isdigit() and (row.get("text") or "").strip()
        ]
    _cache[path] = (mtime, tasks)
    return tasks


def save_tasks(path, tasks, fields):
    """Write tasks back to CSV (via a temp file so a failed write can't corrupt the original)."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        f.write(",".join(fields) + "\n")
        writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC, lineterminator="\n")
        for task in tasks:
            writer.writerow([getattr(task, field) for field in fields])
    os.replace(tmp_path, path)
    _cache.pop(path, None)


def next_task_id(tasks):
    return max((t.id for t in tasks), default=0) + 1


def group_by_category(tasks):
    """[(category, [tasks...]), ...] in the order categories first appear in the file."""
    groups = {}
    for task in tasks:
        groups.setdefault(task.category, []).append(task)
    return list(groups.items())


def pick_task(tasks, avoid=(), never=()):
    """A random task, preferring ones not in `avoid` (already played) and never one in `never`."""
    pool = [t for t in tasks if t.id not in never]
    fresh = [t for t in pool if t.id not in avoid]
    choices = fresh or pool
    return random.choice(choices) if choices else None
