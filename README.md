# steam-scavenge

A web app and poitns tracker for running a steam library game show. It rolls random tasks for each round, scores players by finishing order, shows a live scoreboard, and saves each session.

[Rules!!!!](https://docs.google.com/presentation/d/1u3qphJGUw1EZpYNN_z6_ACk6JLpGf2zYq8NUKR6RNqc/edit?usp=sharing)

idea stolen from petrichor and cjya, was just to make it easier to host for frens :)

NOTE: THE WEB VERSION IS DIFFERENT, BUT SHOULD WORK BETTER! THE FLASK APP IS OUTDATED LOL

## Running the Flask app (if you want to idk)

You just need a venv and **Python 3.9+**.

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
| `deactivate` | Leave the venv |
