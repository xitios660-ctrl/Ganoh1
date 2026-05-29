import React, { useEffect, useRef, useState } from 'react';
import { Music, VolumeX } from 'lucide-react';

// Calm classical café music — public-domain composition, royalty-free.
const AUDIO_SRC = '/audio/lounge.mp3?v=2';
const STORAGE_KEY = 'ganoh_bgmusic_on';
const VOL_KEY = 'ganoh_bgmusic_vol';
const POS_KEY = 'ganoh_bgmusic_pos';

/**
 * Royalty-free lounge background music — plays EVERYWHERE in the app.
 * - Persists play state + position across pages (Selector → Menu → Kitchen → Gestor…)
 * - Mounted once at app root so navigation doesn't restart it
 * - Auto-play attempted on first user interaction (browser autoplay policy)
 */
export const BackgroundMusic = () => {
  const [playing, setPlaying] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored === null ? true : stored === 'true';
    } catch {
      return true;
    }
  });
  const [volume] = useState(() => {
    try {
      const v = parseFloat(localStorage.getItem(VOL_KEY) || '0.22');
      return isNaN(v) ? 0.22 : v;
    } catch {
      return 0.22;
    }
  });
  const audioRef = useRef(null);
  const [needsUserGesture, setNeedsUserGesture] = useState(false);

  // Setup audio element once (lives forever, never restarts on navigation)
  useEffect(() => {
    if (!audioRef.current) {
      const a = new Audio(AUDIO_SRC);
      a.loop = true;
      a.volume = volume;
      a.preload = 'auto';
      try {
        const pos = parseFloat(localStorage.getItem(POS_KEY) || '0');
        if (!isNaN(pos)) a.currentTime = pos;
      } catch { /* ignore */ }
      audioRef.current = a;
    }
    const a = audioRef.current;

    const posInterval = setInterval(() => {
      try { localStorage.setItem(POS_KEY, String(a.currentTime || 0)); } catch { /* ignore */ }
    }, 5000);

    return () => clearInterval(posInterval);
  }, [volume]);

  // React to play state
  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    if (playing) {
      const p = a.play();
      if (p && p.catch) {
        p.catch(() => {
          // Autoplay blocked — wait for user gesture
          setNeedsUserGesture(true);
        });
      } else {
        setNeedsUserGesture(false);
      }
    } else {
      a.pause();
      setNeedsUserGesture(false);
    }
  }, [playing]);

  // On ANY user gesture (click, key, touch), try to start audio
  useEffect(() => {
    if (!needsUserGesture) return;
    const tryStart = () => {
      const a = audioRef.current;
      if (a && playing) {
        a.play().then(() => setNeedsUserGesture(false)).catch(() => { /* still blocked */ });
      }
    };
    const opts = { once: true, passive: true };
    window.addEventListener('click', tryStart, opts);
    window.addEventListener('keydown', tryStart, opts);
    window.addEventListener('touchstart', tryStart, opts);
    return () => {
      window.removeEventListener('click', tryStart);
      window.removeEventListener('keydown', tryStart);
      window.removeEventListener('touchstart', tryStart);
    };
  }, [needsUserGesture, playing]);

  // Pause on tab hidden to save battery, resume on visible
  useEffect(() => {
    const onVis = () => {
      const a = audioRef.current;
      if (!a) return;
      if (document.hidden) {
        a.pause();
      } else if (playing) {
        a.play().catch(() => { /* ignore */ });
      }
    };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, [playing]);

  const toggle = () => {
    const next = !playing;
    setPlaying(next);
    try { localStorage.setItem(STORAGE_KEY, String(next)); } catch { /* ignore */ }
    if (next && audioRef.current) {
      audioRef.current.play().then(() => setNeedsUserGesture(false)).catch(() => { /* ignore */ });
    }
  };

  return (
    <button
      onClick={toggle}
      data-testid="bg-music-toggle"
      aria-label={playing ? 'Pausar música ambiente' : 'Tocar música ambiente'}
      title={playing ? 'Música ambiente: tocando' : 'Música ambiente: clique para tocar'}
      className="fixed bottom-4 left-4 z-40 h-11 w-11 rounded-full flex items-center justify-center backdrop-blur-xl bg-black/55 hover:bg-black/75 text-white/90 hover:text-[#a8d96b] transition-all hover:scale-110 active:scale-95 shadow-lg shadow-black/40 border border-white/10"
      style={{
        boxShadow: playing
          ? '0 0 0 2px rgba(168,217,107,0.4), 0 8px 24px rgba(0,0,0,0.35)'
          : '0 4px 12px rgba(0,0,0,0.3)',
      }}
    >
      {playing ? <Music className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
      {playing && !needsUserGesture && (
        <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-[#a8d96b] animate-pulse" />
      )}
      {needsUserGesture && playing && (
        <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
      )}
    </button>
  );
};

export default BackgroundMusic;
