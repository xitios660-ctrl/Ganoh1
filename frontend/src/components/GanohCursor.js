import React, { useEffect, useRef, useState } from 'react';

/**
 * GanohCursor - cinematic custom cursor (ring + dot).
 * Disabled on touch devices. Detects interactive elements to enlarge.
 */
export const GanohCursor = () => {
  const ringRef = useRef(null);
  const dotRef = useRef(null);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    // Disable on coarse pointers (mobile/tablet)
    const mq = window.matchMedia('(pointer: fine)');
    setEnabled(mq.matches);
    const onChange = (e) => setEnabled(e.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let raf;
    let tx = 0, ty = 0, rx = 0, ry = 0, dx = 0, dy = 0;

    const onMove = (e) => { tx = e.clientX; ty = e.clientY; };
    const onOver = (e) => {
      const tag = e.target?.tagName?.toLowerCase();
      const interactive = e.target?.closest?.('a, button, [role="button"], input, select, textarea, [data-cursor="hover"], .group');
      if (interactive || ['a', 'button', 'input', 'select', 'textarea'].includes(tag)) {
        ringRef.current?.classList.add('is-hover');
      } else {
        ringRef.current?.classList.remove('is-hover');
      }
    };

    const loop = () => {
      // Lerp ring slower for trailing effect
      rx += (tx - rx) * 0.18;
      ry += (ty - ry) * 0.18;
      dx += (tx - dx) * 0.45;
      dy += (ty - dy) * 0.45;
      if (ringRef.current) ringRef.current.style.transform = `translate(${rx}px, ${ry}px) translate(-50%, -50%)`;
      if (dotRef.current) dotRef.current.style.transform = `translate(${dx}px, ${dy}px) translate(-50%, -50%)`;
      raf = requestAnimationFrame(loop);
    };

    window.addEventListener('mousemove', onMove, { passive: true });
    window.addEventListener('mouseover', onOver, { passive: true });
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseover', onOver);
    };
  }, [enabled]);

  if (!enabled) return null;

  return (
    <>
      <div ref={ringRef} className="ganoh-cursor" data-testid="ganoh-cursor" />
      <div ref={dotRef} className="ganoh-cursor-dot" />
    </>
  );
};

export default GanohCursor;
