import React, { useRef, useState } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';

/**
 * Tilt3DCard - real 3D mouse-aware tilt with depth shadow + shine sweep.
 */
export const Tilt3DCard = ({ children, className = '', depth = 14, accent = '#a8d96b', testId, onClick, glare = true, scale = 1.02 }) => {
  const ref = useRef(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const sx = useSpring(x, { stiffness: 220, damping: 22 });
  const sy = useSpring(y, { stiffness: 220, damping: 22 });
  const rotY = useTransform(sx, [-0.5, 0.5], [depth, -depth]);
  const rotX = useTransform(sy, [-0.5, 0.5], [-depth, depth]);
  const glareBg = useTransform(
    [sx, sy],
    ([gx, gy]) => `radial-gradient(circle at ${(0.5 - gx) * 100}% ${(0.5 - gy) * 100}%, ${accent}55, transparent 45%)`
  );

  const [hovered, setHovered] = useState(false);

  const handleMove = (e) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    x.set((e.clientX - rect.left) / rect.width - 0.5);
    y.set((e.clientY - rect.top) / rect.height - 0.5);
  };
  const handleLeave = () => { x.set(0); y.set(0); setHovered(false); };

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={handleLeave}
      onClick={onClick}
      whileTap={{ scale: 0.98 }}
      animate={{ scale: hovered ? scale : 1 }}
      style={{ rotateX: rotX, rotateY: rotY, transformStyle: 'preserve-3d', perspective: 1200 }}
      transition={{ type: 'spring', stiffness: 200, damping: 20 }}
      className={`relative will-change-transform ${className}`}
      data-testid={testId}
    >
      {children}
      {glare && (
        <motion.div
          className="pointer-events-none absolute inset-0 rounded-[inherit] mix-blend-overlay transition-opacity duration-300"
          style={{
            background: glareBg,
            opacity: hovered ? 1 : 0,
          }}
        />
      )}
    </motion.div>
  );
};

export default Tilt3DCard;
