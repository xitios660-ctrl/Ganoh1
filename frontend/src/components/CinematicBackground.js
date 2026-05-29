import React, { useEffect, useRef } from 'react';

/**
 * CinematicBackground - parallax mouse-aware ambient layer.
 * PERFORMANCE: usa ref + rAF direto no DOM (sem setState), zero rerenders no mousemove.
 */
export const CinematicBackground = ({ accent = '#a8d96b' }) => {
  const orb1 = useRef(null);
  const orb2 = useRef(null);
  const beam = useRef(null);

  useEffect(() => {
    let raf;
    let tx = 0, ty = 0, x = 0, y = 0;

    const onMove = (e) => {
      tx = e.clientX / window.innerWidth - 0.5;
      ty = e.clientY / window.innerHeight - 0.5;
    };

    const loop = () => {
      // lerp para suavizar
      x += (tx - x) * 0.06;
      y += (ty - y) * 0.06;
      if (orb1.current) orb1.current.style.transform = `translate3d(${x * -40}px, ${y * -40}px, 0)`;
      if (orb2.current) orb2.current.style.transform = `translate3d(${x * 60}px, ${y * 60}px, 0)`;
      if (beam.current) beam.current.style.transform = `translate3d(${x * 30}px, ${y * 30}px, 0) rotate(${x * 4}deg)`;
      raf = requestAnimationFrame(loop);
    };

    window.addEventListener('mousemove', onMove, { passive: true });
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('mousemove', onMove);
    };
  }, []);

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden" data-testid="cinematic-bg">
      {/* base radial */}
      <div
        className="absolute inset-0"
        style={{ background: `radial-gradient(ellipse at center, ${accent}14, transparent 60%)` }}
      />

      {/* orb back */}
      <div
        ref={orb1}
        className="absolute rounded-full blur-[100px] will-change-transform"
        style={{
          width: '55vmin', height: '55vmin',
          left: '10%', top: '15%',
          background: `radial-gradient(circle, ${accent}26, transparent 70%)`,
          animation: 'ganoh-pulse-slow 9s ease-in-out infinite',
        }}
      />
      <div
        ref={orb2}
        className="absolute rounded-full blur-[120px] will-change-transform"
        style={{
          width: '50vmin', height: '50vmin',
          right: '8%', bottom: '12%',
          background: `radial-gradient(circle, ${accent}1f, transparent 70%)`,
          animation: 'ganoh-pulse-slow 11s ease-in-out infinite',
        }}
      />

      {/* light beam - CSS only, parallax via ref */}
      <div
        ref={beam}
        className="absolute -inset-1/4 opacity-[0.04] will-change-transform"
        style={{
          background: `linear-gradient(120deg, transparent 42%, ${accent} 50%, transparent 58%)`,
          animation: 'ganoh-beam 22s ease-in-out infinite',
        }}
      />

      {/* film grain — static SVG (no animation = no cost) */}
      <div
        className="absolute inset-0 opacity-[0.06] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />

      {/* vignette */}
      <div
        className="absolute inset-0"
        style={{ background: 'radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,0.6) 100%)' }}
      />
    </div>
  );
};

export default CinematicBackground;
