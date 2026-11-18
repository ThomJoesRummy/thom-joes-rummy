// Progressive Rummy table, fifth edition (update 1).  Talks to server.py: the server
// decides every move; this page only shows the table and sends what the
// player taps.
//
// How a turn works on this page:
//   1. Draw: tap the draw pile or the top discard (third edition: the discard
//      stays open after you've laid down, unless the host turns that off).
//   2. Tap cards in your hand to pick them.  The buttons under your hand
//      change to say what you can do with the cards you picked:
//        - before you've laid down: "Lay down my goal" (the table works out
//          the groups from the cards you picked) or "Find my goal"
//        - after you've laid down: "Put down as a new group" for 3 or more
//          cards, or pick one card and tap a glowing group on the table to
//          add it there (anyone's group; deuces and jokers too)
//   3. Discard: pick one card and tap "Discard", or tap the discard pile.
"use strict";

const $ = (id) => document.getElementById(id);
const SESSION_KEY = "progressive-rummy-session";

let session = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
let state = null;
let version = -1;
let selected = new Set();
let sortMode = "suit";
let freshCard = null;
let dealtRound = Number(sessionStorage.getItem("dealt-round") || 0);
let modalDismissed = 0;
let busy = false;

const SEAT_COLORS = ["#f0a83a", "#4fa8e8", "#e0628a", "#82cc6c"];
const ARROWS = { top: "\u2191", left: "\u2190", right: "\u2192", bottom: "\u2193" };

