import React, { useRef, useEffect, useState } from 'react';

const LOGO_URL = '/assets/ganoh-logo.png';

/**
 * Logo3D — cinematic, eye-catching 3D logo for the menu header / hero.
 * - Mouse-parallax tilt (perspective transform)
 * - Floating idle animation
 * - Animated emerald glow + gold shimmer pass
 * - Soft inner shadow ring around the logo
 * - Adapts to light / dark theme
 *
 * Props:
 *   size: 'sm' | 'md' | 'lg' | 'xl' — height preset
 *   isDark: boolean
 *   variant: 'header' | 'hero'  — controls intensity of effects
 */
export const Logo3D = ({ size = 'md', isDark = false, variant = 'hero', className = '' }) => {
  const wrapRef = useRef(null);
  const [tilt, setTilt] = useState({ rx: 0, ry: 0 });

  const heightClass = {
    sm: 'h-10',
    md: 'h-14',
    lg: 'h-20 md:h-24',
    xl: 'h-28 md:h-36',
  }[size] || 'h-20';

  // Mouse parallax — gives true 3D feel
  useEffect(() => {
    if (variant !== 'hero') return; // only hero gets full parallax
    const el = wrapRef.current;
    if (!el) return;
    let raf = 0;
    const onMove = (e) => {
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = (e.clientX - cx) / rect.width;
      const dy = (e.clientY - cy) / rect.height;
      const maxTilt = 14;
      const ry = Math.max(-1, Math.min(1, dx)) * maxTilt;
      const rx = -Math.max(-1, Math.min(1, dy)) * maxTilt;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setTilt({ rx, ry }));
    };
    const onLeave = () => setTilt({ rx: 0, ry: 0 });
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseleave', onLeave);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseleave', onLeave);
      cancelAnimationFrame(raf);
    };
  }, [variant]);

  const isHero = variant === 'hero';

  return (
    <div
      ref={wrapRef}
      className={`logo3d-wrap relative inline-block select-none ${className}`}
      style={{ perspective: '1100px' }}
    >
      {/* Soft cinematic halo behind the logo */}
      {isHero && (
        <>
          <span
            aria-hidden
            className="absolute inset-0 -m-10 rounded-full blur-3xl logo3d-halo-pulse pointer-events-none"
            style={{
              background: isDark
                ? 'radial-gradient(circle, rgba(168,217,107,0.45) 0%, rgba(168,217,107,0.10) 45%, transparent 70%)'
                : 'radial-gradient(circle, rgba(127,184,74,0.30) 0%, rgba(127,184,74,0.06) 45%, transparent 70%)',
            }}
          />
          {/* concentric ring */}
          <span
            aria-hidden
            className="absolute inset-0 -m-6 rounded-full logo3d-ring-spin pointer-events-none"
            style={{
              border: isDark
                ? '1px dashed rgba(168,217,107,0.30)'
                : '1px dashed rgba(127,184,74,0.30)',
            }}
          />
          {/* secondary slow ring */}
          <span
            aria-hidden
            className="absolute inset-0 -m-12 rounded-full logo3d-ring-spin-rev pointer-events-none"
            style={{
              border: isDark
                ? '1px dashed rgba(212,175,55,0.18)'
                : '1px dashed rgba(212,175,55,0.18)',
            }}
          />
        </>
      )}

      {/* 3D tilting stage */}
      <div
        className={`logo3d-stage relative ${isHero ? 'logo3d-float' : ''}`}
        style={{
          transformStyle: 'preserve-3d',
          transform: `rotateX(${tilt.rx}deg) rotateY(${tilt.ry}deg)`,
          transition: 'transform 240ms cubic-bezier(0.2, 0.8, 0.2, 1)',
        }}
      >
        {/* Back depth layer — slightly offset & blurred copy for parallax */}
        {isHero && (
          <img
            src={LOGO_URL}
            alt=""
            aria-hidden
            className={`absolute inset-0 ${heightClass} w-auto opacity-40 logo3d-back`}
            style={{
              transform: 'translateZ(-30px) scale(1.04)',
              filter: isDark
                ? 'invert(1) hue-rotate(180deg) blur(8px) brightness(1.3) drop-shadow(0 0 40px rgba(168,217,107,0.55))'
                : 'blur(6px) brightness(1.1) drop-shadow(0 0 25px rgba(127,184,74,0.4))',
            }}
          />
        )}

        {/* Front sharp logo with cinematic drop-shadow */}
        <img
          src={LOGO_URL}
          alt="GANOH Café Bistrô"
          className={`relative ${heightClass} w-auto logo3d-front`}
          style={{
            transform: 'translateZ(20px)',
            filter: isDark
              ? (isHero
                  ? 'invert(1) hue-rotate(180deg) brightness(1.18) contrast(1.05) drop-shadow(0 6px 12px rgba(0,0,0,0.6)) drop-shadow(0 0 24px rgba(168,217,107,0.6)) drop-shadow(0 0 6px rgba(212,175,55,0.4))'
                  : 'invert(1) hue-rotate(180deg) brightness(1.25) drop-shadow(0 2px 6px rgba(0,0,0,0.65)) drop-shadow(0 0 12px rgba(168,217,107,0.55))')
              : 'contrast(1.06) saturate(1.06) drop-shadow(0 4px 8px rgba(0,0,0,0.16)) drop-shadow(0 0 14px rgba(127,184,74,0.32))',
          }}
        />

        {/* Specular shimmer pass — slides across the logo */}
        {isHero && (
          <span
            aria-hidden
            className="absolute inset-0 logo3d-shimmer pointer-events-none"
            style={{
              transform: 'translateZ(35px)',
              background:
                'linear-gradient(115deg, transparent 30%, rgba(255,255,255,0.55) 47%, rgba(255,247,210,0.85) 50%, rgba(255,255,255,0.55) 53%, transparent 70%)',
              mixBlendMode: isDark ? 'overlay' : 'soft-light',
              maskImage: `url(${LOGO_URL})`,
              WebkitMaskImage: `url(${LOGO_URL})`,
              maskSize: 'contain',
              WebkitMaskSize: 'contain',
              maskRepeat: 'no-repeat',
              WebkitMaskRepeat: 'no-repeat',
              maskPosition: 'center',
              WebkitMaskPosition: 'center',
            }}
          />
        )}
      </div>

      {/* Floor reflection — gives it weight, true 3D feel */}
      {isHero && (
        <span
          aria-hidden
          className="block absolute left-1/2 -translate-x-1/2 opacity-50 pointer-events-none"
          style={{
            top: '92%',
            width: '70%',
            height: '36%',
            background: `url(${LOGO_URL}) center/contain no-repeat`,
            transform: 'scaleY(-1)',
            maskImage: 'linear-gradient(to bottom, rgba(0,0,0,0.45), transparent 70%)',
            WebkitMaskImage: 'linear-gradient(to bottom, rgba(0,0,0,0.45), transparent 70%)',
            filter: isDark
              ? 'invert(1) hue-rotate(180deg) brightness(1.4) blur(2px)'
              : 'brightness(1) blur(1.5px)',
          }}
        />
      )}
    </div>
  );
};

export default Logo3D;
