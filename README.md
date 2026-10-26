# steam-scavenge

A Python Flask points tracker for running a game show. It rolls random tasks for each round, scores players by finishing order, shows a live scoreboard, and saves each session.

[Rules!!!!](https://docs.google.com/presentation/d/1u3qphJGUw1EZpYNN_z6_ACk6JLpGf2zYq8NUKR6RNqc/edit?usp=sharing)

## Running it

You need **Python 3.9+**.

**Git Bash**

```bash
py -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
flask --app app run --debug
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run --debug
```

Then open **http://127.0.0.1:5000**. After the first setup, you only need to activate the venv and run the last line.

| Command | What it does |
|---|---|
| `flask --app app run --debug` | Start the app |
| `flask --app app run --port 5001` | Start on a different port |
| `pytest` | Run the tests |
| `deactivate` | Leave the venv |

## Playing without tasks

Tasks start **off**, so you just play rounds and points. Flip the **Tasks** switch (top right) to turn them on. While it's off, no tasks are rolled, and none are shown on the host page, the scoreboard or past rounds. If you turn it back on mid-round, the open round gets a task.

## File structure

```
points-tracker/
├── app.py                  Flask app and routes
├── models.py               Database tables (players, rounds, scores)
├── scoring.py              Points rules: places → points, totals → ranks
├── tasks.py                Loads, saves and picks tasks
├── sessions.py             Saves and loads session files
├── tasks.csv               Task bank (id, category, text)
├── gimmicks.csv            Gimmick bank (id, text, rule)
├── requirements.txt
├── templates/
│   ├── base.html           Shared layout and CDN libraries
│   ├── host.html           Main host page
│   ├── scoreboard.html     Standalone scoreboard
│   ├── sessions.html       Saved sessions list
│   ├── session_detail.html One saved session
│   └── partials/           HTMX fragments (tiles, round panel, history, …)
├── static/
│   ├── app.js              Round placement, toasts, confetti
│   └── app.css             Midnight theme styles
├── tests/                  pytest suite
├── instance/gameshow.db    Current game (created on first run, git-ignored)
└── sessions/               Saved sessions as JSON (created on first save, git-ignored)
```