// ------------------------------------------------------------ server calls
async function post(path, body) {
  const res = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({ ok: false, error: "The table didn't answer." }));
  if (!data.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

// Sends one move.  Returns the server's result, or null when the move was
// refused (the reason is shown in the message box).
async function act(action, extra = {}) {
  if (busy) return null;
  busy = true;
  try {
    const data = await post("/api/action", { code: session.code, token: session.token, action, ...extra });
    if (data.result && data.result.drawn !== undefined) freshCard = data.result.drawn;
    apply(data.state);
    return data.result || {};
  } catch (e) {
    Sound.play("oops");
    toast(e.message, true);
    return null;
  } finally {
    busy = false;
  }
}

async function pollLoop() {
  const mySession = session;
  while (session === mySession) {
    try {
      const url = `/api/state?code=${encodeURIComponent(session.code)}&token=${encodeURIComponent(session.token)}&since=${version}`;
      const res = await fetch(url, { cache: "no-store" });
      if (session !== mySession) return;        // you left this table while waiting
      if (res.status === 403 || res.status === 404) {
        const data = await res.json().catch(() => ({}));
        leave(data.error || "That table is gone.");
        return;
      }
      const data = await res.json();
      $("conn").classList.add("hidden");
      if (session === mySession) apply(data.state);
    } catch (e) {
      if (session !== mySession) return;
      $("conn").classList.remove("hidden");
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

function saveSession(s) {
  session = s;
  localStorage.setItem(SESSION_KEY, JSON.stringify(s));
  history.replaceState(null, "", `/?table=${s.code}`);
  version = -1;
  pollLoop();
}

function leave(message) {
  localStorage.removeItem(SESSION_KEY);
  session = null;
  state = null;
  show("lobby");
  if (message) toast(message);
}

// ------------------------------------------------------------ helpers
function show(screen) {
  for (const id of ["lobby", "waiting", "game"]) $(id).classList.toggle("hidden", id !== screen);
}

let toastTimer = null;
function toast(msg, isError = false) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.toggle("error", isError);
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), isError ? 7000 : 4500);
}
$("toast").onclick = () => $("toast").classList.add("hidden");

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function cardEl(c, tag = "div") {
  const e = el(tag, "card");
  if (c.rank === 0) {
    e.classList.add("joker");
    e.append(el("span", "corner", "JK"), el("span", "pip", "\u2605"), el("span", "corner br", "JK"));
  } else {
    if (c.suit === "H" || c.suit === "D") e.classList.add("red");
    const corner = el("span", "corner", c.label);
    corner.append(el("small", "", c.symbol));
    const corner2 = el("span", "corner br", c.label);
    corner2.append(el("small", "", c.symbol));
    e.append(corner, el("span", "pip", c.symbol), corner2);
  }
  if (c.wild) { e.classList.add("is-wild"); e.append(el("span", "wild-tag", "WILD")); }
  e.title = c.name + (c.wild ? " (wild)" : "");
  e.setAttribute("aria-label", e.title);
  return e;
}

function backEl() { return el("div", "card back"); }

function shortName(c) {
  return c.rank === 0 ? "Joker" : `${c.label}${c.symbol}`;
}

function positions(n) {
  // Seats go clockwise; the next player is on your left.
  if (n === 2) return ["bottom", "top"];
  if (n === 3) return ["bottom", "left", "right"];
  return ["bottom", "left", "top", "right"];
}

function whereIs(seat) {
  const n = state.players.length;
  return positions(n)[(seat - state.you + n) % n];
}

function playerName(seat) {
  const p = state.players.find((q) => q.seat === seat);
  return p ? p.name : "?";
}

const SUIT_ORDER = { S: 0, H: 1, C: 2, D: 3 };
function sortHand(cards) {
  const rankKey = (c) => (c.wild ? 100 + c.rank : c.rank);
  const suitKey = (c) => (c.wild ? 9 : SUIT_ORDER[c.suit]);
  return [...cards].sort((a, b) =>
    sortMode === "suit"
      ? suitKey(a) - suitKey(b) || rankKey(a) - rankKey(b)
      : rankKey(a) - rankKey(b) || suitKey(a) - suitKey(b));
}

function goalSize() {
  return state.round.groups.reduce((n, g) => n + g.size, 0);
}

function pickedCards() {
  const byId = new Map(state.hand.map((c) => [c.id, c]));
  return [...selected].map((id) => byId.get(id)).filter(Boolean);
}

// ------------------------------------------------------------ state updates
function apply(s) {
  if (!s) return;
  const prev = state;
  const newDeal = s.status === "playing" && dealtRound !== s.round.number;
  state = s;
  version = s.version;
  const ids = new Set(s.hand.map((c) => c.id));
  selected = new Set([...selected].filter((id) => ids.has(id)));
  const wasMine = prev && prev.status === "playing" && prev.current === prev.you;
  const isMine = s.status === "playing" && s.current === s.you;
  if ((wasMine && !isMine) || (prev && prev.round.number !== s.round.number)) selected.clear();
  if (freshCard !== null && !ids.has(freshCard)) freshCard = null;
  render();
  reactToChanges(prev, s, newDeal);
}

// Sounds and the "your turn" nudge, worked out from what changed.
function reactToChanges(prev, s, newDeal) {
  const mine = s.status === "playing" && s.current === s.you;
  const wasMine = !!prev && prev.status === "playing" && prev.current === prev.you &&
    prev.round.number === s.round.number;
  if (newDeal) {
    Sound.play("deal", Math.min(s.round.dealt * s.players.length, 24));
    if (mine) setTimeout(() => yourTurn(), 1400);
    return;
  }
  if (!prev || prev.round.number !== s.round.number) return;
  const tableCards = (st) => st.table.reduce((n, m) => n + m.cards.length, 0);
  if (prev.status === "playing" && (s.status === "round_over" || s.status === "game_over")) {
    Sound.play("discard");
    setTimeout(() => Sound.play("roundOver"), 250);
    return;
  }
  if (s.status !== "playing") return;
  if (tableCards(s) > tableCards(prev)) Sound.play("place");
  if (prev.phase === "draw" && s.phase === "play" && prev.current === s.current) Sound.play("draw");
  if (s.discard_count > prev.discard_count && prev.current !== s.current) Sound.play("discard");
  if (mine && !wasMine) setTimeout(() => yourTurn(), 300);
}

function yourTurn() {
  if (!state || state.status !== "playing" || state.current !== state.you) return;
  Sound.play("yourTurn");
  const rack = $("rack");
  rack.classList.remove("flash");
  void rack.offsetWidth;            // restart the glow animation
  rack.classList.add("flash");
  toast(`Your turn, ${state.players[state.you].name}! Start by drawing a card.`);
}

// ------------------------------------------------------------ rendering
function render() {
  if (!state) return;
  if (drag && drag.started) { renderLater = true; return; }   // finish the drag first
  if (state.status === "lobby") return renderWaiting();
  show("game");
  renderTop();
  renderSeats();
  renderZones();
  renderCenter();
  renderMe();
  renderScores();
  renderOptions();
  renderModal();
  fitWithTableArt();
  updateJump();
  if (state.status === "playing" && dealtRound !== state.round.number) {
    dealtRound = state.round.number;
    sessionStorage.setItem("dealt-round", String(dealtRound));
  }
}

// Third edition: computer speed button and the host's table rule.
function renderOptions() {
  const o = state.options || {};
  const sb = $("speed-btn");
  sb.textContent = o.slow_bots ? "Computers: slower" : "Computers: normal speed";
  sb.setAttribute("aria-pressed", o.slow_bots ? "true" : "false");
  const box = $("rule-discard");
  box.checked = !!o.discard_after_laydown;
  box.disabled = !state.can.options;
  $("rule-note").textContent = state.can.options
    ? "Only you can change this, because you made the table."
    : `Only ${(state.players[state.host] || state.players[0]).name} can change this.`;
}

// Third edition: on a computer screen, shrink the whole table a little so the
// table, your hand and the scores all fit in the window without scrolling up
// and down.  Phones (narrow screens) scroll as before.
const FIT_MIN = 0.6;        // never smaller than 60%, so cards stay readable
// Fourth edition: on a touch screen (a tablet, or a phone turned sideways)
// buttons and cards must stay big enough for a finger, so the table shrinks
// less and the page scrolls instead.
const TOUCH = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
const FIT_MIN_TOUCH = 0.85;
function fitToWindow() {
  const layout = document.querySelector("#game .layout");
  const area = document.querySelector("#game .table-area");
  const top = document.querySelector("#game .topbar");
  if (!layout || !area) return;
  if (window.innerWidth <= 760 || $("game").classList.contains("hidden")) {
    layout.style.zoom = "";
    layout.style.removeProperty("--fit-h");
    return;
  }
  const avail = window.innerHeight - top.offsetHeight;
  const pad = 16;                                  // layout padding, top and bottom
  layout.style.setProperty("--fit-h", "120px");     // keep the score panel out of the measurement
  const setZ = (v) => { layout.style.zoom = String(v); return (area.scrollHeight + pad) * v; };
  let z = 1;
  if (setZ(1) > avail) {
    // A smaller table is also a wider one (its groups wrap less), so find the
    // largest size that fits by stepping, not by one division.
    const min = TOUCH ? FIT_MIN_TOUCH : FIT_MIN;
    z = Math.max(min, avail / (area.scrollHeight + pad));
    while (z < 1 && setZ(Math.min(1, z + 0.02)) <= avail) z = Math.min(1, z + 0.02);
    while (z > min && setZ(z) > avail) z = Math.max(min, z - 0.02);
    setZ(z);
  }
  layout.style.setProperty("--fit-h", `${Math.floor(avail / z - pad)}px`);
}

// ---------------------------------------------------------------------------
// Fifth edition, update 2: Tom's own table picture (static/table-art.jpg, made
// from his design by art_source/make_table_art.py).  Measurements are in pixels
// of his 1254 x 1254 picture, from the centre of the gold rings:
const ART = {
  size: 1254,
  inner: 312,     // inner gold ring: it goes round the draw pile and the discard pile
  text: 320,      // "Thom Joe's" (top) and "Progressive Rummy" (bottom) start here
  topText: 385,   // ... and end here
  champ: 425,     // CHAMPIONSHIP, under "Progressive Rummy", ends here
  outer: 505,     // outer gold ring
  corner: 330,    // the corner of the picture that holds each card suit
  leather: 320,   // the leather tile is cut at the picture's own size
};
let artInfo = { mode: "none", s: 0 };

// Size of one CSS pixel on screen (the table is shrunk to fit on a computer).
function cssUnit(elm) {
  const w = parseFloat(getComputedStyle(elm).width);
  return w > 0 ? elm.getBoundingClientRect().width / w : 1;
}
function shown(elm) { return !!elm && elm.getClientRects().length > 0 && elm.getBoundingClientRect().width > 0; }

// Picture size that keeps the draw pile and the discard pile (with their
// labels) inside the writing, so "Progressive Rummy" isn't hidden under them.
function artScale() {
  const piles = document.querySelector("#felt .piles");
  const k = cssUnit(piles);
  const r = piles.getBoundingClientRect();
  return (Math.hypot(r.width / 2, r.height / 2) / k + 3) / ART.text;
}
function px(elm, side, k) { return elm.getBoundingClientRect()[side] / k; }

// Step 1 (changes the layout, so it runs before fitToWindow).  The piles get
// just enough space above and below them for the writing round the crown to
// show.  (Update 3: the round's goal has moved off the table, next to your cards.)
function layoutTableArt() {
  const felt = $("felt");
  if (!felt || $("game").classList.contains("hidden")) return;
  const disc = $("disc");
  felt.classList.remove("plaque-corner", "no-tl");
  disc.style.marginTop = disc.style.marginBottom = "";
  const s = artScale();
  const k = cssUnit(felt);
  // Update 3: the round's goal is no longer on the table (it sits with your
  // cards), so nothing has to be fitted into the top left corner any more.
  const mode = window.innerWidth <= 760 ? "phone" : "middle";
  // Room for the writing: above the piles up to the players' name plates and
  // cards, below them down to the turn messages.  A few passes, because the
  // middle of the table re-centres.
  const banner = $("turn-banner"), steps = $("steps");
  let mt = 0, mb = 0;
  for (let pass = 0; pass < 3; pass++) {
    const p = document.querySelector("#felt .piles");
    const cy = (px(p, "top", k) + px(p, "bottom", k)) / 2;
    // The lowest name plate or row of laid-down cards above the piles that
    // sits over the writing (the top player on a computer; on a phone, where
    // the seats stack, the seat just above the middle).
    const cx = (px(p, "left", k) + px(p, "right", k)) / 2, reach = ART.topText * s;
    const overs = [...felt.querySelectorAll(".spot:not(.bottom) .plate, .spot:not(.bottom) .zone")]
      .filter((e) => shown(e) && px(e, "bottom", k) < cy && px(e, "right", k) > cx - reach && px(e, "left", k) < cx + reach)
      .map((e) => px(e, "bottom", k));
    const above = overs.length ? Math.max(...overs) : null;
    const lows = [banner, steps].filter((e) => shown(e) && e.getBoundingClientRect().height > 3);
    const below = lows.length ? Math.min(...lows.map((e) => px(e, "top", k))) : null;
    const needTop = above === null ? 0 : Math.ceil(ART.topText * s + 3 - (cy - above));
    const needBottom = below === null ? 0 : Math.ceil(cy + ART.champ * s + 3 - below);
    if (needTop <= 0 && needBottom <= 0) break;
    mt = Math.max(0, mt + Math.max(0, needTop));
    mb = Math.max(0, mb + Math.max(0, needBottom));
    disc.style.marginTop = `${mt}px`;
    disc.style.marginBottom = `${mb}px`;
  }
  artInfo = { mode, s, mt, mb };
}

// The room made for the writing must not make the table smaller on screen by
// more than a little, or make the page scroll on a computer.  If it would,
// the room is cut back (the bottom of the writing can then go under the turn
// messages); fitting the whole table on the screen comes first.
const ART_MAX_SHRINK = 0.12;
function setArtMargins(f) {
  const disc = $("disc");
  disc.style.marginTop = `${Math.round((artInfo.mt || 0) * f)}px`;
  disc.style.marginBottom = `${Math.round((artInfo.mb || 0) * f)}px`;
  artInfo.f = f;
}
function zoomNow() { return parseFloat(document.querySelector("#game .layout").style.zoom) || 1; }
function overflowing() { return document.documentElement.scrollHeight > window.innerHeight + 1; }
function fitWithTableArt() {
  if ($("game").classList.contains("hidden")) { fitToWindow(); return; }
  artBusy = true;
  try { fitWithTableArtNow(); } finally { artBusy = false; artSig = tableArtSig(); }
}
function fitWithTableArtNow() {
  layoutTableArt();
  if (window.innerWidth > 760 && (artInfo.mt || artInfo.mb)) {
    setArtMargins(0); fitToWindow();
    const z0 = zoomNow(), over0 = overflowing(), h0 = document.documentElement.scrollHeight;
    setArtMargins(1); fitToWindow();
    // When the page already scrolls (a phone turned sideways), the writing may
    // add at most a little to the scrolling.
    const ok = () => zoomNow() >= z0 - ART_MAX_SHRINK - 1e-6 &&
      (over0 ? document.documentElement.scrollHeight <= h0 + 40 : !overflowing());
    if (!ok()) {
      let lo = 0, hi = 1;
      for (let i = 0; i < 6; i++) {
        const mid = (lo + hi) / 2;
        setArtMargins(mid); fitToWindow();
        if (ok()) lo = mid; else hi = mid;
      }
      setArtMargins(lo); fitToWindow();
    }
  } else {
    artInfo.f = 1;
    fitToWindow();
  }
  placeTableArt();
}

// Anything on the table that changes size (a label, a laid-down group, the
// goal) moves the piles, so the picture is put back under them.
let artRaf = 0, artBusy = false, artSig = "";
function tableArtSig() {
  const r = (e) => { if (!e) return ""; const b = e.getBoundingClientRect(); return [b.left, b.top, b.width, b.height].map(Math.round).join(","); };
  return [innerWidth, innerHeight, r($("felt")), r(document.querySelector("#felt .piles")),
    r($("goal-plaque")), r($("turn-banner")), r($("steps"))].join("|");
}
if (window.ResizeObserver) {
  const ro = new ResizeObserver(() => {
    if (artBusy || artRaf) return;
    artRaf = requestAnimationFrame(() => {
      artRaf = 0;
      if (state && state.status !== "lobby" && tableArtSig() !== artSig) fitWithTableArt();
    });
  });
  ["felt", "disc", "goal-plaque", "turn-banner", "steps"].forEach((id) => { const e = $(id); if (e) ro.observe(e); });
  const piles = document.querySelector("#felt .piles");
  if (piles) ro.observe(piles);
}

// Step 2 (after fitToWindow, moves nothing else): put the middle of the gold
// rings right under the middle of the two piles.
function placeTableArt() {
  const felt = $("felt"), art = $("table-art"), clip = $("table-art-clip");
  if (!felt || !art || $("game").classList.contains("hidden")) return;
  const k = cssUnit(felt);
  const innerLeft = px(felt, "left", k) + felt.clientLeft, innerTop = px(felt, "top", k) + felt.clientTop;
  const p = document.querySelector("#felt .piles");
  const cx = (px(p, "left", k) + px(p, "right", k)) / 2 - innerLeft;
  const cy = (px(p, "top", k) + px(p, "bottom", k)) / 2 - innerTop;
  const s = artInfo.s || artScale();
  const size = ART.size * s;
  art.style.width = art.style.height = `${size}px`;
  art.style.left = `${cx - size / 2}px`;
  art.style.top = `${cy - size / 2}px`;
  clip.style.setProperty("--art-px", `${size}px`);
  clip.style.setProperty("--corner-px", `${ART.corner * s}px`);
  felt.style.setProperty("--leather-px", `${ART.leather * s}px`);
  // A card suit in a corner is left out where a player's name, cards or
  // writing would sit on it.
  const busy = [...felt.querySelectorAll(".spot .plate, .spot .zone, .spot .backs, #goal-plaque, #turn-banner, #steps")]
    .filter(shown).map((e) => e.getBoundingClientRect());
  clip.querySelectorAll(".table-corner").forEach((c) => {
    c.classList.remove("off");
    if (getComputedStyle(c).display === "none") return;
    const b = c.getBoundingClientRect();
    const core = 0.62;     // the suit itself sits in this part of the corner
    const r = {
      left: c.classList.contains("tl") || c.classList.contains("bl") ? b.left : b.right - b.width * core,
      right: c.classList.contains("tl") || c.classList.contains("bl") ? b.left + b.width * core : b.right,
      top: c.classList.contains("tl") || c.classList.contains("tr") ? b.top : b.bottom - b.height * core,
      bottom: c.classList.contains("tl") || c.classList.contains("tr") ? b.top + b.height * core : b.bottom,
    };
    if (busy.some((o) => o.left < r.right && o.right > r.left && o.top < r.bottom && o.bottom > r.top)) c.classList.add("off");
  });
  artInfo = { ...artInfo, s, cx, cy, W: felt.clientWidth, H: felt.clientHeight,
    corners: [...clip.querySelectorAll(".table-corner")].filter((c) => getComputedStyle(c).display !== "none").length };
  window.__tableArt = artInfo;          // for the developer checks
}

function renderWaiting() {
  show("waiting");
  $("w-code").textContent = state.room;
  // On the game computer the address is "localhost", which a phone can't
  // use, so show the Wi-Fi address the black window also shows.
  const local = /^(localhost|127\.|\[::1\])/.test(location.hostname);
  const origin = local && lanOrigin ? lanOrigin : location.origin;
  $("w-link").textContent = `${origin}/?table=${state.room}`;
  $("w-phone").classList.toggle("hidden", local && !lanOrigin);
  $("w-phone").textContent = local
    ? "That link is for phones and tablets on the same Wi-Fi as this computer, " +
      "an iPhone or an Android. They just open it in their web browser; nothing to install."
    : "Text that link to your friends. They open it in the web browser on an iPhone, " +
      "an Android or a computer. Nothing to install and no sign-up.";
  if (local && lanOrigin === undefined) {
    lanOrigin = null;
    fetch("/api/info").then((r) => r.json()).then((d) => { lanOrigin = d.lan || null; render(); }).catch(() => {});
  }
  const list = $("w-players");
  list.replaceChildren(...state.players.map((p) =>
    el("li", "", p.name + (p.seat === state.you ? " (you)" : "") + (p.seat === 0 ? ", made the table" : ""))),
    ...Array.from({ length: state.max_players - state.players.length }, () => el("li", "empty-seat", "Empty seat")));
  const empty = state.max_players - state.players.length;
  $("start").classList.toggle("hidden", !state.can.start);
  $("fill-btn").classList.toggle("hidden", !state.can.fill_bots);
  clockSetAt = Date.now();
  clockSeconds = state.seconds_left;
  if (empty === 0) {
    $("w-note").textContent = "All four seats are taken. Dealing now.";
  } else if (state.window < state.windows) {
    $("w-note").textContent = `${empty} empty seat${empty > 1 ? "s" : ""}. If they aren't filled, ` +
      "the clock starts over once. Then computer players take the empty seats for the whole game.";
  } else {
    $("w-note").textContent = `Last call: when the clock runs out, computer players take ` +
      `the ${empty} empty seat${empty > 1 ? "s" : ""} for the whole game.`;
  }
  updateClock();
}

// The joining clock counts down here between updates from the table.
let clockSeconds = null;
let clockSetAt = 0;
function updateClock() {
  const box = $("w-clock");
  if (!state || state.status !== "lobby" || clockSeconds === null) { box.textContent = ""; return; }
  const left = Math.max(0, Math.round(clockSeconds - (Date.now() - clockSetAt) / 1000));
  const label = state.window < state.windows ? "Time to join" : "Clock started over";
  box.textContent = `${label}: 0:${String(left).padStart(2, "0")}`;
  box.classList.toggle("low", left <= 10);
}
setInterval(updateClock, 500);

function renderTop() {
  const r = state.round;
  $("g-round").textContent = `Round ${r.number} of ${r.last}`;
  // Turn order, starting left of the dealer, with whose turn it is lit up.
  const n = state.players.length;
  const order = $("turn-order");
  order.replaceChildren(el("span", "label", "Turn order:"));
  const first = state.players.findIndex((p) => p.dealer);
  for (let k = 1; k <= n; k++) {
    const p = state.players[(first + k) % n];
    const chip = el("span", "chip" + (p.turn ? " now" : ""), p.seat === state.you ? "You" : p.name);
    chip.style.setProperty("--seat-color", SEAT_COLORS[p.seat % 4]);
    order.append(chip);
    if (k < n) order.append(el("span", "sep", "\u203a"));
  }
}

function avatarEl(p) {
  const a = el("div", "avatar" + (p.turn ? " thinking" : "") + (p.bot ? " is-bot" : ""));
  a.style.setProperty("--seat-color", SEAT_COLORS[p.seat % 4]);
  a.append(el("span", "initial", (p.name.trim()[0] || "?").toUpperCase()));
  a.setAttribute("aria-hidden", "true");
  return a;
}

function plateContent(box, p) {
  box.replaceChildren();
  box.style.setProperty("--seat-color", SEAT_COLORS[p.seat % 4]);
  box.classList.toggle("is-turn", p.turn);
  const line1 = el("div", "plate-line");
  line1.append(avatarEl(p));
  const nameBox = el("div", "plate-name");
  nameBox.append(el("strong", "", p.name + (p.seat === state.you ? " (you)" : "")));
  nameBox.append(el("span", "plate-score", `${p.total} points so far`));
  line1.append(nameBox);
  box.append(line1);
  const badges = el("div", "badges");
  if (p.turn) badges.append(el("span", "badge turn", p.seat === state.you ? "YOUR TURN" :
    state.phase === "draw" ? "Turn: drawing" : "Turn: playing"));
  badges.append(el("span", "badge " + (p.laid ? "down" : "notdown"), p.laid ? "Goal laid down" : "Not down yet"));
  if (p.bot) badges.append(el("span", "badge bot", "Computer"));
  if (p.dealer) badges.append(el("span", "badge", "Dealer"));
  box.append(badges);
  // Third edition: what this player did on this turn, or on their last one.
  if (p.seat !== state.you && state.status === "playing") {
    const moves = p.moves || [];
    const line = el("div", "plate-moves" + (p.turn ? " live" : ""));
    if (moves.length) {
      line.append(el("b", "", p.turn ? "This turn: " : "Last turn: "));
      line.append(document.createTextNode(moves.join(" \u2192 ")));
    } else {
      line.append(el("b", "", "Last turn: "), document.createTextNode("not yet"));
    }
    box.append(line);
  }
}

function renderSeats() {
  for (const where of ["top", "left", "right"]) {
    const spot = document.querySelector(`.spot.${where}`);
    spot.classList.add("empty");
    spot.querySelector(".plate").replaceChildren();
    spot.querySelector(".zone").replaceChildren();
  }
  const animate = state.status === "playing" && dealtRound !== state.round.number;
  state.players.forEach((p) => {
    const where = whereIs(p.seat);
    if (where === "bottom") return;
    const spot = document.querySelector(`.spot.${where}`);
    spot.classList.remove("empty");
    spot.style.setProperty("--seat-color", SEAT_COLORS[p.seat % 4]);
    const plate = spot.querySelector(".plate");
    plateContent(plate, p);
    const backs = el("div", "backs");
    const shown = Math.min(p.cards, 12);
    for (let i = 0; i < shown; i++) {
      const b = backEl();
      const spread = Math.min(7, 60 / Math.max(shown, 1));
      b.style.rotate = `${(i - (shown - 1) / 2) * spread}deg`;    // held in a fan
      if (animate) {
        b.classList.add("dealing");
        b.style.animationDelay = `${i * 60}ms`;
      }
      backs.append(b);
    }
    const hold = el("div", "holding");
    hold.append(backs, el("span", "count", `${p.cards} card${p.cards === 1 ? "" : "s"} in hand`));
    plate.append(hold);
  });
}

// Each player's laid-down groups sit on the felt in front of their own seat.
function renderZones() {
  const targetsFor = currentTargets();
  state.players.forEach((p) => {
    const where = whereIs(p.seat);
    const zone = document.querySelector(`.spot.${where} .zone`);
    zone.replaceChildren();
    zone.style.setProperty("--seat-color", SEAT_COLORS[p.seat % 4]);
    const mine = p.seat === state.you;
    zone.append(el("div", "zone-title", mine ? "Your cards on the table" : `${p.name}'s cards on the table`));
    const groups = state.table.filter((m) => m.owner === p.seat);
    if (!groups.length) {
      zone.append(el("div", "zone-empty", p.laid ? "" : (mine ? "Nothing laid down yet" : "Nothing laid down yet")));
      return;
    }
    const row = el("div", "zone-groups");
    for (const m of groups) row.append(meldEl(m, targetsFor));
    zone.append(row);
  });
}

// Which groups the one picked card can go on (from the server), or null.
function currentTargets() {
  if (!(state.can.play_off && selected.size === 1)) return null;
  const id = [...selected][0];
  return new Set(state.targets[String(id)] || []);
}

function meldEl(m, targets) {
  const box = el("div", "meld");
  box.dataset.index = m.index;
  box.style.setProperty("--seat-color", SEAT_COLORS[m.owner % 4]);
  const label = el("div", "meld-label", m.label);
  if (m.wilds) label.append(el("span", "wild-count", ` \u00b7 ${m.wilds} wild${m.wilds > 1 ? "s" : ""}`));
  box.append(label);
  const cards = el("div", "meld-cards");
  let fresh = 0;
  m.cards.forEach((c) => {
    const e = cardEl(c);
    if (c.recent) { e.classList.add("recent"); fresh++; }
    cards.append(e);
  });
  if (fresh) {
    box.classList.add("has-recent");
    label.append(el("span", "recent-tag", fresh === m.cards.length ? " NEW" : ` +${fresh} new`));
  }
  box.append(cards);
  if (targets && targets.has(m.index)) {
    box.classList.add("target");
    box.setAttribute("role", "button");
    box.tabIndex = 0;
    const card = pickedCards()[0];
    const what = `Add ${card ? shortName(card) : "card"} here`;
    box.append(el("div", "target-tag", what));
    box.setAttribute("aria-label", `${what}: ${playerName(m.owner)}'s ${m.label}`);
    const go = async () => {
      const res = await act("play_off", { card: [...selected][0], meld: m.index });
      if (res) { selected.clear(); render(); }
    };
    box.onclick = go;
    box.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } };
  } else if (targets) {
    box.classList.add("no-target");
  }
  return box;
}

