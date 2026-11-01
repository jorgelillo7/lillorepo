/**
 * Sound, synthesized with the Web Audio API: room ambiences, doors, steps,
 * scare stings and a heartbeat. No audio files, so nothing to license.
 * Browsers only start audio after a user gesture; `unlock()` is called on the
 * first tap or key, and until then everything is silently skipped.
 */

import type { Ambience } from "../engine/game.ts";
import { settings } from "./settings.ts";

let ctx: AudioContext | null = null;
let master: GainNode;
let noise: AudioBuffer;
let current: { name: Ambience; stop: () => void } | null = null;
let wanted: Ambience = "silence";
let heart: number | null = null;

function makeNoise(c: AudioContext): AudioBuffer {
  // Brown noise: integrated white noise, soft and low, a good base for rooms.
  const buffer = c.createBuffer(1, c.sampleRate * 3, c.sampleRate);
  const data = buffer.getChannelData(0);
  let last = 0;
  for (let i = 0; i < data.length; i++) {
    last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02;
    data[i] = last * 3.5;
  }
  return buffer;
}

export function unlock(): void {
  if (!ctx) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return;
    ctx = new Ctor();
    master = ctx.createGain();
    master.connect(ctx.destination);
    noise = makeNoise(ctx);
    applyVolume();
    document.addEventListener("visibilitychange", () => {
      if (!ctx) return;
      if (document.hidden) void ctx.suspend();
      else void ctx.resume();
    });
  }
  if (ctx.state === "suspended") void ctx.resume();
  setAmbience(wanted, true);
}

export function audioState(): string {
  return ctx ? ctx.state : "locked";
}

export function applyVolume(): void {
  if (!ctx) return;
  const s = settings();
  master.gain.setTargetAtTime(s.muted ? 0 : s.volume * 0.6, ctx.currentTime, 0.1);
}

function noiseSource(c: AudioContext): AudioBufferSourceNode {
  const src = c.createBufferSource();
  src.buffer = noise;
  src.loop = true;
  return src;
}

function osc(c: AudioContext, type: OscillatorType, freq: number): OscillatorNode {
  const o = c.createOscillator();
  o.type = type;
  o.frequency.value = freq;
  return o;
}

/** Builds one ambience into `out`; returns its sources so it can be stopped. */
function build(c: AudioContext, name: Ambience, out: GainNode): AudioScheduledSourceNode[] {
  const sources: AudioScheduledSourceNode[] = [];
  const add = <T extends AudioScheduledSourceNode>(n: T) => (sources.push(n), n);
  if (name === "hum") {
    // Fluorescent tubes: mains hum and its harmonics, with a slow flicker.
    const g = c.createGain();
    g.gain.value = 0.05;
    for (const [f, v] of [[100, 1], [200, 0.5], [300, 0.25]] as const) {
      const o = add(osc(c, "sine", f));
      const og = c.createGain();
      og.gain.value = v;
      o.connect(og).connect(g);
    }
    const lfo = add(osc(c, "sine", 0.3));
    const lg = c.createGain();
    lg.gain.value = 0.02;
    lfo.connect(lg).connect(g.gain);
    g.connect(out);
    const n = add(noiseSource(c));
    const f = c.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.value = 500;
    const ng = c.createGain();
    ng.gain.value = 0.25;
    n.connect(f).connect(ng).connect(out);
  } else if (name === "drone") {
    // Two detuned low tones under a slowly breathing filter.
    const f = c.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.value = 260;
    const g = c.createGain();
    g.gain.value = 0.09;
    for (const freq of [55, 55.6, 82.4]) add(osc(c, "sawtooth", freq)).connect(f);
    const lfo = add(osc(c, "sine", 0.07));
    const lg = c.createGain();
    lg.gain.value = 120;
    lfo.connect(lg).connect(f.frequency);
    f.connect(g).connect(out);
  } else if (name === "wind") {
    const n = add(noiseSource(c));
    const f = c.createBiquadFilter();
    f.type = "bandpass";
    f.frequency.value = 400;
    f.Q.value = 0.8;
    const lfo = add(osc(c, "sine", 0.11));
    const lg = c.createGain();
    lg.gain.value = 250;
    lfo.connect(lg).connect(f.frequency);
    const g = c.createGain();
    g.gain.value = 0.5;
    n.connect(f).connect(g).connect(out);
  } else if (name === "drip") {
    // Damp room tone, plus water drops scheduled at random below.
    const n = add(noiseSource(c));
    const f = c.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.value = 300;
    const g = c.createGain();
    g.gain.value = 0.35;
    n.connect(f).connect(g).connect(out);
  }
  for (const s of sources) s.start();
  return sources;
}

