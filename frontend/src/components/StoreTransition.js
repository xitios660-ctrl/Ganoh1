import React, { useEffect, useState } from 'react';

/**
 * StoreTransition - Cinematic full-screen "portal opening" animation
 * played when user clicks a store button. Total duration ≈ 5.2s.
 *
 * Phases (timed):
 *   0.0s  - Black radial iris closes from button position
 *   0.2s  - Store name reveals (letter-by-letter)
 *   2.0s  - Tagline + golden divider appear
 *   2.9s  - Light beams sweep outward
 *   4.4s  - Doors split horizontally and open
 *   5.2s  - onComplete fires → navigate
 *
 * Props:
 *   store: { id, name, tagline, accent? }
 *   origin: { x, y } - click coordinates for iris start
 *   onComplete: () => void
 */

const STORE_CONFIG = {
  runner: {
    name: 'GANOH Runner',
    tagline: 'Energia · Performance · Sabor',
    accent: '#a8d96b',
    accentDeep: '#7CB342',
    backdrop: 'radial-gradient(ellipse at center, #0a1d0d 0%, #050805 70%, #000 100%)',
  },
  'gym-londres': {
    name: 'GANOH GYM Londres',
    tagline: 'Força · Foco · Equilíbrio',
    accent: '#e9c46a',
    accentDeep: '#c9a342',
    backdrop: 'radial-gradient(ellipse at center, #1d1606 0%, #08050a 70%, #000 100%)',
  },
};

export const StoreTransition = ({ storeId, origin = { x: '50%', y: '50%' }, onComplete }) => {
  const [phase, setPhase] = useState(0);
  const cfg = STORE_CONFIG[storeId] || STORE_CONFIG.runner;

  useEffect(() => {
    const timers = [
      setTimeout(() => setPhase(1), 200),    // letters start revealing
      setTimeout(() => setPhase(2), 2000),   // divider + tagline appear
      setTimeout(() => setPhase(3), 2900),   // light beams sweep
      setTimeout(() => setPhase(4), 4400),   // veil fades + zoom-out
      setTimeout(() => onComplete && onComplete(), 5200),
    ];
    return () => timers.forEach(clearTimeout);
  }, [onComplete]);

  const letters = cfg.name.split('');

  return (
    <div className="store-transition" data-testid={`store-transition-${storeId}`}>
      {/* Iris from click origin */}
      <div
        className="st-iris"
        style={{
          left: origin.x,
          top: origin.y,
          background: cfg.backdrop,
        }}
      />

      {/* Light beams sweeping */}
      <div className={`st-beams ${phase >= 3 ? 'st-beams--active' : ''}`}>
        <span style={{ '--beam-color': cfg.accent }} />
        <span style={{ '--beam-color': cfg.accent, animationDelay: '0.12s' }} />
        <span style={{ '--beam-color': cfg.accentDeep, animationDelay: '0.24s' }} />
        <span style={{ '--beam-color': cfg.accent, animationDelay: '0.36s' }} />
      </div>

      {/* Glow halo behind text */}
      <div
        className={`st-halo ${phase >= 1 ? 'st-halo--visible' : ''}`}
        style={{ background: `radial-gradient(circle, ${cfg.accent}40, transparent 70%)` }}
      />

      {/* Centered store name + tagline */}
      <div className="st-content">
        <div className="st-name">
          {letters.map((ch, i) => (
            <span
              key={i}
              className={`st-letter ${phase >= 1 ? 'st-letter--in' : ''}`}
              style={{
                animationDelay: `${0.13 * i}s`,
                color: ch === '·' ? cfg.accent : '#ffffff',
              }}
            >
              {ch === ' ' ? '\u00A0' : ch}
            </span>
          ))}
        </div>

        <div
          className={`st-divider ${phase >= 2 ? 'st-divider--in' : ''}`}
          style={{ background: `linear-gradient(90deg, transparent, ${cfg.accent}, transparent)` }}
        />

        <p
          className={`st-tagline ${phase >= 2 ? 'st-tagline--in' : ''}`}
          style={{ color: `${cfg.accent}cc` }}
        >
          {cfg.tagline}
        </p>

        <p
          className={`st-stamp ${phase >= 2 ? 'st-stamp--in' : ''}`}
          style={{ color: cfg.accent }}
        >
          Entrando no cardápio
        </p>
      </div>

      {/* Particles */}
      {phase >= 1 && (
        <div className="st-particles">
          {Array.from({ length: 24 }).map((_, i) => (
            <span
              key={i}
              style={{
                left: `${5 + Math.random() * 90}%`,
                top: `${10 + Math.random() * 80}%`,
                animationDelay: `${Math.random() * 0.8}s`,
                background: cfg.accent,
              }}
            />
          ))}
        </div>
      )}

      {/* Fade-out veil that grows + fades at phase 4 to reveal menu underneath */}
      <div className={`st-veil ${phase >= 4 ? 'st-veil--out' : ''}`} />
    </div>
  );
};

export default StoreTransition;
