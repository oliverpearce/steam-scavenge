// Client-side glue: the round placement store, toasts, confetti and icon refreshes.

document.addEventListener("alpine:init", () => {
  // Lives outside the swapped DOM so placements survive HTMX re-renders (e.g. a +1 mid-round).
  Alpine.store("round", {
    roundId: null,
    picks: [], // [{ id, tie }] in finishing order; tie = shares the previous pick's place
    tieNext: false,

    isActive() {
      return this.roundId !== null;
    },

    sync(roundId) {
      if (this.roundId === roundId) return;
      this.roundId = roundId;
      this.picks = [];
      this.tieNext = false;
    },

    playerCount() {
      return document.querySelectorAll("[data-player-id]").length;
    },

    // Bottom place, matching scoring.places_for_round: anyone unclicked ties for last.
    lastPlace() {
      const placed = this.placed();
      if (placed.length < this.playerCount()) return placed.length + 1;
      return Math.max(0, ...placed.map((p) => p.place));
    },

    // Standard competition places, matching scoring.places_from_order on the server.
    placed() {
      let place = 0;
      return this.picks.map((pick, i) => {
        if (!(pick.tie && i > 0)) place = i + 1;
        return { id: pick.id, place };
      });
    },

    placeOf(id) {
      const hit = this.placed().find((p) => p.id === id);
      return hit ? hit.place : null;
    },

    // Last place gets 0; each place above earns one more.
    pointsFor(place) {
      return Math.max(this.lastPlace() - place, 0);
    },

    medal(place) {
      return { 1: "🥇", 2: "🥈", 3: "🥉" }[place] || `#${place}`;
    },

    nameOf(id) {
      const tile = document.querySelector(`[data-player-id="${id}"]`);
      return tile ? tile.dataset.playerName : "?";
    },

    toggle(id) {
      const index = this.picks.findIndex((p) => p.id === id);
      if (index === -1) {
        this.picks.push({ id, tie: this.tieNext && this.picks.length > 0 });
        this.tieNext = false;
        return;
      }
      const [removed] = this.picks.splice(index, 1);
      // If the next pick was tied to the one removed, it inherits that pick's tie status.
      const next = this.picks[index];
      if (next && next.tie) next.tie = removed.tie;
    },

    undo() {
      if (this.picks.length) this.toggle(this.picks[this.picks.length - 1].id);
    },

    confirm() {
      if (!this.isActive() || !this.picks.length) return;
      htmx.ajax("POST", `/rounds/${this.roundId}/confirm`, {
        target: "#board",
        swap: "outerHTML",
        values: { order: JSON.stringify(this.picks) },
      });
    },
  });
});

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

function refreshIcons() {
  if (window.lucide) lucide.createIcons();
}

// Scoreboard polling sends its current version; the server answers 204 when nothing changed.
function leaderboardVersion() {
  const lb = document.getElementById("lb");
  return lb ? lb.dataset.version : "";
}

function leaderboardRounds() {
  const lb = document.getElementById("lb");
  return lb ? Number(lb.dataset.rounds) : 0;
}

function openScoreboard() {
  const modal = document.getElementById("scoreboard-modal");
  modal.showModal();
  htmx.trigger("#scoreboard-live", "refresh");
}

// Per-browser UI preferences (e.g. the round history points toggle). Storage can be blocked, so fail quietly.
function loadPref(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

function savePref(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

function openTaskManager() {
  document.getElementById("tasks-modal").showModal();
  htmx.ajax("GET", "/partials/tasks?kind=tasks", { target: "#task-manager", swap: "outerHTML" });
}

function refreshBoard() {
  htmx.ajax("GET", "/partials/board", { target: "#board", swap: "outerHTML" });
}

function toggleScoreboardFullscreen() {
  const modal = document.getElementById("scoreboard-modal");
  if (document.fullscreenElement) document.exitFullscreen();
  else modal.requestFullscreen();
}

let knownRounds = null;

document.addEventListener("DOMContentLoaded", () => {
  refreshIcons();
  knownRounds = leaderboardRounds();
});

document.addEventListener("htmx:afterSettle", () => {
  refreshIcons();
  // Celebrate on the scoreboard when a new round lands.
  if (document.getElementById("lb")) {
    const rounds = leaderboardRounds();
    if (knownRounds !== null && rounds > knownRounds) celebrate();
    knownRounds = rounds;
  }
});

// Events raised by the server's HX-Trigger header.
document.addEventListener("toast", (e) => showToast(e.detail.message, e.detail.kind));
document.addEventListener("confetti", celebrate);

document.addEventListener("htmx:responseError", () => showToast("Something went wrong. Try again.", "error"));
document.addEventListener("htmx:sendError", () => showToast("Can't reach the server. Is it still running?", "error"));