function renderCenter() {
  const r = state.round;
  $("goal-round").textContent = `Round ${r.number} goal`;
  // Update 4: a two-part goal can go on two lines ("1 set of 3 &" / "1 run of 10").
  const gt = $("goal-text");
  gt.textContent = "";
  String(r.goal).split(" & ").forEach((part, i, all) => {
    const s = document.createElement("span");
    s.className = "goal-part";
    s.textContent = part + (i < all.length - 1 ? " &" : "");
    gt.append(s, i < all.length - 1 ? " " : "");
  });
  $("goal-sub").textContent = `${r.dealt} cards dealt`;
  $("goal-plaque").title = "Sets: same rank. Runs: same suit, in a row.";
  $("jump-goal").textContent = `Goal: ${r.goal}`;

  const myDraw = state.can.draw;
  const stock = $("stock");
  stock.disabled = !myDraw;
  stock.classList.toggle("clickable", myDraw);
  stock.setAttribute("aria-label", myDraw ? "Draw a card from the pile" : "Draw pile");
  $("stock-count").textContent = myDraw ? `Tap to draw (${state.stock_count} left)` : `Draw pile: ${state.stock_count}`;

  const d = $("discard");
  d.replaceChildren();
  const discardNow = state.can.discard && selected.size === 1;
  let label = "Discard pile";
  if (state.discard_top) {
    const c = cardEl(state.discard_top, "button");
    if (state.can.take_discard) {
      c.classList.add("clickable");
      c.setAttribute("aria-label", `Take ${state.discard_top.name} from the discard pile`);
      c.onclick = () => act("draw", { source: "discard" });
      label = `Tap to take ${shortName(state.discard_top)}`;
    } else if (discardNow) {
      c.classList.add("drop-here");
      c.setAttribute("aria-label", "Discard your picked card here");
      c.onclick = doDiscard;
      label = "Tap to discard here";
    } else {
      c.disabled = true;
      const by = state.discard_top_by;
      if (by !== null && by !== undefined && state.players[by]) {
        label = by === state.you ? "You discarded this" : `${state.players[by].name} discarded this`;
      }
    }
    d.append(c);
  } else {
    const e = el("button", "card empty");
    if (discardNow) { e.classList.add("drop-here"); e.onclick = doDiscard; label = "Tap to discard here"; }
    else e.disabled = true;
    d.append(e);
  }
  $("discard-label").textContent = label;

  // Whose turn, and the three steps of a turn.
  const banner = $("turn-banner");
  banner.classList.remove("mine");
  const steps = $("steps");
  steps.querySelectorAll("li").forEach((li) => li.classList.remove("now", "done"));
  if (state.status !== "playing") {
    banner.textContent = state.status === "game_over" ? "Game over" : "Round over";
    steps.classList.add("hidden");
    return;
  }
  steps.classList.remove("hidden");
  const cur = state.players[state.current];
  const stepNow = state.phase === "draw" ? "draw" : "play";
  steps.querySelector(`[data-step="${stepNow}"]`).classList.add("now");
  if (stepNow === "play") {
    steps.querySelector('[data-step="draw"]').classList.add("done");
    steps.querySelector('[data-step="discard"]').classList.add("now");
  }
  steps.classList.toggle("theirs", cur.seat !== state.you);
  if (cur.seat === state.you) {
    banner.textContent = state.phase === "draw" ? "Your turn: draw a card" : "Your turn: play, then discard one card";
    banner.classList.add("mine");
  } else {
    banner.textContent = `${ARROWS[whereIs(cur.seat)]} ${cur.name}'s turn` +
      (state.phase === "draw" ? " (drawing)" : " (playing)");
  }
}

