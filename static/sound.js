// Card-table sounds, made in the browser with the Web Audio API (no sound
// files).  Browsers keep sound off until the person taps or clicks the page
// once, so the sound starts on the first tap.  The Sound button turns it
// off and on, and the choice is remembered on that device.
"use strict";

const Sound = (() => {
  const KEY = "progressive-rummy-sound";
  let ctx = null;
  let on = localStorage.getItem(KEY) !== "off";
  const log = [];                       // for the browser test: what was played
  window.__soundLog = log;

  function unlock() {
    try {
      if (!ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return;
        ctx = new AC();
      }
      if (ctx.state === "suspended") ctx.resume();
    } catch (e) { /* no sound on this device */ }
  }
  for (const ev of ["pointerdown", "keydown", "touchstart"]) {
    window.addEventListener(ev, unlock, { capture: true, passive: true });
  }

  function ready() {
    return on && ctx && ctx.state === "running";
  }

  function noise(seconds) {
    const len = Math.max(1, Math.floor(ctx.sampleRate * seconds));
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len) ** 2;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    return src;
  }

  // A card snapping onto felt: a short burst of filtered noise.
  function snap(at, { freq = 2600, q = 0.9, gain = 0.5, length = 0.07 } = {}) {
    const src = noise(length);
    const filter = ctx.createBiquadFilter();
    filter.type = "bandpass";
    filter.frequency.value = freq * (0.9 + Math.random() * 0.2);
    filter.Q.value = q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(gain, at);
    g.gain.exponentialRampToValueAtTime(0.001, at + length);
    src.connect(filter).connect(g).connect(ctx.destination);
    src.start(at);
  }

  function tone(at, freq, length, gain = 0.15, type = "sine") {
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.value = freq;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(gain, at + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, at + length);
    osc.connect(g).connect(ctx.destination);
    osc.start(at);
    osc.stop(at + length + 0.05);
  }

  const sounds = {
    // one flick per card going round the table (capped so it stays short)
    deal(count = 20, gap = 0.05) {
      const t = ctx.currentTime + 0.05;
      for (let i = 0; i < count; i++) snap(t + i * gap, { gain: 0.35, length: 0.05 });
    },
    draw() { snap(ctx.currentTime, { freq: 1800, gain: 0.4, length: 0.09 }); },
    discard() {
      const t = ctx.currentTime;
      snap(t, { freq: 1200, q: 0.7, gain: 0.6, length: 0.11 });
    },
    place() {               // laying down or adding to the table
      const t = ctx.currentTime;
      for (let i = 0; i < 3; i++) snap(t + i * 0.06, { freq: 1500, gain: 0.45, length: 0.08 });
    },
    yourTurn() {
      const t = ctx.currentTime;
      tone(t, 660, 0.18);
      tone(t + 0.14, 880, 0.3);
    },
    roundOver() {
      const t = ctx.currentTime;
      [523, 659, 784, 1047].forEach((f, i) => tone(t + i * 0.12, f, 0.35, 0.12, "triangle"));
    },
    oops() { tone(ctx.currentTime, 196, 0.2, 0.08, "square"); },
  };

  function play(name, ...args) {
    const played = ready();
    log.push({ name, played, muted: !on });
    if (log.length > 200) log.shift();
    if (!played) return;
    try { sounds[name](...args); } catch (e) { /* ignore a sound that fails */ }
  }

  function setOn(value) {
    on = value;
    localStorage.setItem(KEY, on ? "on" : "off");
    if (on) { unlock(); play("draw"); }
  }

  return { play, setOn, isOn: () => on, unlock };
})();
