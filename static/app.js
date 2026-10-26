// steam scavenge: a static gameshow points tracker. No server: the current game lives in
// this browser's localStorage, and saving a session writes a JSON file you can open later.

const GAME_TITLE = "steam scavenge";
const GAME_KEY = "steam-scavenge:game";
const BANKS_KEY = "steam-scavenge:banks"; // only set once the task bank has been edited

// Bright colours that stay readable on a dark background; new players cycle through them.
const PALETTE = [
  "#f472b6", "#60a5fa", "#34d399", "#fbbf24", "#a78bfa", "#f87171",
  "#22d3ee", "#fb923c", "#a3e635", "#e879f9", "#2dd4bf", "#facc15",
];

// Badge colours per category; anything not listed gets the fallback.
const CATEGORY_COLORS = {
  speed: "#f87171",
  find: "#34d399",
  most: "#60a5fa",
  judged: "#c084fc",
  weird: "#f472b6",
  closest: "#fbbf24",
  survive: "#2dd4bf",
  action: "#fb923c",
  death: "#e11d48",
  gimmick: "#fbbf24",
};
const FALLBACK_COLOR = "#94a3b8";

/* Scoring ----------------------------------------------------------------- */

// Last place earns 0 and each place above it earns one more.
function pointsForPlace(place, last) {
  if (!place || place < 1) return 0;
  return Math.max(last - place, 0);
}

// Standard competition places ("1, 2, 2, 4") for a finishing order of { id, tie } picks.
function placesFromOrder(order) {
  let place = 0;
  return order.map((pick, i) => {
    if (!(pick.tie && i > 0)) place = i + 1;
    return { id: pick.id, place };
  });
}

// Places for everyone in a round: the clicked order, then anyone unclicked tied for last.
function placesForRound(order, playerIds) {
  const placed = placesFromOrder(order);
  const seen = new Set(placed.map((p) => p.id));
  const bottom = placed.length + 1;
  return placed.concat(playerIds.filter((id) => !seen.has(id)).map((id) => ({ id, place: bottom })));
}

// The bottom place in a round. A missing place counts as tied for last.
function lastPlace(places) {
  const known = places.filter((p) => p != null);
  if (known.length < places.length) return known.length + 1;
  return Math.max(0, ...known);
}

// Sort [item, total] pairs high to low with shared ranks: 10, 8, 8, 5 -> 1, 2, 2, 4.
function rankTotals(entries) {
  const ordered = [...entries].sort((a, b) => b[1] - a[1]);
  const ranked = [];
  ordered.forEach(([item, total], i) => {
    const prev = ranked[ranked.length - 1];
    ranked.push({ rank: prev && prev.total === total ? prev.rank : i + 1, item, total });
  });
  return ranked;
}

/* Formatting -------------------------------------------------------------- */

function ordinal(n) {
  const suffix = n % 100 >= 10 && n % 100 <= 20 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${suffix}`;
}

function initials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";
}

function signed(n) {
  return n > 0 ? `+${n}` : `${n}`;
}

function medal(place) {
  return { 1: "🥇", 2: "🥈", 3: "🥉" }[place] || `#${place}`;
}

function placeMarker(place) {
  return { 1: "🥇", 2: "🥈", 3: "🥉" }[place] || (place ? ordinal(place) : "–");
}

function dateLabel(d) {
  return `${d.toLocaleString("en-US", { month: "short" })} ${d.getDate()}, ${d.getFullYear()}`;
}

