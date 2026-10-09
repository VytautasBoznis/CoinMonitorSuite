// War Room sound effects, synthesized with Web Audio (no audio files). Browsers only start audio
// after a user gesture, so `wake()` runs from a click; the mute choice persists.

const KEY = "coinmon.sfx";

class Sfx {
  muted = localStorage.getItem(KEY) === "off";
  private ctx?: AudioContext;
  private out?: GainNode;
  private lastPing = 0;

  /** Starts audio. The first call must come from a user gesture. */
  wake() {
    if (this.muted) return;
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.out = this.ctx.createGain();
      this.out.gain.value = 0.22;
      this.out.connect(this.ctx.destination);
    }
    void this.ctx.resume();
  }

  setMuted(muted: boolean) {
    this.muted = muted;
    localStorage.setItem(KEY, muted ? "off" : "on");
    if (!muted) this.wake();
  }

  private live(): AudioContext | undefined {
    return !this.muted && this.ctx?.state === "running" ? this.ctx : undefined;
  }

  private tone(freq: number, dur: number, o: { type?: OscillatorType; gain?: number; to?: number; at?: number } = {}) {
    const ctx = this.live();
    if (!ctx) return;
    const t = ctx.currentTime + (o.at ?? 0);
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = o.type ?? "sine";
    osc.frequency.setValueAtTime(freq, t);
    if (o.to) osc.frequency.exponentialRampToValueAtTime(o.to, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(o.gain ?? 0.4, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g).connect(this.out!);
    osc.start(t);
    osc.stop(t + dur + 0.05);
  }

  private noise(dur: number, gain: number) {
    const ctx = this.live();
    if (!ctx) return;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * dur), ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length) ** 2;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 900;
    const g = ctx.createGain();
    g.gain.value = gain;
    src.connect(lp).connect(g).connect(this.out!);
    src.start();
  }

  /** A liquidation print: the bigger, the deeper. Rate-limited so a cascade stays listenable. */
  ping(usd: number) {
    const now = performance.now();
    if (now - this.lastPing < 110) return;
    this.lastPing = now;
    const k = Math.min(1, Math.log10(Math.max(usd, 10)) / 6.5);
    this.tone(1500 - 1100 * k, 0.09 + 0.14 * k, { type: "triangle", gain: 0.1 + 0.22 * k });
  }

  /** A whale print. */
  boom() {
    this.tone(120, 1.0, { gain: 0.8, to: 30 });
    this.noise(0.7, 0.6);
  }

  /** Geiger tick, higher as a coin nears its strike. */
  tick(p: number) {
    this.tone(650 + 950 * p, 0.045, { type: "square", gain: 0.05 + 0.1 * p });
  }

  /** The bot bought. */
  fill() {
    [523.25, 659.25, 783.99, 1046.5, 1318.5].forEach((f, i) =>
      this.tone(f, 0.24, { type: "square", gain: 0.16, at: i * 0.07 }),
    );
    this.tone(60, 1.4, { gain: 0.7, to: 28 });
  }

  /** A position closed: up for a win, down for a loss. */
  close(win: boolean) {
    (win ? [784, 988, 1175, 1568] : [523, 440, 349, 262]).forEach((f, i) =>
      this.tone(f, 0.22, { type: "triangle", gain: 0.2, at: i * 0.08 }),
    );
  }

  /** The safety cover. */
  arm() {
    this.tone(160, 0.28, { type: "sawtooth", gain: 0.12, to: 560 });
  }
}

export const sfx = new Sfx();
