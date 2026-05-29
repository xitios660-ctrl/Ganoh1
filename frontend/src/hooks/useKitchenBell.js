import { useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'ganoh_kitchen_bell_on';

/**
 * useKitchenBell — plays a classic bell "ding" whenever a new order arrives.
 *
 * Royalty-free, generated procedurally via Web Audio (zero dependency, zero bandwidth).
 * Detects "new" orders by comparing the latest order count / set of IDs against the
 * previous render.
 *
 * Returns { enabled, toggle, mute } so the UI can render a toggle.
 */
export function useKitchenBell(orders) {
  const [enabled, setEnabled] = useState(() => {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      return v === null ? true : v === 'true';
    } catch {
      return true;
    }
  });
  const prevIdsRef = useRef(null); // null = first render, no bell

  // Play the bell (two-tone metallic chime)
  const playBell = () => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      const master = ctx.createGain();
      master.gain.value = 0.0001;
      master.connect(ctx.destination);

      // Two partials of a bell — fundamental + ringing harmonic
      const partials = [
        { freq: 880, decay: 1.8, gain: 0.5 }, // A5
        { freq: 1318.5, decay: 1.2, gain: 0.3 }, // E6 (perfect 5th up)
      ];
      const now = ctx.currentTime;
      partials.forEach((p) => {
        const osc = ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.value = p.freq;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0, now);
        g.gain.linearRampToValueAtTime(p.gain, now + 0.005);
        g.gain.exponentialRampToValueAtTime(0.0001, now + p.decay);
        osc.connect(g);
        g.connect(master);
        osc.start(now);
        osc.stop(now + p.decay + 0.05);
      });

      // Soft attack noise (mallet hit)
      const noiseBuf = ctx.createBuffer(1, ctx.sampleRate * 0.05, ctx.sampleRate);
      const data = noiseBuf.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1);
      const noise = ctx.createBufferSource();
      noise.buffer = noiseBuf;
      const filter = ctx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.value = 3500;
      const ng = ctx.createGain();
      ng.gain.setValueAtTime(0.18, now);
      ng.gain.exponentialRampToValueAtTime(0.0001, now + 0.08);
      noise.connect(filter);
      filter.connect(ng);
      ng.connect(master);
      noise.start(now);

      // Master envelope
      master.gain.setValueAtTime(0.0001, now);
      master.gain.exponentialRampToValueAtTime(0.85, now + 0.01);
      master.gain.exponentialRampToValueAtTime(0.0001, now + 2.0);

      // Auto-close context to avoid leaks
      setTimeout(() => {
        try { ctx.close(); } catch { /* ignore */ }
      }, 2500);
    } catch (e) {
      console.warn('Kitchen bell failed:', e);
    }
  };

  useEffect(() => {
    if (!Array.isArray(orders)) return;
    const currentIds = new Set(orders.map((o) => o.id || o._id).filter(Boolean));

    if (prevIdsRef.current === null) {
      // First load — just snapshot, no bell
      prevIdsRef.current = currentIds;
      return;
    }

    // Find new orders (present now but not before)
    let newCount = 0;
    currentIds.forEach((id) => {
      if (!prevIdsRef.current.has(id)) newCount++;
    });

    if (newCount > 0 && enabled) {
      playBell();
    }
    prevIdsRef.current = currentIds;
  }, [orders, enabled]);

  const toggle = () => {
    const next = !enabled;
    setEnabled(next);
    try { localStorage.setItem(STORAGE_KEY, String(next)); } catch { /* ignore */ }
    if (next) playBell(); // preview when turning on
  };

  return { enabled, toggle, playBell };
}

export default useKitchenBell;