function statusText() {
  const me = state.players[state.you];
  if (state.status === "round_over") return "This round is over. Tap here for the scores and the next deal.";
  if (state.status === "game_over") return "The game is over. Tap here for the final scores.";
  if (!me.turn) {
    const cur = state.players[state.current];
    const moves = (cur && cur.moves) || [];
    return moves.length
      ? `${cur.name} so far this turn: ${moves.join(" \u2192 ")}.`
      : `Waiting for ${playerName(state.current)}. You can sort and group your hand while you wait.`;
  }
  if (state.phase === "draw") {
    return state.can.take_discard
      ? `Step 1: draw. Tap the draw pile, or tap the ${shortName(state.discard_top)} on the discard pile to take it.`
      : "Step 1: draw. Tap the draw pile.";
  }
  const n = selected.size;
  const last = state.hand.length === 1;
  if (last) return "One card left: pick it and tap Discard to go out.";
  if (!state.laid) {
    if (n === 0) return `Step 2: if you hold the whole goal (${state.round.goal}), pick those cards and tap Lay down. ` +
      "Not there yet? Pick one card to discard.";
    if (n === 1) return `You picked ${shortName(pickedCards()[0])}. Tap Discard to end your turn, or pick more cards to lay down your goal.`;
    return `${n} cards picked. Tap "Lay down my goal" when you've picked every card for it.`;
  }
  if (n === 0) return "Step 2: pick a card to add to any glowing group, pick 3 or more for a new group, or pick one card to discard.";
  if (n === 1) {
    const t = currentTargets();
    const c = shortName(pickedCards()[0]);
    return t && t.size
      ? `You picked ${c}. Tap a glowing group to add it there, or tap Discard to end your turn.`
      : `You picked ${c}. It doesn't fit on any group on the table. Tap Discard to end your turn with it.`;
  }
  return `${n} cards picked. Tap "Put down as a new group" to lay them down as another set or run.`;
}

function renderMe() {
  const me = state.players[state.you];
  plateContent($("me-head"), me);
  $("me-head").append(el("span", "count", `${state.hand.length} card${state.hand.length === 1 ? "" : "s"} in your hand`));
  $("rack").classList.toggle("is-turn", me.turn);
  $("rack").style.setProperty("--seat-color", SEAT_COLORS[me.seat % 4]);
  $("status").textContent = statusText();
  $("status").classList.toggle("clickable", state.status === "round_over" || state.status === "game_over");

  renderHand();
  renderActions();
  $("sort-btn").textContent = sortMode === "suit" ? "Sort by rank" : "Sort by suit";
  $("clear-btn").disabled = selected.size === 0;
  renderGroupButtons();
  updateJump();
}

// The buttons under the hand say exactly what they will do.
function renderActions() {
  const box = $("actions");
  box.replaceChildren();
  const btn = (text, cls, onclick, disabled = false) => {
    const b = el("button", cls, text);
    b.onclick = onclick;
    b.disabled = disabled;
    box.append(b);
    return b;
  };
  const me = state.players[state.you];
  if (state.status !== "playing") return;
  if (!me.turn) {
    box.append(el("span", "wait-note", `${playerName(state.current)} is playing. Your buttons come back on your turn.`));
    return;
  }
  if (state.phase === "draw") {
    btn("Draw from the pile", "primary", () => act("draw", { source: "stock" }));
    if (state.can.take_discard) btn(`Take the ${shortName(state.discard_top)} from the discard pile`, "secondary",
      () => act("draw", { source: "discard" }));
    return;
  }
  const picked = pickedCards();
  const n = picked.length;
  if (!state.laid) {
    const need = goalSize();
    btn(n >= need ? `Lay down my goal (${n} cards picked)` : `Lay down my goal (pick at least ${need} cards)`,
      n >= need ? "primary" : "secondary", doLayDown, n < need);
    btn("Find my goal for me", "secondary", doSuggest);
  } else {
    const min = state.new_group_min.set;
    btn(n >= min ? `Put down as a new group (${n} cards)` : `New group (pick ${min} or more cards)`,
      n >= min ? "primary" : "secondary", doNewGroup, n < min);
  }
  const goOut = state.hand.length === 1;
  const discardText = n === 1
    ? `Discard ${shortName(picked[0])} and ${goOut ? "go out" : "end my turn"}`
    : n === 0 ? "Discard (pick one card first)" : `Discard (pick just one card, you have ${n})`;
  btn(discardText, n === 1 ? "discard-btn ready" : "discard-btn", doDiscard, false);
}

async function doDiscard() {
  if (selected.size !== 1) {
    toast(selected.size === 0
      ? "First tap the one card you want to throw away."
      : `You have ${selected.size} cards picked. Tap "Clear picked cards", then tap just the one card to throw away.`, true);
    return;
  }
  const id = [...selected][0];
  const ok = await act("discard", { card: id });
  if (ok) selected.clear();
  render();
}

async function doLayDown() {
  const res = await act("lay_down", { cards: [...selected] });
  if (res) {
    selected.clear();
    toast("Your goal is down. Now you can add cards to any group and put down new groups.");
    render();
  }
}

async function doSuggest() {
  const res = await act("suggest");
  if (!res) return;
  if (!res.groups) {
    toast(`You don't have every card for this round's goal (${state.round.goal}) yet.`, true);
    return;
  }
  selected = new Set(res.groups.flat());
  toast("I picked the cards for your goal. Check them, then tap Lay down my goal.");
  render();
}

