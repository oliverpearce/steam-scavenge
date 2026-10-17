# Gameshow Points Tracker

A dark-themed Flask app for keeping score at a gameshow. Add players as tiles, click them in finishing order each round, and points are awarded automatically: 1st place gets the max, and each place after gets one fewer. Every name and number can still be edited by hand, and a live scoreboard page is ready for a TV or projector.

<!-- Screenshot: add one here, e.g. ![Host view](docs/host.png) -->

## Features

- **Quick player entry**: type a name and press Enter, or paste a whole list (commas or new lines).
- **Tile-based rounds**: start a round, then click tiles in finishing order. 🥇 🥈 🥉 badges show a live points preview.
- **Automatic points**: 1st gets the max (default = number of players), then −1 per place, never below 0. Ties share a place, and the next place skips ahead (1, 2, 2, 4).
- **Manual control**: rename players (double-click the name), change colours, use +1 / −1 and custom ± adjustments with notes, edit any cell on the score sheet, edit round titles and max points, and recalculate a round.
- **Live scoreboard popup**: click **Scoreboard** on the host page to open the standings over the page. It refreshes every 2 seconds and has a full-screen button for showing it on a TV. A standalone version is also at `/scoreboard` if you'd rather use a second screen.
- **CSV export** and **reset** (clear scores only, or start a whole new game).
- Data is saved in SQLite (`instance/gameshow.db`), so it survives restarts.

**Stack:** Flask 3 · Flask-SQLAlchemy · HTMX 2 · Alpine.js 3 · Tailwind CSS + daisyUI 4 (`night` theme) · Lucide icons · canvas-confetti · animate.css. The front-end libraries load from CDNs, so there's no Node or build step. The browser needs internet access the first time it loads the page.

---

## Prerequisites

- **Python 3.9 or newer.** Check with:
  ```powershell
  py --version        # Windows (Python launcher)
  python3 --version   # macOS / Linux
  ```
  If you don't have it, download it from <https://www.python.org/downloads/>. On Windows, tick **"Add python.exe to PATH"** in the installer.

## Setup (one time)

All commands run from the project folder (`points-tracker`). Everything installs into a local virtual environment in `.venv/`, so nothing is installed globally.

### Windows (PowerShell)

```powershell
cd path\to\points-tracker
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> **"running scripts is disabled on this system"?** Run this once, then try activating again:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### Windows (Command Prompt)

```bat
cd path\to\points-tracker
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS / Linux

```bash
cd path/to/points-tracker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Once the venv is active, your prompt starts with `(.venv)`.

## Running the app

Activate the venv first if it isn't already. Use `.\.venv\Scripts\Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux. Then run:

```powershell
flask --app app run --debug
```

or equivalently:

```powershell
python app.py
```

Then open:

| Page | URL | Use |
|---|---|---|
| Host control panel | <http://127.0.0.1:5000> | You, running the show. Click **Scoreboard** for the popup leaderboard, and **⤢** inside it for full screen. Press **Esc** to close it. |
| Standalone scoreboard (optional) | <http://127.0.0.1:5000/scoreboard> | Only needed for a separate screen or device |

Stop the server with **Ctrl+C**.

### Showing the scoreboard on another device (same Wi-Fi)

```powershell
flask --app app run --host 0.0.0.0
```

Find your computer's local IP address (`ipconfig` on Windows, `ipconfig getifaddr en0` on macOS). On the other device, open `http://<that-ip>:5000/scoreboard`. Windows may ask you to allow Python through the firewall. Allow it on **private** networks.

### Custom game title

Set `GAMESHOW_TITLE` before starting the server:

```powershell
$env:GAMESHOW_TITLE = "Friday Night Quiz"   # PowerShell
flask --app app run --debug
```

```bash
GAMESHOW_TITLE="Friday Night Quiz" flask --app app run --debug   # macOS / Linux
```

## Running the tests

With the venv active:

```powershell
pytest
```

## How to use it

1. **Add players.** Type a name in the top box and press **Enter**. To add several at once, paste a list like `Alice, Bob, Cara`. Press **Shift+Enter** for a new line.
2. **Start a round.** Click **Start round**. The panel shows how many points 1st place gets. It defaults to the number of players, and you can change it for this round.
3. **Place players.** Click tiles in the order the players finished. Click a placed tile again to unplace it, or use **Undo**.
   - **Ties:** click **Tie with previous**, then click the tied player. They get the same place and points as the player before them.
   - Anyone you don't click gets 0 for the round.
4. **Confirm round.** Points are saved, totals update, and confetti fires. Click **Scoreboard** to show the audience the standings in a popup.
5. **Fix things by hand at any time:**
   - **Rename:** double-click a player's name, or use **⋯ → Rename**. **⋯** also lets you change their colour or remove them.
   - **Quick points:** use **− / +** on a tile, or **± pts** for a custom amount with an optional note (e.g. "bonus question").
   - **Score sheet:** click any number to edit it. This includes round results and the **Bonus** column. Changes save when you leave the box or press Enter.
   - **Rounds:** edit a round's title or max points in the column header. Click **↻** to recalculate that round's points from finishing places, or **🗑** to delete the round.
6. **Export / reset.** Open the **⋮** menu (top right) and choose **Export CSV**, or **Reset…**. Reset can clear only the scores (keeping players) or start a new game.

## Resetting data

- In the app, use **⋮ → Reset…**.
- Or stop the server and delete `instance/gameshow.db`. A fresh database is created on the next start.

## Leaving the virtual environment

```powershell
deactivate
```

Next time, just activate the venv again and run the app. You don't need to reinstall.

## Troubleshooting

| Problem | Fix |
|---|---|
| `flask` / `pytest` not recognized, or `No module named flask` | The venv isn't active. Activate it (see above), or run the venv's copy directly: `.\.venv\Scripts\flask.exe --app app run --debug` |
| `No module named venv` | Your `python` command points at a stripped-down Python. On Windows, use the launcher: `py -m venv .venv` |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `Address already in use` / port 5000 busy | Use another port: `flask --app app run --debug --port 5001` |
| Page looks unstyled or buttons do nothing | The browser couldn't reach the CDNs. Check your internet connection and refresh. |
| Scoreboard not updating on another device | Start with `--host 0.0.0.0`, use the host computer's IP address, and allow Python through the firewall |

## Project layout

```
app.py              Flask app factory and all routes
models.py           Player / Round / Score tables (SQLite via Flask-SQLAlchemy)
scoring.py          Pure functions: places -> points, totals -> ranks
templates/          Jinja pages (host, scoreboard) and HTMX partials
static/app.js       Alpine round-placement store, toasts, confetti
static/app.css      Dark-theme styling for tiles and the scoreboard
tests/              pytest suite
```