// "2026-10-17T19:42:05" -> "Oct 17, 2026 · 7:42 PM"
function niceDateTime(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value || "";
  return `${dateLabel(d)} · ${d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
}

// Local time as an ISO string without the timezone, e.g. "2026-10-17T19:42:05".
function isoNow() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
}

function slugify(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60).replace(/-+$/, "") || "session";
}

function categoryColor(category) {
  return CATEGORY_COLORS[category] || FALLBACK_COLOR;
}

function roundLabel(rnd) {
  return rnd.title || `Round ${rnd.number}`;
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/* Tasks ------------------------------------------------------------------- */

// [[category, [tasks...]], ...] in the order categories first appear.
function groupByCategory(tasks) {
  const groups = new Map();
  for (const task of tasks) {
    if (!groups.has(task.category)) groups.set(task.category, []);
    groups.get(task.category).push(task);
  }
  return [...groups];
}

// A random task, preferring ones not in `avoid` (already played) and never one in `never`.
function pickTask(tasks, avoid, never) {
  const pool = tasks.filter((t) => !never.has(t.id));
  const fresh = pool.filter((t) => !avoid.has(t.id));
  const choices = fresh.length ? fresh : pool;
  return choices.length ? choices[Math.floor(Math.random() * choices.length)] : null;
}

function nextTaskId(tasks) {
  return Math.max(0, ...tasks.map((t) => t.id)) + 1;
}

/* Storage ----------------------------------------------------------------- */

// Storage can be blocked (private windows, strict settings), so every access fails quietly.
function readJson(key) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? null : JSON.parse(value);
  } catch {
    return null;
  }
}

function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

function removeKey(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

function loadPref(key, fallback) {
  const value = readJson(key);
  return value === null ? fallback : value;
}

function savePref(key, value) {
  writeJson(key, value);
}

// Rounds are "open" or "done". Scores with roundId null are manual bonus/penalty points.
// A round's frozen task is the text it was played with, so later task edits don't rewrite history.
function emptyGame() {
  return { version: 2, nextId: 1, tasksEnabled: false, players: [], rounds: [], scores: [], picks: [] };
}

function loadGame() {
  return { ...emptyGame(), ...(readJson(GAME_KEY) || {}) };
}

function loadBanks() {
  const saved = readJson(BANKS_KEY);
  return {
    tasks: saved?.tasks || structuredClone(DEFAULT_TASKS),
    gimmicks: saved?.gimmicks || structuredClone(DEFAULT_GIMMICKS),
  };
}

/* Derived view ------------------------------------------------------------ */

function taskOf(rnd, taskById, gimmickById) {
  if (rnd.frozen) return rnd.frozen;
  const task = rnd.gimmick ? gimmickById.get(rnd.gimmickTaskId) : taskById.get(rnd.taskId);
  return task ? { category: task.category, text: task.text, rule: task.rule || "" } : null;
}

// Everything the pages show, worked out from the raw game and task banks.
function buildView(game, banks) {
  const taskById = new Map(banks.tasks.map((t) => [t.id, t]));
  const gimmickById = new Map(banks.gimmicks.map((t) => [t.id, t]));
  const players = game.players;
  const doneRounds = game.rounds.filter((r) => r.status === "done").sort((a, b) => a.number - b.number);
  const openRound = game.rounds.find((r) => r.status === "open") || null;

  const totals = {};
  const bonus = {};
  const bonusNotes = {};
  const cells = {}; // "playerId:roundId" -> score
  for (const p of players) {
    totals[p.id] = 0;
    bonus[p.id] = 0;
    bonusNotes[p.id] = [];
  }
  for (const s of game.scores) {
    if (!(s.playerId in totals)) continue;
    totals[s.playerId] += s.points;
    if (s.roundId == null) {
      bonus[s.playerId] += s.points;
      bonusNotes[s.playerId].push(`${signed(s.points)} ${s.note || ""}`.trim());
    } else {
      cells[`${s.playerId}:${s.roundId}`] = s;
    }
  }

  const ranked = rankTotals(players.map((p) => [p, totals[p.id]]));
  const rankOf = Object.fromEntries(ranked.map((r) => [r.item.id, r.rank]));
  const byId = Object.fromEntries(players.map((p) => [p.id, p]));

  // Finished rounds as plain data: the shape saved in session files too.
  const history = doneRounds.map((rnd) => {
    const task = taskOf(rnd, taskById, gimmickById);
    const results = Object.values(cells)
      .filter((s) => s.roundId === rnd.id)
      .map((s) => ({
        player_id: s.playerId, player: byId[s.playerId].name, color: byId[s.playerId].color,
        place: s.place, points: s.points,
      }))
      .sort((a, b) => b.points - a.points || (a.place || 999) - (b.place || 999) || a.player.localeCompare(b.player));
    return {
      number: rnd.number,
      label: roundLabel(rnd),
      gimmick: !!rnd.gimmick,
      category: rnd.gimmick ? "gimmick" : task?.category ?? null,
      task: task?.text ?? null,
      rule: task?.rule ?? "",
      results,
    };
  });

  const lastRound = doneRounds[doneRounds.length - 1] || null;
  return {
    taskById, gimmickById, players, doneRounds, openRound, totals, bonus, bonusNotes, cells,
    ranked, rankOf, history, lastRound,
    openTask: openRound ? taskById.get(openRound.taskId) || null : null,
    backupTask: openRound ? taskById.get(openRound.backupTaskId) || null : null,
    gimmickTask: openRound ? gimmickById.get(openRound.gimmickTaskId) || null : null,
  };
}

function sessionSnapshot(view, name) {
  return {
    version: 2,
    name,
    saved_at: isoNow(),
    game_title: GAME_TITLE,
    players: view.ranked.map(({ rank, item: p, total }) => ({
      id: p.id, name: p.name, color: p.color, rank, total, bonus: view.bonus[p.id],
    })),
    rounds: view.history,
  };
}

// Rebuild a playable game from a saved session file, so you can keep going where you left off.
function gameFromSnapshot(snapshot) {
  const game = emptyGame();
  const nid = () => game.nextId++;
  const idMap = new Map();
  for (const p of snapshot.players) {
    const id = nid();
    idMap.set(p.id, id);
    game.players.push({ id, name: p.name, color: p.color || PALETTE[game.players.length % PALETTE.length] });
  }
  (snapshot.rounds || []).forEach((r, index) => {
    const number = index + 1;
    const results = (r.results || []).filter((res) => idMap.has(res.player_id));
    const rnd = {
      id: nid(), number, title: r.label && r.label !== `Round ${r.number}` ? r.label : null,
      status: "done", maxPoints: Math.max(0, ...results.map((res) => res.points)),
      taskId: null, backupTaskId: null, gimmick: !!r.gimmick, gimmickTaskId: null,
      frozen: r.task ? { category: r.gimmick ? "gimmick" : r.category, text: r.task, rule: r.rule || "" } : null,
    };
    game.rounds.push(rnd);
    for (const res of results) {
      game.scores.push({ id: nid(), playerId: idMap.get(res.player_id), roundId: rnd.id, place: res.place, points: res.points, note: null });
    }
  });
  for (const p of snapshot.players) {
    if (p.bonus) game.scores.push({ id: nid(), playerId: idMap.get(p.id), roundId: null, place: null, points: p.bonus, note: "Carried over" });
  }
  game.tasksEnabled = (snapshot.rounds || []).some((r) => r.task || r.gimmick);
  return game;
}

/* Files ------------------------------------------------------------------- */

// Chrome and Edge get a real save dialog (starting on the Desktop); other browsers download the file.
async function saveTextFile(filename, text, mime, extension) {
  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        startIn: "desktop",
        types: [{ description: filename, accept: { [mime]: [extension] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(text);
      await writable.close();
      return true;
    } catch (error) {
      if (error.name === "AbortError") return false;
      // Anything else (e.g. blocked in this context): fall back to a plain download.
    }
  }
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return true;
}

function csvCell(value) {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/* Host page --------------------------------------------------------------- */

function host() {
  return {
    game: loadGame(),
    banks: loadBanks(),
    tieNext: false,
    session: null, // a saved session file being viewed
    sessionName: "",
    clearAfter: false,
    showRoundPoints: loadPref("showRoundPoints", false),
    showSessionRoundPoints: loadPref("showSessionRoundPoints", true),
    taskKind: "tasks",
    taskQuery: "",
    pickerSlot: "main",
    pickerCat: "",

    init() {
      Alpine.effect(() => writeJson(GAME_KEY, this.game));
      this.$watch("showRoundPoints", (v) => savePref("showRoundPoints", v));
      this.$watch("showSessionRoundPoints", (v) => savePref("showSessionRoundPoints", v));
      // Another tab (e.g. a second host window) changed the game.
      window.addEventListener("storage", (e) => {
        if (e.key === GAME_KEY) this.game = loadGame();
        if (e.key === BANKS_KEY) this.banks = loadBanks();
      });
    },

    get view() {
      return buildView(this.game, this.banks);
    },

    nid() {
      return this.game.nextId++;
    },

    cell(playerId, roundId) {
      return this.view.cells[`${playerId}:${roundId}`] || null;
    },

    // --- Players ------------------------------------------------------------

    addPlayers(input) {
      const names = input.value.split(/[,\n]/).map((n) => n.trim().slice(0, 80)).filter(Boolean);
      if (!names.length) return showToast("Type a name first", "warning");
      const existing = this.game.players.length;
      names.forEach((name, i) => {
        this.game.players.push({ id: this.nid(), name, color: PALETTE[(existing + i) % PALETTE.length] });
      });
      input.value = "";
      input.focus();
      showToast(names.length === 1 ? `Added ${names[0]}` : `Added ${names.length} players`);
    },

    renamePlayer(player, name) {
      name = name.trim().slice(0, 80);
      if (name) player.name = name;
    },

    removePlayer(player) {
      if (!confirm(`Remove ${player.name} and all their points?`)) return;
      this.game.players = this.game.players.filter((p) => p.id !== player.id);
      this.game.scores = this.game.scores.filter((s) => s.playerId !== player.id);
      this.game.picks = this.game.picks.filter((pick) => pick.id !== player.id);
      showToast(`Removed ${player.name}`, "info");
    },

    adjust(player, amount, note = "") {
      amount = parseInt(amount, 10);
      note = note.trim().slice(0, 120);
      if (!amount) return showToast("Enter a non-zero amount", "warning");
      this.game.scores.push({ id: this.nid(), playerId: player.id, roundId: null, place: null, points: amount, note: note || null });
      // Quick +1/-1 taps stay silent; custom adjustments get a confirmation.
      if (Math.abs(amount) !== 1 || note) showToast(`${signed(amount)} for ${player.name}`);
    },

    setBonus(player, value) {
      const target = parseInt(value, 10);
      if (Number.isNaN(target)) return showToast("Bonus must be a whole number", "warning");
      const current = this.view.bonus[player.id];
      if (target !== current) {
        this.game.scores.push({ id: this.nid(), playerId: player.id, roundId: null, place: null, points: target - current, note: "Manual edit" });
      }
    },

    // --- Rounds -------------------------------------------------------------

    nextRoundNumber() {
      return Math.max(0, ...this.game.rounds.map((r) => r.number)) + 1;
    },

    startRound() {
      if (this.view.openRound) return showToast("Finish the current round first", "warning");
      if (!this.game.players.length) return showToast("Add some players first", "warning");
      const rnd = {
        id: this.nid(), number: this.nextRoundNumber(), title: null, status: "open",
        maxPoints: this.game.players.length - 1,
        taskId: null, backupTaskId: null, gimmick: false, gimmickTaskId: null, frozen: null,
      };
      if (this.game.tasksEnabled) {
        this.rollTask(rnd, "main");
        this.rollTask(rnd, "backup");
      }
      this.game.rounds.push(rnd);
      this.game.picks = [];
      this.tieNext = false;
    },

    // Ids already played in finished rounds, so new rolls avoid repeats.
    playedIds(field, gimmick) {
      return new Set(
        this.game.rounds.filter((r) => r.status === "done" && !!r.gimmick === gimmick && r[field] != null).map((r) => r[field]),
      );
    },

    // Give the round a fresh random task in `slot` ("main", "backup" or "gimmick").
    rollTask(rnd, slot) {
      let task;
      if (slot === "gimmick") {
        task = pickTask(this.banks.gimmicks, this.playedIds("gimmickTaskId", true), new Set([rnd.gimmickTaskId]));
        if (task) rnd.gimmickTaskId = task.id;
      } else {
        task = pickTask(this.banks.tasks, this.playedIds("taskId", false), new Set([rnd.taskId, rnd.backupTaskId]));
        if (task) rnd[slot === "main" ? "taskId" : "backupTaskId"] = task.id;
      }
      return task;
    },

    reroll(slot) {
      const rnd = this.view.openRound;
      if (!rnd) return;
      if (!this.rollTask(rnd, slot)) {
        return showToast(`Nothing else to roll. Add more ${slot === "gimmick" ? "gimmicks" : "tasks"} with the Tasks button`, "warning");
      }
      if (slot !== "backup") rnd.gimmick = slot === "gimmick";
    },

    // Put a specific task in a slot. Picking the other slot's task swaps them.
    setTask(slot, taskId) {
      const rnd = this.view.openRound;
      if (!rnd) return;
      if (slot === "gimmick") {
        rnd.gimmickTaskId = taskId;
      } else {
        const field = slot === "main" ? "taskId" : "backupTaskId";
        const other = slot === "main" ? "backupTaskId" : "taskId";
        if (rnd[other] === taskId) [rnd.taskId, rnd.backupTaskId] = [rnd.backupTaskId, rnd.taskId];
        else rnd[field] = taskId;
      }
      if (slot !== "backup") rnd.gimmick = slot === "gimmick";
      document.getElementById("picker-modal").close();
    },

    swapTasks() {
      const rnd = this.view.openRound;
      [rnd.taskId, rnd.backupTaskId] = [rnd.backupTaskId, rnd.taskId];
      rnd.gimmick = false;
      showToast("Backup task is now the main task", "info");
    },

    toggleGimmick() {
      const rnd = this.view.openRound;
      rnd.gimmick = !rnd.gimmick;
      if (rnd.gimmick && rnd.gimmickTaskId == null) this.rollTask(rnd, "gimmick"); // keep an earlier roll
      showToast(rnd.gimmick ? "Gimmick round!" : "Back to the rolled task", "info");
    },

    // --- Placement ----------------------------------------------------------

    placed() {
      return placesFromOrder(this.game.picks);
    },

    placeOf(id) {
      const hit = this.placed().find((p) => p.id === id);
      return hit ? hit.place : null;
    },

    // Bottom place right now: anyone unclicked ties for last.
    currentLastPlace() {
      const placed = this.placed();
      if (placed.length < this.game.players.length) return placed.length + 1;
      return Math.max(0, ...placed.map((p) => p.place));
    },

    pointsFor(place) {
      return pointsForPlace(place, this.currentLastPlace());
    },

    nameOf(id) {
      return this.game.players.find((p) => p.id === id)?.name || "?";
    },

    togglePick(id) {
      const picks = this.game.picks;
      const index = picks.findIndex((p) => p.id === id);
      if (index === -1) {
        picks.push({ id, tie: this.tieNext && picks.length > 0 });
        this.tieNext = false;
        return;
      }
      const [removed] = picks.splice(index, 1);
      // If the next pick was tied to the one removed, it inherits that pick's tie status.
      const next = picks[index];
      if (next && next.tie) next.tie = removed.tie;
    },

    undoPick() {
      const picks = this.game.picks;
      if (picks.length) this.togglePick(picks[picks.length - 1].id);
    },

    confirmRound() {
      const rnd = this.view.openRound;
      if (!rnd) return;
      if (!this.game.picks.length) return showToast("Click players in finishing order first", "warning");
      const playerIds = this.game.players.map((p) => p.id);
      const places = placesForRound(this.game.picks, playerIds);
      const bottom = lastPlace(places.map((p) => p.place));
      for (const { id, place } of places) {
        this.game.scores.push({ id: this.nid(), playerId: id, roundId: rnd.id, place, points: pointsForPlace(place, bottom), note: null });
      }
      rnd.maxPoints = pointsForPlace(1, bottom); // what 1st place earned, for reference
      rnd.frozen = this.game.tasksEnabled ? taskOf(rnd, this.view.taskById, this.view.gimmickById) : null;
      rnd.status = "done";
      this.game.picks = [];
      this.tieNext = false;
      showToast(`${roundLabel(rnd)} saved!`);
      celebrate();
    },

    setRoundTitle(rnd, title) {
      rnd.title = title.trim().slice(0, 80) || null;
    },

    recalcRound(rnd) {
      if (!confirm(`Recalculate ${roundLabel(rnd)} from finishing places (last place = 0)? Manual edits in this round will be overwritten.`)) return;
      const scores = this.game.scores.filter((s) => s.roundId === rnd.id);
      const bottom = lastPlace(scores.map((s) => s.place));
      for (const s of scores) s.points = pointsForPlace(s.place || bottom, bottom);
      rnd.maxPoints = pointsForPlace(1, bottom);
      showToast(`${roundLabel(rnd)} recalculated`);
    },

    deleteRound(rnd) {
      const open = rnd.status === "open";
      if (!confirm(open ? "Cancel this round? Nothing will be saved." : `Delete ${roundLabel(rnd)} and all of its points?`)) return;
      const label = roundLabel(rnd);
      this.game.rounds = this.game.rounds.filter((r) => r.id !== rnd.id);
      this.game.scores = this.game.scores.filter((s) => s.roundId !== rnd.id);
      [...this.game.rounds].sort((a, b) => a.number - b.number).forEach((r, i) => (r.number = i + 1));
      if (open) this.game.picks = [];
      showToast(open ? "Round cancelled" : `Deleted ${label}`, "info");
    },

    setScore(rnd, player, value) {
      const points = parseInt(value, 10);
      if (Number.isNaN(points)) return showToast("Points must be a whole number", "warning");
      const score = this.cell(player.id, rnd.id);
      if (score) score.points = points;
      else this.game.scores.push({ id: this.nid(), playerId: player.id, roundId: rnd.id, place: null, points, note: null });
    },

    // --- Game ---------------------------------------------------------------

    setTasksEnabled(enabled) {
      this.game.tasksEnabled = enabled;
      const rnd = this.view.openRound;
      if (enabled && rnd && rnd.taskId == null) { // round started with tasks off
        this.rollTask(rnd, "main");
        this.rollTask(rnd, "backup");
      }
      showToast(enabled ? "Tasks on" : "Tasks off: just rounds and points", "info");
    },

    exportCsv() {
      const view = this.view;
      const rows = [["Rank", "Player", ...view.doneRounds.map(roundLabel), "Bonus", "Total"]];
      for (const { rank, item: p, total } of view.ranked) {
        rows.push([rank, p.name, ...view.doneRounds.map((r) => this.cell(p.id, r.id)?.points ?? 0), view.bonus[p.id], total]);
      }
      const text = rows.map((row) => row.map(csvCell).join(",")).join("\n") + "\n";
      saveTextFile("gameshow-scores.csv", text, "text/csv", ".csv");
    },

    reset(mode) {
      this.game.scores = [];
      this.game.rounds = [];
      this.game.picks = [];
      if (mode === "all") this.game.players = [];
      document.getElementById("reset-modal").close();
      showToast(mode === "all" ? "New game started" : "Scores cleared, players kept", "info");
    },

    // --- Sessions -----------------------------------------------------------

    openSaveModal() {
      this.sessionName = dateLabel(new Date());
      this.clearAfter = false;
      document.getElementById("save-modal").showModal();
    },

    async saveSession() {
      const name = this.sessionName.trim().slice(0, 80);
      if (!name) return showToast("Give the session a name", "warning");
      if (!this.game.players.length) return showToast("Nothing to save yet. Add players first", "warning");
      if (this.view.openRound) return showToast("Confirm or cancel the open round before saving", "warning");

      const snapshot = sessionSnapshot(this.view, name);
      const saved = await saveTextFile(`${slugify(name)}.json`, JSON.stringify(snapshot, null, 2), "application/json", ".json");
      if (!saved) return;
      if (this.clearAfter) {
        this.game.scores = [];
        this.game.rounds = [];
      }
      document.getElementById("save-modal").close();
      showToast(`Saved “${name}”`);
    },

    async openSessionFile(input) {
      const file = input.files[0];
      input.value = "";
      if (!file) return;
      try {
        const data = JSON.parse(await file.text());
        if (!Array.isArray(data.players) || !Array.isArray(data.rounds)) throw new Error("not a session");
        this.session = data;
        window.scrollTo({ top: 0 });
      } catch {
        showToast("That file isn't a saved steam scavenge session", "error");
      }
    },

    resumeSession() {
      if (this.game.players.length && !confirm("Replace the current game with this saved one? Save the current game first if you want to keep it.")) return;
      this.game = gameFromSnapshot(this.session);
      showToast(`Loaded “${this.session.name}”`);
      this.session = null;
    },

    sessionCell(player, index) {
      const result = this.session.rounds[index].results?.find((r) => r.player_id === player.id);
      return result ? result.points : "–";
    },

    // Round history shows the game's rounds, or the open session file's.
    get historyRounds() {
      return this.session ? this.session.rounds : this.view.history;
    },

    get historyShowPoints() {
      return this.session ? this.showSessionRoundPoints : this.showRoundPoints;
    },

    set historyShowPoints(value) {
      if (this.session) this.showSessionRoundPoints = value;
      else this.showRoundPoints = value;
    },

    // --- Task bank ----------------------------------------------------------

    openTaskManager() {
      this.taskQuery = "";
      document.getElementById("tasks-modal").showModal();
    },

    get bankGroups() {
      return groupByCategory(this.banks[this.taskKind]);
    },

    get bankCategories() {
      return [...new Set(this.banks.tasks.map((t) => t.category))].sort();
    },

    matchesQuery(task) {
      const q = this.taskQuery.trim().toLowerCase();
      return !q || `${task.category} ${task.text} ${task.rule}`.toLowerCase().includes(q);
    },

    // Build a task from an add/edit form, or show what's missing.
    taskFromForm(form, id) {
      const data = new FormData(form);
      const text = (data.get("text") || "").trim();
      if (!text) return showToast("The task needs some text", "warning");
      const category = this.taskKind === "gimmicks" ? "gimmick" : (data.get("category") || "").trim().toLowerCase();
      if (!category) return showToast("Give the task a category", "warning");
      return { id, category, text, rule: this.taskKind === "gimmicks" ? (data.get("rule") || "").trim() : "" };
    },

    saveBanks() {
      writeJson(BANKS_KEY, this.banks);
    },

    addTask(form) {
      const list = this.banks[this.taskKind];
      const task = this.taskFromForm(form, nextTaskId(list));
      if (!task) return;
      list.push(task);
      this.saveBanks();
      form.reset();
      showToast("Added");
    },

    editTask(form, task) {
      const updated = this.taskFromForm(form, task.id);
      if (!updated) return false;
      Object.assign(task, updated);
      this.saveBanks();
      showToast("Saved");
      return true;
    },

    deleteTask(task) {
      if (!confirm(`Delete “${task.text}”?`)) return;
      this.banks[this.taskKind] = this.banks[this.taskKind].filter((t) => t.id !== task.id);
      this.saveBanks();
      showToast("Deleted");
    },

    resetBanks() {
      if (!confirm("Put the task and gimmick lists back to the defaults? Your edits will be lost.")) return;
      removeKey(BANKS_KEY);
      this.banks = loadBanks();
      showToast("Task lists reset", "info");
    },

    // --- Task picker --------------------------------------------------------

    openPicker(slot) {
      this.pickerSlot = slot;
      const current = this.pickerCurrent;
      const groups = this.pickerGroups;
      this.pickerCat = current ? current.category : groups.length ? groups[0][0] : "";
      document.getElementById("picker-modal").showModal();
    },

    get pickerGroups() {
      return groupByCategory(this.pickerSlot === "gimmick" ? this.banks.gimmicks : this.banks.tasks);
    },

    get pickerItems() {
      return this.pickerGroups.find(([category]) => category === this.pickerCat)?.[1] || [];
    },

    get pickerCurrent() {
      return { main: this.view.openTask, backup: this.view.backupTask, gimmick: this.view.gimmickTask }[this.pickerSlot];
    },
  };
}

/* Scoreboard page --------------------------------------------------------- */

function scoreboard() {
  return {
    game: loadGame(),
    banks: loadBanks(),

    init() {
      let knownRounds = this.view.doneRounds.length;
      // The host page writes to localStorage; this picks up every change from other tabs.
      window.addEventListener("storage", (e) => {
        if (e.key === GAME_KEY) this.game = loadGame();
        if (e.key === BANKS_KEY) this.banks = loadBanks();
        const rounds = this.view.doneRounds.length;
        if (rounds > knownRounds) celebrate();
        knownRounds = rounds;
      });
    },

    get view() {
      return buildView(this.game, this.banks);
    },

    lastScore(player) {
      const last = this.view.lastRound;
      return last ? this.view.cells[`${player.id}:${last.id}`] || null : null;
    },
  };
}

/* UI helpers -------------------------------------------------------------- */

function showToast(message, kind = "success") {
  const box = document.getElementById("toasts");
  if (!box || !message) return;
  const toast = document.createElement("div");
  toast.className = `alert alert-${kind} py-2 text-sm shadow-lg animate__animated animate__fadeInUp animate__faster`;
  toast.textContent = message;
  box.appendChild(toast);
  setTimeout(() => {
    toast.classList.replace("animate__fadeInUp", "animate__fadeOutDown");
    toast.addEventListener("animationend", () => toast.remove(), { once: true });
  }, 2800);
}

function celebrate() {
  if (typeof confetti !== "function") return;
  confetti({ particleCount: 140, spread: 90, origin: { y: 0.6 } });
  setTimeout(() => confetti({ particleCount: 70, angle: 60, spread: 65, origin: { x: 0, y: 0.7 } }), 180);
  setTimeout(() => confetti({ particleCount: 70, angle: 120, spread: 65, origin: { x: 1, y: 0.7 } }), 320);
}

function closeDropdowns() {
  document.activeElement?.blur();
}

function toggleScoreboardFullscreen() {
  const modal = document.getElementById("scoreboard-modal");
  if (document.fullscreenElement) document.exitFullscreen();
  else modal.requestFullscreen();
}

// Hide the main task or backup on the host page (for streaming). Classes sit on <html> so re-renders never flash the text.
const HIDE_SLOTS = ["main", "backup"];

function applyHidden() {
  for (const slot of HIDE_SLOTS) {
    document.documentElement.classList.toggle(`hide-${slot}`, loadPref(`hide-${slot}`, false));
  }
}

function toggleHidden(slot) {
  const hidden = document.documentElement.classList.toggle(`hide-${slot}`);
  savePref(`hide-${slot}`, hidden);
}

applyHidden();

// Alpine adds elements as data changes; swap any new <i data-lucide> placeholders for icons.
let iconsQueued = false;

function refreshIcons() {
  iconsQueued = false;
  if (window.lucide) lucide.createIcons();
}

document.addEventListener("DOMContentLoaded", () => {
  refreshIcons();
  new MutationObserver(() => {
    if (iconsQueued || !document.querySelector("i[data-lucide]")) return;
    iconsQueued = true;
    requestAnimationFrame(refreshIcons);
  }).observe(document.body, { childList: true, subtree: true });
});