async function doNewGroup() {
  const res = await act("new_group", { cards: [...selected] });
  if (res) { selected.clear(); render(); }
}

function renderScores() {
  const players = state.players;
  const table = $("score-table");
  const head = el("tr");
  head.append(el("th", "", "Rnd"), ...players.map((p) => el("th", "", p.name)));
  const rows = [head];
  for (let r = 1; r <= state.round.last; r++) {
    const played = players.some((p) => p.rounds[String(r)] !== undefined);
    if (!played && r !== state.round.number) continue;
    const tr = el("tr", r === state.round.number && state.status === "playing" ? "now" : "");
    tr.append(el("td", "", String(r)));
    for (const p of players) {
      const v = p.rounds[String(r)];
      tr.append(el("td", "", v === undefined ? "\u2026" : v === null ? "stopped" : String(v)));
    }
    rows.push(tr);
  }
  const total = el("tr", "total");
  total.append(el("td", "", "Total"), ...players.map((p) => el("td", "", String(p.total))));
  rows.push(total);
  table.replaceChildren(...rows);
  $("log").replaceChildren(...[...state.log].reverse().map((line) => el("li", "", line)));
}

function renderModal() {
  const over = state.status === "round_over" || state.status === "game_over";
  const lr = state.last_round;
  if (!over || !lr || modalDismissed === state.version) {
    $("modal").classList.add("hidden");
    return;
  }
  $("modal").classList.remove("hidden");
  const players = state.players;
  if (state.status === "game_over") {
    const low = Math.min(...players.map((p) => p.total));
    const winners = players.filter((p) => p.total === low).map((p) => p.name);
    $("m-title").textContent = `Game over: ${winners.join(" and ")} win${winners.length > 1 ? "" : "s"}!`;
  } else {
    $("m-title").textContent = lr.winner === null
      ? `Round ${lr.round} was stopped`
      : `${playerName(lr.winner)} went out in round ${lr.round}`;
  }
  $("m-note").textContent = lr.note || "Points are the cards left in each hand. Lowest total wins.";
  const head = el("tr");
  head.append(el("th", "", "Player"), el("th", "", "This round"), el("th", "", "Total"));
  const rows = [head, ...players.map((p) => {
    const tr = el("tr");
    const pts = lr.points[String(p.seat)];
    tr.append(el("td", "", p.name), el("td", "", pts === undefined ? "-" : String(pts)), el("td", "", String(p.total)));
    return tr;
  })];
  $("m-table").replaceChildren(...rows);
  $("next-btn").classList.toggle("hidden", !state.can.next_round);
  $("next-btn").textContent = `Deal round ${state.round.number + 1}`;
}

// ------------------------------------------------------------ your card holder (fourth and fifth editions)
// Fifth edition: your hand stands in a card holder with two rows, a top row
// and a bottom row, like a rack on the edge of the table.  The deal and every
// card you draw land in the bottom row.  You can move cards up to the top row
// and back down, and put them in any order you like.  Either row can hold
// groups (fourth edition) to plan your sets and runs.
// Only this browser knows how you arranged your holder: nothing about it is
// ever sent to the table, so other players never see it, and it doesn't
// change what you may play.
//
// Moving cards:
//   * Mouse: drag a card onto another card, onto a group, onto the other row,
//     or onto "Drop here for a new group".  Drag a picked card to move all
//     your picked cards.  Drag a group by its name to move the whole group.
//   * Phone or tablet: press and hold a card (or a group's name) for a
//     moment, then drag it.
//   * Or, without dragging: pick cards, then tap "Up a row" / "Down a row",
//     "Make a group", or "Move here" on a group.  With one card picked, the
//     arrow buttons move it left or right.
//   * Laying down: drag your picked cards up onto your place on the felt (in
//     front of your holder), drag one card onto a glowing group to add it,
//     or drag it onto the discard pile.  The buttons still do the same.
const PLAN_PREFIX = "progressive-rummy-plan:";
var lanOrigin;            // the computer's Wi-Fi address, asked once (see renderWaiting)
let plan = null;          // { key, round, groups: [{ id, ids, row }], top: [ids], loose: [ids], next }
let drag = null;          // a card drag in progress
let renderLater = false;  // a table update arrived during a drag
let suppressClick = 0;    // time until which a card tap is ignored (it was a drag)
const ROWS = ["top", "bottom"];
const ROW_NAME = { top: "top row", bottom: "bottom row" };

function planKey() { return session ? `${PLAN_PREFIX}${session.code}:${session.token}` : ""; }

function cardCmp(a, b) {
  const rankKey = (c) => (c.wild ? 100 + c.rank : c.rank);
  const suitKey = (c) => (c.wild ? 9 : SUIT_ORDER[c.suit]);
  return sortMode === "suit"
    ? suitKey(a) - suitKey(b) || rankKey(a) - rankKey(b) || a.id - b.id
    : rankKey(a) - rankKey(b) || suitKey(a) - suitKey(b) || a.id - b.id;
}

function handById() { return new Map(state.hand.map((c) => [c.id, c])); }

function insertSorted(list, card, byId) {
  let i = list.findIndex((id) => byId.has(id) && cardCmp(byId.get(id), card) > 0);
  if (i < 0) i = list.length;
  list.splice(i, 0, card.id);
}

// The loose cards of a row: "top" for the top row, "loose" for the bottom row.
function looseArea(row) { return row === "top" ? "top" : "loose"; }
function rowGroups(row) { return plan.groups.filter((g) => g.row === row); }
function rowOfArea(areaId) {
  if (areaId === "top") return "top";
  if (areaId === "loose") return "bottom";
  const g = plan.groups.find((q) => q.id === areaId);
  return g ? g.row : "bottom";
}

// Keep the holder in step with the cards really in your hand: cards you
// played or threw away leave it, a card you drew joins the bottom row in its
// sorted place, and a new deal starts with everything in the bottom row.
function syncPlan() {
  const key = planKey();
  const round = state.round.number;
  if (!plan || plan.key !== key) {
    try { plan = JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { plan = null; }
    if (plan) plan.key = key;
  }
  if (!plan || plan.round !== round || !Array.isArray(plan.groups) || !Array.isArray(plan.loose)) {
    // Clear holders saved for earlier tables, so they don't pile up.
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith(PLAN_PREFIX) && k !== key) localStorage.removeItem(k);
    }
    plan = { key, round, groups: [], top: [], loose: [], next: 1 };
  }
  if (!Array.isArray(plan.top)) plan.top = [];
  const byId = handById();
  const seen = new Set();
  const keep = (ids) => ids.filter((id) => byId.has(id) && !seen.has(id) && (seen.add(id), true));
  plan.groups = plan.groups
    .map((g) => ({ id: g.id, ids: keep(g.ids || []), row: g.row === "top" ? "top" : "bottom" }))
    .filter((g) => g.ids.length);
  plan.top = keep(plan.top);
  plan.loose = keep(plan.loose);
  for (const c of sortHand(state.hand)) if (!seen.has(c.id)) insertSorted(plan.loose, c, byId);
  savePlan();
}

function savePlan() {
  try { localStorage.setItem(plan.key, JSON.stringify(plan)); } catch (e) { /* private mode: the holder lasts until the page reloads */ }
}

function areaIds(areaId) {
  if (areaId === "loose") return plan.loose;
  if (areaId === "top") return plan.top;
  const g = plan.groups.find((q) => q.id === areaId);
  return g ? g.ids : null;
}

function areaOf(id) {
  for (const g of plan.groups) if (g.ids.includes(id)) return g.id;
  if (plan.top.includes(id)) return "top";
  return "loose";
}

// Every card id in the order you see them: the top row (its groups, then its
// loose cards), then the bottom row the same way.
function displayOrder() {
  const out = [];
  for (const row of ROWS) {
    for (const g of rowGroups(row)) out.push(...g.ids);
    out.push(...areaIds(looseArea(row)));
  }
  return out;
}

// Move cards to an area ("loose", "top", a group id, or a new group:
// "new-top", "new-bottom"), before one
// card or at the end.  ("new" = a new group in the row of the first card.)
function moveCards(ids, target, beforeId = null) {
  const moving = displayOrder().filter((id) => ids.includes(id));
  if (!moving.length) return;
  if (beforeId !== null && moving.includes(beforeId)) {
    // dropped on itself: put the cards before the next card that isn't moving
    const list = areaIds(areaOf(beforeId));
    const at = list.indexOf(beforeId);
    beforeId = list.slice(at).find((id) => !moving.includes(id)) ?? null;
  }
  // "Make a group" keeps the new group in the row its first card was in.
  const homeRow = rowOfArea(areaOf(moving[0]));
  for (const g of plan.groups) g.ids = g.ids.filter((id) => !moving.includes(id));
  plan.top = plan.top.filter((id) => !moving.includes(id));
  plan.loose = plan.loose.filter((id) => !moving.includes(id));
  let list;
  if (target === "new" || target === "new-top" || target === "new-bottom") {
    const g = { id: `g${plan.next++}`, ids: [], row: target === "new" ? homeRow : target === "new-top" ? "top" : "bottom" };
    plan.groups.push(g);
    list = g.ids;
  } else {
    list = areaIds(target) || plan.loose;
  }
  let at = beforeId === null ? -1 : list.indexOf(beforeId);
  if (at < 0) at = list.length;
  list.splice(at, 0, ...moving);
  plan.groups = plan.groups.filter((g) => g.ids.length);
  savePlan();
  localStorage.setItem("progressive-rummy-grouped", "1");
}

// Move a whole group to a row, keeping it a group (it goes to the end of that row's groups).
function moveGroupToRow(gid, row) {
  const g = plan.groups.find((q) => q.id === gid);
  if (!g) return;
  plan.groups = plan.groups.filter((q) => q !== g);
  g.row = row;
  plan.groups.push(g);
  savePlan();
}