function scheduleDrips(c: AudioContext, out: GainNode, alive: () => boolean): void {
  const drip = () => {
    if (!alive()) return;
    const t = c.currentTime;
    const o = osc(c, "sine", 1400 + Math.random() * 600);
    o.frequency.exponentialRampToValueAtTime(420, t + 0.09);
    const g = c.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.18, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    const echo = c.createDelay();
    echo.delayTime.value = 0.13;
    const fb = c.createGain();
    fb.gain.value = 0.35;
    o.connect(g).connect(out);
    g.connect(echo).connect(fb).connect(echo);
    fb.connect(out);
    o.start(t);
    o.stop(t + 0.15);
    setTimeout(drip, 1500 + Math.random() * 4000);
  };
  setTimeout(drip, 800);
}

/** Crossfade to `name`. Repeating the current one does nothing. */
export function setAmbience(name: Ambience, force = false): void {
  wanted = name;
  if (!ctx || (!force && current?.name === name)) return;
  if (current?.name === name) return;
  const c = ctx;
  current?.stop();
  const out = c.createGain();
  out.gain.setValueAtTime(0.0001, c.currentTime);
  out.gain.exponentialRampToValueAtTime(1, c.currentTime + 1.5);
  out.connect(master);
  let alive = true;
  const sources = build(c, name, out);
  if (name === "drip") scheduleDrips(c, out, () => alive);
  current = {
    name,
    stop: () => {
      alive = false;
      out.gain.cancelScheduledValues(c.currentTime);
      out.gain.setTargetAtTime(0.0001, c.currentTime, 0.4);
      setTimeout(() => {
        for (const s of sources) s.stop();
        out.disconnect();
      }, 2000);
    },
  };
}

function burst(c: AudioContext, filterType: BiquadFilterType, freq: number, gain: number, dur: number, at = 0): void {
  const t = c.currentTime + at;
  const n = noiseSource(c);
  const f = c.createBiquadFilter();
  f.type = filterType;
  f.frequency.value = freq;
  const g = c.createGain();
  g.gain.setValueAtTime(gain, t);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  n.connect(f).connect(g).connect(master);
  n.start(t);
  n.stop(t + dur + 0.05);
}

/** A heavy door: a creaking hinge, then the thud. */
export function door(): void {
  if (!ctx) return;
  const c = ctx;
  const t = c.currentTime;
  const o = osc(c, "sawtooth", 90);
  o.frequency.setValueAtTime(90, t);
  o.frequency.linearRampToValueAtTime(160, t + 0.5);
  o.frequency.linearRampToValueAtTime(120, t + 0.8);
  const f = c.createBiquadFilter();
  f.type = "bandpass";
  f.frequency.value = 900;
  f.Q.value = 6;
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(0.12, t + 0.1);
  g.gain.exponentialRampToValueAtTime(0.0001, t + 0.85);
  o.connect(f).connect(g).connect(master);
  o.start(t);
  o.stop(t + 0.9);
  burst(c, "lowpass", 160, 0.9, 0.35, 0.9);
}

/** A footstep, for moving on within a place. */
export function step(): void {
  if (!ctx) return;
  burst(ctx, "lowpass", 260, 0.35, 0.12);
}

/** A scare sting: a dissonant stab over a low hit. */
export function sting(): void {
  if (!ctx) return;
  const c = ctx;
  const t = c.currentTime;
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(0.22, t + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t + 2.2);
  g.connect(master);
  for (const f of [233, 247, 349, 370, 523]) {
    const o = osc(c, "sawtooth", f);
    o.connect(g);
    o.start(t);
    o.stop(t + 2.3);
  }
  burst(c, "lowpass", 120, 1.2, 0.8);
}

function beat(): void {
  if (!ctx) return;
  burst(ctx, "lowpass", 90, 0.9, 0.12);
  burst(ctx, "lowpass", 80, 0.6, 0.12, 0.22);
}

/** A heartbeat while `bpm` is set; null stops it. */
export function heartbeat(bpm: number | null): void {
  if (heart !== null) clearInterval(heart);
  heart = null;
  if (bpm) heart = window.setInterval(beat, 60000 / bpm);
}

// Read by the headless play-through checks; harmless for readers.
(window as unknown as { __audio: object }).__audio = {
  state: audioState,
  ambience: () => current?.name ?? null,
};
