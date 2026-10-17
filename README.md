# steam scavenge

A Flask points tracker for running a gameshow. It rolls random tasks for each round, scores players by finishing order, shows a live scoreboard, and saves each session.

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
