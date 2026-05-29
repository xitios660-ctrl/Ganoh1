import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

/**
 * Cinematic Ambient Sound
 * - Procedurally generated using WebAudio (no MP3 file needed → 0 bandwidth)
 * - 3-layer pad: deep drone + soft pulse + sparse shimmer
 * - User-initiated only (browser autoplay policy compliant)
 * - Mute by default, persisted in localStorage
 */
export const AmbientSound = () => {
  const [enabled, setEnabled] = useState(() => {
    try { return localStorage.getItem('ganoh_ambient_sound') === 'on'; } catch { return false; }
  });
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const ctxRef = useRef(null);
  const nodesRef = useRef(null);

  const stopAudio = useCallback(() => {
    if (nodesRef.current) {
      try {
        nodesRef.current.master.gain.cancelScheduledValues(0);
        nodesRef.current.master.gain.linearRampToValueAtTime(0, (ctxRef.current?.currentTime || 0) + 0.6);
        setTimeout(() => {
          try {
            nodesRef.current?.oscillators?.forEach(o => o.stop());
            nodesRef.current = null;
          } catch (e) { /* ignore */ }
        }, 700);
      } catch (e) { /* ignore */ }
    }
  }, []);

  const startAudio = useCallback(() => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      if (!ctxRef.current) ctxRef.current = new Ctx();
      const ctx = ctxRef.current;
      if (ctx.state === 'suspended') ctx.resume();

      // Master gain (very soft, cinematic)
      const master = ctx.createGain();
      master.gain.value = 0;
      master.connect(ctx.destination);
      master.gain.linearRampToValueAtTime(0.045, ctx.currentTime + 1.5);

      // Layer 1 — Deep drone (root)
      const drone = ctx.createOscillator();
      drone.type = 'sine';
      drone.frequency.value = 110; // A2
      const droneGain = ctx.createGain();
      droneGain.gain.value = 0.55;

      // LFO for drone modulation
      const lfo = ctx.createOscillator();
      lfo.frequency.value = 0.08;
      const lfoGain = ctx.createGain();
      lfoGain.gain.value = 2;
      lfo.connect(lfoGain);
      lfoGain.connect(drone.frequency);

      drone.connect(droneGain);
      droneGain.connect(master);

      // Layer 2 — Soft pulse (fifth)
      const pulse = ctx.createOscillator();
      pulse.type = 'triangle';
      pulse.frequency.value = 164.81; // E3
      const pulseGain = ctx.createGain();
      pulseGain.gain.value = 0.25;
      pulse.connect(pulseGain);
      pulseGain.connect(master);

      // Layer 3 — Filtered noise shimmer
      const bufferSize = 2 * ctx.sampleRate;
      const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const data = noiseBuffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) data[i] = (Math.random() * 2 - 1) * 0.5;
      const noise = ctx.createBufferSource();
      noise.buffer = noiseBuffer;
      noise.loop = true;
      const noiseFilter = ctx.createBiquadFilter();
      noiseFilter.type = 'bandpass';
      noiseFilter.frequency.value = 2500;
      noiseFilter.Q.value = 1.2;
      const noiseGain = ctx.createGain();
      noiseGain.gain.value = 0.07;
      noise.connect(noiseFilter);
      noiseFilter.connect(noiseGain);
      noiseGain.connect(master);

      drone.start();
      pulse.start();
      lfo.start();
      noise.start();

      nodesRef.current = { master, oscillators: [drone, pulse, lfo, noise] };
    } catch (e) {
      console.warn('AudioContext failed', e);
    }
  }, []);

  useEffect(() => {
    if (enabled) startAudio(); else stopAudio();
    return () => stopAudio();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  const toggle = () => {
    const next = !enabled;
    setEnabled(next);
    try { localStorage.setItem('ganoh_ambient_sound', next ? 'on' : 'off'); } catch { /* ignore */ }
  };

  return (
    <button
      onClick={toggle}
      data-testid="ambient-sound-toggle"
      aria-label={enabled ? 'Desativar som ambiente' : 'Ativar som ambiente'}
      title={enabled ? 'Som ambiente: ligado' : 'Som ambiente: clique para ligar'}
      className={`fixed bottom-4 right-4 z-40 h-11 w-11 rounded-full flex items-center justify-center backdrop-blur-xl transition-all hover:scale-110 active:scale-95 ${
        isDark
          ? 'bg-white/[0.06] hover:bg-white/[0.12] text-white/80 hover:text-[#a8d96b] shadow-lg shadow-black/40'
          : 'bg-black/[0.04] hover:bg-black/[0.08] text-foreground/70 hover:text-[#6ba33b] shadow-md'
      }`}
      style={{
        boxShadow: enabled
          ? '0 0 0 2px rgba(168,217,107,0.4), 0 8px 24px rgba(0,0,0,0.25)'
          : undefined,
      }}
    >
      {enabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
      {enabled && (
        <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-[#a8d96b] animate-pulse" />
      )}
    </button>
  );
};