// Picked cards up or down a row.  Cards already in that row stay where they are.
function moveToRow(ids, row) {
  const going = ids.filter((id) => rowOfArea(areaOf(id)) !== row);
  if (!going.length) return;
  if (row === "top") moveUpSeparate(going);
  else moveCards(going, looseArea(row));
}

// Update 3 (Tom's note): cards moved up to a top row that already holds
// cards used to join the cards already there, so a run you had set up got
// mixed with the new cards and you had to slide them apart by hand.  Now the
// cards already in the top row keep together as their own group, and the cards
// coming up start a new group of their own beside it.  (The first cards moved
// up to an empty top row simply stand there, as before.  Dropping a card on a
// particular card still puts it right there.)
function moveUpSeparate(ids) {
  if (!ids.length) return;
  const topHasCards = plan.top.length > 0 || rowGroups("top").length > 0;
  if (!topHasCards) { moveCards(ids, "top"); return; }
  if (plan.top.length) {
    const keep = plan.top.filter((id) => !ids.includes(id));
    if (keep.length) plan.groups.push({ id: `g${plan.next++}`, ids: keep, row: "top" });
    plan.top = plan.top.filter((id) => ids.includes(id));
  }
  moveCards(ids, "new-top");
}

function breakUpGroup(gid) {
  const g = plan.groups.find((q) => q.id === gid);
  if (!g) return;
  const byId = handById();
  plan.groups = plan.groups.filter((q) => q.id !== gid);
  const list = areaIds(looseArea(g.row));
  for (const id of g.ids) if (byId.has(id)) insertSorted(list, byId.get(id), byId);
  savePlan();
}

// Every group is broken up; each card stays in the row it was in.
function breakUpAll() {
  for (const g of [...plan.groups]) breakUpGroup(g.id);
}

function nudge(id, dir) {
  const list = areaIds(areaOf(id));
  const i = list.indexOf(id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= list.length) return;
  [list[i], list[j]] = [list[j], list[i]];
  savePlan();
}

// The sort button sorts the cards inside each group and the loose cards of
// each row; your groups and rows stay as they are.
function sortAllAreas() {
  const byId = handById();
  const srt = (ids) => ids.filter((id) => byId.has(id)).sort((a, b) => cardCmp(byId.get(a), byId.get(b)));
  for (const g of plan.groups) g.ids = srt(g.ids);
  plan.top = srt(plan.top);
  plan.loose = srt(plan.loose);
  savePlan();
}

function handCardEl(c, i, animate, targets) {
  const e = cardEl(c, "button");
  e.dataset.id = c.id;
  if (selected.has(c.id)) e.classList.add("selected");
  if (c.id === freshCard) { e.classList.add("fresh"); e.append(el("span", "new-tag", "NEW")); }
  if (selected.size === 0 && targets[String(c.id)]) e.classList.add("fits");
  if (animate) {
    e.classList.add("dealing");
    e.style.animationDelay = `${i * 45}ms`;
  }
  e.setAttribute("aria-pressed", selected.has(c.id) ? "true" : "false");
  e.onclick = () => {
    if (Date.now() < suppressClick) return;
    if (selected.has(c.id)) selected.delete(c.id); else selected.add(c.id);
    render();
  };
  e.addEventListener("pointerdown", onCardPointerDown);
  e.addEventListener("touchstart", onCardTouchStart, { passive: true });
  e.addEventListener("contextmenu", (ev) => ev.preventDefault());
  return e;
}

function renderHand() {
  syncPlan();
  const animate = state.status === "playing" && dealtRound !== state.round.number;
  const targets = state.can.play_off ? state.targets : {};
  const byId = handById();
  const hand = $("hand");
  hand.replaceChildren();
  hand.classList.toggle("has-groups", plan.groups.length > 0);
  const topUsed = plan.top.length > 0 || rowGroups("top").length > 0;
  hand.classList.toggle("top-used", topUsed);
  const picked = [...selected];
  let i = 0;
  let n = 0;
  const area = (into, areaId, ids, title, grouped, row) => {
    const isLoose = areaId === "loose" || areaId === "top";
    const box = el("div", "hand-group" + (isLoose ? " loose" : "") + (grouped ? "" : " plain"));
    box.dataset.area = areaId;
    if (grouped) {
      const head = el("div", "hg-head");
      const name = el("span", "hg-name", `${title} \u00b7 ${ids.length} card${ids.length === 1 ? "" : "s"}`);
      head.append(name);
      const outside = picked.filter((id) => !ids.includes(id));
      if (outside.length) {
        const mv = el("button", "hg-btn move", `Move ${outside.length} here`);
        mv.setAttribute("aria-label", `Move ${outside.length} picked card${outside.length === 1 ? "" : "s"} to ${title}`);
        mv.onclick = () => { moveCards(outside, areaId); render(); };
        head.append(mv);
      }
      if (!isLoose) {
        name.classList.add("handle");
        name.dataset.group = areaId;
        name.title = "Drag the name to move the whole group";
        name.addEventListener("pointerdown", onCardPointerDown);
        name.addEventListener("touchstart", onCardTouchStart, { passive: true });
        const allPicked = ids.every((id) => selected.has(id));
        const pk = el("button", "hg-btn pick", allPicked ? "Unpick" : "Pick these");
        pk.setAttribute("aria-label", `${allPicked ? "Unpick" : "Pick"} the cards in ${title}`);
        pk.onclick = () => {
          for (const id of ids) { if (allPicked) selected.delete(id); else selected.add(id); }
          render();
        };
        const other = row === "top" ? "bottom" : "top";
        const ud = el("button", "hg-btn row-move", row === "top" ? "\u25bc" : "\u25b2");
        ud.title = `Move ${title} to the ${ROW_NAME[other]}`;
        ud.setAttribute("aria-label", ud.title);
        ud.onclick = () => { moveGroupToRow(areaId, other); render(); };
        const x = el("button", "hg-btn undo", "\u2715");
        x.title = `Break up ${title} (its cards stay loose in the same row)`;
        x.setAttribute("aria-label", `Break up ${title}`);
        x.onclick = () => { breakUpGroup(areaId); render(); };
        head.append(pk, ud, x);
      }
      box.append(head);
    }
    const cards = el("div", "hg-cards");
    for (const id of ids) cards.append(handCardEl(byId.get(id), i++, animate, targets));
    if (!ids.length) cards.append(el("span", "hg-empty", "No loose cards"));
    box.append(cards);
    into.append(box);
  };
  for (const row of ROWS) {
    const shelf = el("div", `shelf shelf-${row}`);
    shelf.dataset.row = row;
    shelf.dataset.area = looseArea(row);
    shelf.append(el("div", "shelf-label", row === "top" ? "Top row" : "Bottom row"));
    const slot = el("div", "shelf-cards");
    const groups = rowGroups(row);
    const grouped = groups.length > 0;
    for (const g of groups) area(slot, g.id, g.ids, `Group ${++n}`, true, row);
    const looseIds = areaIds(looseArea(row));
    if (looseIds.length) {
      area(slot, looseArea(row), looseIds, "Not grouped", grouped, row);
    } else if (!grouped) {
      shelf.classList.add("is-empty");
      const hint = el("div", "hand-group plain shelf-empty");
      hint.dataset.area = looseArea(row);
      hint.textContent = row === "top"
        ? (state.hand.length ? "Top row: drag cards up here, or pick cards and tap \u25b2 Up a row" : "Top row")
        : (state.hand.length ? "Bottom row is empty" : "No cards in your hand");
      slot.append(hint);
    }
    shelf.append(slot, el("div", "shelf-ledge"));
    hand.append(shelf);
  }
}

// The buttons for arranging your holder, next to Sort and Clear.
function renderGroupButtons() {
  const n = selected.size;
  const mk = $("group-btn");
  mk.textContent = n ? `Make a group of ${n}` : "Make a group";
  mk.disabled = n === 0;
  const one = n === 1 ? [...selected][0] : null;
  let canL = false, canR = false;
  if (one !== null) {
    const list = areaIds(areaOf(one));
    const at = list.indexOf(one);
    canL = at > 0;
    canR = at >= 0 && at < list.length - 1;
  }
  $("left-btn").classList.toggle("hidden", one === null);
  $("right-btn").classList.toggle("hidden", one === null);
  $("left-btn").disabled = !canL;
  $("right-btn").disabled = !canR;
  const ids = [...selected];
  const anyBottom = ids.some((id) => rowOfArea(areaOf(id)) === "bottom");
  const anyTop = ids.some((id) => rowOfArea(areaOf(id)) === "top");
  $("up-btn").disabled = !anyBottom;
  $("down-btn").disabled = !anyTop;
  $("up-btn").textContent = n && anyBottom ? `\u25b2 Up a row (${ids.filter((id) => rowOfArea(areaOf(id)) === "bottom").length})` : "\u25b2 Up a row";
  $("down-btn").textContent = n && anyTop ? `\u25bc Down a row (${ids.filter((id) => rowOfArea(areaOf(id)) === "top").length})` : "\u25bc Down a row";
  $("ungroup-btn").classList.toggle("hidden", plan.groups.length === 0);
  if (!localStorage.getItem("progressive-rummy-holder-tip") && state.status === "playing") {
    localStorage.setItem("progressive-rummy-holder-tip", "1");
    localStorage.setItem("progressive-rummy-group-tip", "1");
    setTimeout(() => toast("New: your cards stand in a holder with two rows. Drag a card up to the top row " +
      "(on a phone, press and hold it first), or pick cards and tap \u25b2 Up a row. Only you see how you arrange them."), 1500);
  }
}

