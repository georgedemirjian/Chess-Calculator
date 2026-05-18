/**
 * Synthesized sound effects via Web Audio API.
 * AudioContext is created lazily on first use (browser autoplay policy requires
 * a user gesture before audio is permitted).
 */

let _ctx: AudioContext | null = null;
let _muted = false;

function ctx(): AudioContext {
  if (!_ctx) _ctx = new AudioContext();
  if (_ctx.state === 'suspended') _ctx.resume();
  return _ctx;
}

export function setMuted(v: boolean): void {
  _muted = v;
}

function go(fn: (c: AudioContext, t: number) => void): void {
  if (_muted) return;
  const c = ctx();
  fn(c, c.currentTime);
}

function tone(
  c: AudioContext,
  type: OscillatorType,
  freq: number,
  gain: number,
  start: number,
  dur: number,
): void {
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.connect(g);
  g.connect(c.destination);
  osc.type = type;
  osc.frequency.value = freq;
  g.gain.setValueAtTime(gain, start);
  g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
  osc.start(start);
  osc.stop(start + dur + 0.01);
}

export function playButtonClick(): void {
  go((c, t) => tone(c, 'sine', 900, 0.1, t, 0.035));
}

export function playMove(): void {
  go((c, t) => {
    const sr = c.sampleRate;

    // Layer 1: noise burst shaped with a fast click attack + slower body decay,
    // bandpass-filtered to the resonant frequency range of a hollow wood object.
    const len = Math.floor(sr * 0.07);
    const buf = c.createBuffer(1, len, sr);
    const data = buf.getChannelData(0);
    const clickDecay = sr * 0.004;
    const bodyDecay  = sr * 0.022;
    for (let i = 0; i < len; i++) {
      data[i] = (Math.random() * 2 - 1) *
        (0.45 * Math.exp(-i / clickDecay) + 0.55 * Math.exp(-i / bodyDecay));
    }
    const src = c.createBufferSource();
    src.buffer = buf;
    const bp = c.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 270;
    bp.Q.value = 2.2;
    const ng = c.createGain();
    ng.gain.setValueAtTime(0.6, t);
    ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.07);
    src.connect(bp); bp.connect(ng); ng.connect(c.destination);
    src.start(t);

    // Layer 2: pitch-dropping sine transient for the low wooden thud.
    const thud = c.createOscillator();
    const tg = c.createGain();
    thud.connect(tg); tg.connect(c.destination);
    thud.type = 'sine';
    thud.frequency.setValueAtTime(120, t);
    thud.frequency.exponentialRampToValueAtTime(58, t + 0.045);
    tg.gain.setValueAtTime(0.28, t);
    tg.gain.exponentialRampToValueAtTime(0.0001, t + 0.065);
    thud.start(t);
    thud.stop(t + 0.07);
  });
}

export function playBest(): void {
  go((c, t) => {
    // Ascending C5–E5–G5 arpeggio
    const notes: [number, number][] = [
      [523.25, 0],
      [659.25, 0.08],
      [783.99, 0.16],
    ];
    notes.forEach(([freq, delay]) => tone(c, 'sine', freq, 0.16, t + delay, 0.22));
  });
}

export function playBlunder(): void {
  go((c, t) => {
    // Descending minor interval — Eb4 → B3
    tone(c, 'triangle', 311.13, 0.22, t,       0.28);
    tone(c, 'triangle', 246.94, 0.22, t + 0.24, 0.32);
  });
}

export function playCheckmate(): void {
  go((c, t) => {
    // Triumphant fanfare: C5 E5 G5 C6 on a filtered sawtooth
    const seq: [number, number, number][] = [
      [523.25, 0,    0.13],
      [659.25, 0.15, 0.13],
      [783.99, 0.30, 0.13],
      [1046.5, 0.45, 0.60],
    ];
    seq.forEach(([freq, delay, dur]) => {
      const osc = c.createOscillator();
      const lp  = c.createBiquadFilter();
      const g   = c.createGain();
      osc.connect(lp);
      lp.connect(g);
      g.connect(c.destination);
      osc.type = 'sawtooth';
      osc.frequency.value = freq;
      lp.type = 'lowpass';
      lp.frequency.value = 2200;
      g.gain.setValueAtTime(0.14, t + delay);
      g.gain.exponentialRampToValueAtTime(0.0001, t + delay + dur);
      osc.start(t + delay);
      osc.stop(t + delay + dur + 0.01);
    });
  });
}