// ---------- dragging cards (mouse, or press-and-hold on a touch screen)
function dragStartInfo(target, x, y) {
  const group = target.dataset.group || null;
  let id = Number(target.dataset.id);
  if (group) {
    const ids = areaIds(group);
    if (!ids || !ids.length) return null;
    id = ids[0];
  }
  return { id, group, x0: x, y0: y, started: false, source: target };
}

function onCardPointerDown(ev) {
  if (ev.pointerType === "touch" || ev.button !== 0) return;
  const d = dragStartInfo(ev.currentTarget, ev.clientX, ev.clientY);
  if (!d) return;
  d.pointer = ev.pointerId;
  drag = d;
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerCancel);
}

function onPointerMove(ev) {
  if (!drag || ev.pointerId !== drag.pointer) return;
  if (!drag.started) {
    if (Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < 8) return;
    startDrag();
  }
  moveDrag(ev.clientX, ev.clientY);
  ev.preventDefault();
}

function onPointerUp(ev) {
  if (!drag || ev.pointerId !== drag.pointer) return;
  const wasDrag = drag.started;
  endPointerListeners();
  if (wasDrag) { suppressClick = Date.now() + 80; finishDrag(ev.clientX, ev.clientY); }
  else drag = null;
}

function onPointerCancel() { endPointerListeners(); cancelDrag(); }

function endPointerListeners() {
  window.removeEventListener("pointermove", onPointerMove);
  window.removeEventListener("pointerup", onPointerUp);
  window.removeEventListener("pointercancel", onPointerCancel);
}

const HOLD_MS = 300;
function onCardTouchStart(ev) {
  if (ev.touches.length !== 1) return;
  const t = ev.touches[0];
  const d = dragStartInfo(ev.currentTarget, t.clientX, t.clientY);
  if (!d) return;
  Object.assign(d, { x: t.clientX, y: t.clientY, touch: true });
  d.timer = setTimeout(() => {
    if (drag !== d) return;
    startDrag();
    moveDrag(d.x, d.y);
    if (navigator.vibrate) { try { navigator.vibrate(15); } catch (e) { /* not on every phone */ } }
  }, HOLD_MS);
  drag = d;
}

// Touch moves are watched on the whole page and not "passive", so that once
// a card is being dragged the page doesn't scroll under your finger.
document.addEventListener("touchmove", (ev) => {
  if (!drag || !drag.touch) return;
  const t = ev.touches[0];
  drag.x = t.clientX; drag.y = t.clientY;
  if (!drag.started) {
    if (Math.hypot(t.clientX - drag.x0, t.clientY - drag.y0) > 10) { clearTimeout(drag.timer); drag = null; }
    return;
  }
  ev.preventDefault();
  moveDrag(t.clientX, t.clientY);
}, { passive: false });

document.addEventListener("touchend", (ev) => {
  if (!drag || !drag.touch) return;
  clearTimeout(drag.timer);
  if (drag.started) {
    ev.preventDefault();               // no tap on the card after a drag
    suppressClick = Date.now() + 300;
    finishDrag(drag.x, drag.y);
  } else {
    drag = null;
  }
}, { passive: false });

document.addEventListener("touchcancel", () => { if (drag && drag.touch) { clearTimeout(drag.timer); cancelDrag(); } });

function startDrag() {
  drag.started = true;
  if (drag.group) drag.ids = [...areaIds(drag.group)];
  else drag.ids = selected.has(drag.id) ? displayOrder().filter((id) => selected.has(id)) : [drag.id];
  const hand = $("hand");
  hand.classList.add("dragging-on");
  for (const id of drag.ids) {
    const c = hand.querySelector(`.card[data-id="${id}"]`);
    if (c) c.classList.add("drag-from");
  }
  const ghost = el("div", "drag-ghost");
  const first = hand.querySelector(`.card[data-id="${drag.ids[0]}"]`) || drag.source;
  const src = first.cloneNode(true);
  src.classList.remove("selected", "dealing", "drag-from");
  ghost.append(src);
  if (drag.ids.length > 1) ghost.append(el("span", "drag-count", `${drag.ids.length} cards`));
  document.body.append(ghost);
  drag.ghost = ghost;
  // A "new group" spot in the row the cards come from.  (Only one, so the
  // rows don't grow and move under your finger while you drag.)
  for (const row of [rowOfArea(areaOf(drag.ids[0]))]) {
    const drop = el("div", "hand-group new-group-drop", "Drop here for a new group");
    drop.dataset.area = `new-${row}`;
    const slot = hand.querySelector(`.shelf-${row} .shelf-cards`);
    if (!slot) continue;
    // Update 1: the holder hugs your cards in the middle of the rack.  While
    // you drag, hold it exactly where it is, and if the row has no room left
    // for the drop spot, stretch the holder to the right only, so no card
    // moves under your finger.
    const z = zoomOf(hand) || 1;
    const sh = slot.closest(".shelf");
    // Update 4: on a computer the holder sits in the middle column of the
    // rack, with the round's goal to its left.  While you drag, pin the
    // columns where they are and let the holder reach to the right edge, so
    // there is room at the end of a row and nothing moves under your finger.
    const sr = sh.getBoundingClientRect();
    const last = slot.lastElementChild;
    const free = last ? (sr.right - last.getBoundingClientRect().right) / z : 9999;
    freezeRackColumns(hand);
    const hr = hand.getBoundingClientRect();
    const roomRight = (hr.right - sr.right) / z;
    const extra = free >= 100 ? 0 : Math.max(0, Math.min(roomRight - 2, 110 - free));
    hand.style.justifyContent = "start";
    hand.style.paddingLeft = `${Math.max(0, (sr.left - hr.left) / z)}px`;
    // (+2: a hair of room, so rounding can't push the last card to a new line)
    hand.style.gridTemplateColumns = `min(100%, ${Math.ceil(sr.width / z) + 2 + Math.floor(extra)}px)`;
    const lead = slot.firstElementChild;
    slot.append(drop);
    // Still no room at the end of the row on a computer: the spot floats at
    // the row's right end.  (On a phone it goes on a new line, as before.)
    if (lead && drop.offsetTop > lead.offsetTop + 4 && matchMedia("(min-width: 761px)").matches) drop.classList.add("floating");
  }
  // Update 3: dragging cards up from the bottom row while the top row already
  // has cards in it.  The holder hugs your cards, so the top row has no empty
  // part to drop on, and a drop landed in the group already there.  Now a
  // "New group" spot sits at the right end of the top row, over the row, so
  // nothing moves under your finger; cards dropped there start their own group.
  // (Dropping on the empty part of the top row, when there is one, does the same.)
  const topSlot = hand.querySelector(".shelf-top .shelf-cards");
  if (rowOfArea(areaOf(drag.ids[0])) === "bottom" && topSlot && topSlot.querySelector(".card")) {
    const up = el("div", "hand-group new-group-drop floating up-top", "New group");
    up.dataset.area = "new-top";
    topSlot.closest(".shelf").append(up);
  }
  markTableTargets();
}

// Fifth edition: while you drag cards on your turn, the places on the table
// they can go glow: your own place on the felt (to lay down), a group a
// single card fits on, and the discard pile.
function markTableTargets() {
  if (!state || state.status !== "playing") return;
  const ids = drag.ids;
  const zone = document.querySelector(".spot.bottom .zone");
  if (zone && (state.can.lay_down || (state.can.new_group && ids.length >= state.new_group_min.set))) {
    zone.classList.add("drag-target");
    zone.dataset.hint = state.can.lay_down ? "Drop here to lay down your goal" : "Drop here to put these down as a new group";
  }
  if (ids.length === 1 && state.can.play_off) {
    const fits = new Set(state.targets[String(ids[0])] || []);
    document.querySelectorAll(".meld[data-index]").forEach((m) => {
      if (fits.has(Number(m.dataset.index))) m.classList.add("drag-target");
    });
  }
  if (ids.length === 1 && state.can.discard) {
    const d = $("discard").firstElementChild;
    if (d) d.classList.add("drag-target");
  }
  document.body.classList.add("dragging-cards");
}

function clearTableTargets() {
  document.querySelectorAll(".drag-target, .drag-over").forEach((e) => e.classList.remove("drag-target", "drag-over"));
  document.body.classList.remove("dragging-cards");
}

function dropSpot(x, y) {
  const under = document.elementFromPoint(x, y);
  if (!under) return null;
  const card = under.closest("#hand .card");
  if (card) {
    const r = card.getBoundingClientRect();
    const box = card.closest(".hand-group");
    const next = card.nextElementSibling;
    // Cards overlap, so only the left part of a card shows: split that part.
    const shown = next && next.classList.contains("card") ? next.getBoundingClientRect().left - r.left : r.width;
    const before = x < r.left + shown / 2;
    const id = Number(card.dataset.id);
    let beforeId = id;
    if (!before) beforeId = next && next.classList.contains("card") ? Number(next.dataset.id) : null;
    return { area: box.dataset.area, beforeId, card, before };
  }
  const box = under.closest("#hand .hand-group");
  if (box) return { area: box.dataset.area, beforeId: null, box };
  const shelf = under.closest("#hand .shelf");
  if (shelf) return { area: shelf.dataset.area, beforeId: null, box: shelf, row: shelf.dataset.row };
  const meld = under.closest(".meld.drag-target");
  if (meld) return { table: "meld", meld: Number(meld.dataset.index), box: meld };
  const zone = under.closest(".zone.drag-target");
  if (zone) return { table: "lay", box: zone };
  const pile = under.closest("#discard .drag-target");
  if (pile) return { table: "discard", box: pile };
  return null;
}

function moveDrag(x, y) {
  if (!drag || !drag.ghost) return;
  drag.ghost.style.left = `${x}px`;
  drag.ghost.style.top = `${y}px`;
  document.querySelectorAll("#hand .drop-before, #hand .drop-after, #hand .drop-into, .drag-over")
    .forEach((e) => e.classList.remove("drop-before", "drop-after", "drop-into", "drag-over"));
  const spot = dropSpot(x, y);
  if (!spot) return;
  if (spot.table) spot.box.classList.add("drag-over");
  else if (spot.card) spot.card.classList.add(spot.before ? "drop-before" : "drop-after");
  else spot.box.classList.add("drop-into");
}

async function finishDrag(x, y) {
  const spot = dropSpot(x, y);
  const ids = drag.ids;
  const group = drag.group;
  cleanupDrag();
  if (spot && spot.table && ids.length) {
    if (spot.table === "meld") {
      const res = await act("play_off", { card: ids[0], meld: spot.meld });
      if (res) selected.clear();
    } else if (spot.table === "lay") {
      selected = new Set(ids);
      if (state.can.lay_down) await doLayDown(); else await doNewGroup();
    } else if (spot.table === "discard") {
      selected = new Set(ids);
      await doDiscard();
    }
    render();
    return;
  }
  if (spot && ids.length) {
    const area = spot.area;
    const shelfDrop = area === "top" || area === "loose" || (area && area.startsWith("new-"));
    if (group && shelfDrop && !spot.card) {
      // A whole group dropped on a row: it moves there and stays a group.
      moveGroupToRow(group, area === "top" || area === "new-top" ? "top" : "bottom");
    } else if (area === "new-top" && ids.every((id) => rowOfArea(areaOf(id)) === "bottom")) {
      moveUpSeparate(ids);   // update 3: beside what's already in the top row
    } else if (area && area.startsWith("new")) {
      moveCards(ids, area);
    } else if (area === "top" && !spot.card && ids.every((id) => rowOfArea(areaOf(id)) === "bottom")) {
      // Cards dragged up from the bottom row onto the top row (not onto a
      // particular card) start their own group, apart from what is there.
      moveUpSeparate(ids);
    } else {
      moveCards(ids, area, spot.beforeId);
    }
  }
  render();
}

function cancelDrag() {
  if (!drag) return;
  const was = drag.started;
  cleanupDrag();
  if (was) render();
}

function cleanupDrag() {
  if (drag && drag.ghost) drag.ghost.remove();
  if (drag) clearTimeout(drag.timer);
  drag = null;
  const hand = $("hand");
  hand.classList.remove("dragging-on");
  hand.querySelectorAll(".new-group-drop").forEach((e) => e.remove());
  hand.style.gridTemplateColumns = ""; hand.style.justifyContent = ""; hand.style.paddingLeft = "";
  hand.style.gridColumn = ""; hand.style.justifySelf = "";
  const rack = hand.closest(".rack");
  if (rack) rack.style.gridTemplateColumns = "";
  clearTableTargets();
}

// Update 4: see the drag start above.  Only for the computer layout, where
// the rack has three columns (goal | holder | room).
function freezeRackColumns(hand) {
  const rack = hand.closest(".rack");
  if (!rack || !matchMedia("(min-width: 761px)").matches || rack.style.gridTemplateColumns) return;
  const cols = getComputedStyle(rack).gridTemplateColumns.split(" ").filter(Boolean);
  if (cols.length !== 3) return;
  const before = hand.getBoundingClientRect().left;
  rack.style.gridTemplateColumns = cols.join(" ");
  hand.style.gridColumn = "2 / -1";
  hand.style.justifySelf = "stretch";
  // (the holder's own left edge must not move)
  const after = hand.getBoundingClientRect().left;
  if (Math.abs(after - before) > 0.5) { hand.style.gridColumn = ""; hand.style.justifySelf = ""; rack.style.gridTemplateColumns = ""; }
}

// ------------------------------------------------------------ buttons
$("create").onclick = async () => {
  try {
    const data = await post("/api/create", { name: $("name").value });
    saveSession({ code: data.code, token: data.token });
  } catch (e) { toast(e.message, true); }
};

$("join").onclick = async () => {
  try {
    const data = await post("/api/join", { code: $("code").value, name: $("name").value });
    saveSession({ code: data.code, token: data.token });
  } catch (e) { toast(e.message, true); }
};

$("start").onclick = () => act("start");
$("fill-btn").onclick = () => act("fill_bots");
$("stock").onclick = () => act("draw", { source: "stock" });
$("sort-btn").onclick = () => { sortMode = sortMode === "suit" ? "rank" : "suit"; if (plan) sortAllAreas(); render(); };
$("group-btn").onclick = () => {
  if (!selected.size) return;
  moveCards([...selected], "new");
  selected.clear();
  render();
};
$("left-btn").onclick = () => { if (selected.size === 1) { nudge([...selected][0], -1); render(); } };
$("right-btn").onclick = () => { if (selected.size === 1) { nudge([...selected][0], 1); render(); } };
$("ungroup-btn").onclick = () => { breakUpAll(); render(); };
$("up-btn").onclick = () => { if (selected.size) { moveToRow([...selected], "top"); render(); } };
$("down-btn").onclick = () => { if (selected.size) { moveToRow([...selected], "bottom"); render(); } };
$("clear-btn").onclick = () => { selected.clear(); render(); };
$("next-btn").onclick = () => act("next_round");
function renderSoundBtn() {
  $("sound-btn").textContent = Sound.isOn() ? "Sound on" : "Sound off";
  $("sound-btn").setAttribute("aria-pressed", Sound.isOn() ? "true" : "false");
}
$("sound-btn").onclick = () => { Sound.setOn(!Sound.isOn()); renderSoundBtn(); };
$("speed-btn").onclick = () => { if (state) act("speed", { slow: !state.options.slow_bots }); };
$("rule-discard").onchange = (e) => act("options", { discard_after_laydown: e.target.checked });
window.addEventListener("resize", () => {
  if (state && state.status !== "lobby") fitWithTableArt();
  updateJump();
});

// Fourth edition: on a phone the table is a long page.  When your cards are
// off the bottom of the screen, a button takes you straight to them (it
// glows gold on your turn).
function updateJump() {
  const b = $("jump-hand");
  const game = $("game");
  if (!state || game.classList.contains("hidden")) { b.classList.add("hidden"); return; }
  const r = $("hand").getBoundingClientRect();
  const off = r.top > window.innerHeight - 40;
  b.classList.toggle("hidden", !off);
  const mine = state.status === "playing" && state.players[state.you] && state.players[state.you].turn;
  b.classList.toggle("mine", !!mine);
  $("jump-label").textContent = mine ? "\u25bc Your turn: your cards" : "\u25bc Your cards";
  // Update 3: while your cards (and the goal beside them) are off the screen,
  // the round's goal rides along on this button, so it is always in view.
  b.setAttribute("aria-label", `Scroll down to your cards. Round goal: ${state.round ? state.round.goal : ""}`);
}
$("jump-hand").onclick = () => $("rack").scrollIntoView({ behavior: "smooth", block: "start" });
window.addEventListener("scroll", updateJump, { passive: true });
renderSoundBtn();
$("status").onclick = () => {
  if (state && (state.status === "round_over" || state.status === "game_over")) { modalDismissed = 0; render(); }
};
$("m-close").onclick = () => { modalDismissed = state.version; render(); };
$("scores-btn").onclick = () => $("scoreboard").classList.add("open");
$("close-scores").onclick = () => $("scoreboard").classList.remove("open");

// Fifth edition, update 1: an Exit button, so you can leave the game without
// closing the browser.  Before the deal your seat is freed; once the cards
// are dealt a computer player takes over your seat for the rest of the game.
function openExit() {
  if (!session) return;
  const dealt = state && state.status !== "lobby";
  const others = state ? state.players.filter((p) => !p.bot && p.seat !== state.you).length : 0;
  $("exit-note").textContent = dealt
    ? (others
      ? "A computer player will take your seat, your cards and your score for the rest of this game, so the others can keep playing. You can't come back into this game."
      : "You're the only person at this table, so the game ends for good. You can start a new table afterwards.")
    : "Your seat will open up for someone else. You can start or join another table afterwards.";
  $("exit-modal").classList.remove("hidden");
  $("exit-stay").focus();
}
function closeExit() { $("exit-modal").classList.add("hidden"); }
async function doExit() {
  if (!session) { closeExit(); return; }
  const was = session;
  try {
    await post("/api/leave", { code: was.code, token: was.token });
  } catch (e) {
    // The table is already gone (for example the game was restarted): leave anyway.
  }
  closeExit();
  $("modal").classList.add("hidden");
  $("scoreboard").classList.remove("open");
  try { localStorage.removeItem(`${PLAN_PREFIX}${was.code}:${was.token}`); } catch (e) { /* ignore */ }
  history.replaceState(null, "", "/");
  $("code").value = "";
  leave("You left the table. Start a new table or join another one.");
}
$("exit-btn").onclick = openExit;
$("w-exit").onclick = openExit;
$("exit-stay").onclick = closeExit;
$("exit-yes").onclick = doExit;
$("exit-modal").addEventListener("click", (e) => { if (e.target === $("exit-modal")) closeExit(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("exit-modal").classList.contains("hidden")) closeExit(); });

// The table is scaled to fit the screen (CSS zoom); sizes read from the page
// are in screen pixels, so divide by this to get back to CSS pixels.
function zoomOf(node) {
  let z = 1;
  for (let a = node; a && a.nodeType === 1; a = a.parentElement) {
    const v = parseFloat(getComputedStyle(a).zoom);
    if (v && v !== 1) z *= v;
  }
  return z;
}

// ------------------------------------------------------------ start up
const params = new URLSearchParams(location.search);
const linkCode = (params.get("table") || "").toUpperCase();
if (linkCode) $("code").value = linkCode;
$("name").value = localStorage.getItem("progressive-rummy-name") || "";
$("name").addEventListener("change", () => localStorage.setItem("progressive-rummy-name", $("name").value));

if (session && (!linkCode || linkCode === session.code)) {
  pollLoop();
} else {
  show("lobby");
}
