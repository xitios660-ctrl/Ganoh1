import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

/**
 * KitchenStage3D - Cinematic interactive 3D stage using vanilla Three.js
 * (Bypasses React-Three-Fiber React 19 compat issues).
 * 
 * Features:
 *  - Rotating glass torus knot (the "ring of focus")
 *  - Floating glowing orbs that react to mouse
 *  - Particle starfield + sparkles drifting upward
 *  - Cinematic vignette, scanlines, film grain
 *  - Auto-pause when tab not visible
 */

const BRAND = 0xa8d96b;
const BRAND_DEEP = 0x7cb342;
const ACCENT_GOLD = 0xe9c46a;

export const KitchenStage3D = () => {
  const containerRef = useRef(null);
  const animRef = useRef(null);
  const cleanupRef = useRef(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;

    // === Scene ===
    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x040806, 6, 22);

    // === Camera ===
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 100);
    camera.position.set(0, 0, 8);

    // === Renderer ===
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(width, height);
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    // === Lights ===
    scene.add(new THREE.AmbientLight(0xffffff, 0.25));
    const l1 = new THREE.PointLight(BRAND, 1.2, 30);
    l1.position.set(-6, 4, 5);
    scene.add(l1);
    const l2 = new THREE.PointLight(ACCENT_GOLD, 0.7, 30);
    l2.position.set(6, -3, 4);
    scene.add(l2);
    const l3 = new THREE.PointLight(0x3d7a1a, 0.6, 30);
    l3.position.set(0, 6, -4);
    scene.add(l3);

    // === Torus Knot ring (centerpiece) - pushed back ===
    const ringGeo = new THREE.TorusKnotGeometry(1.2, 0.12, 180, 28);
    const ringMat = new THREE.MeshStandardMaterial({
      color: BRAND,
      emissive: BRAND,
      emissiveIntensity: 0.45,
      roughness: 0.12,
      metalness: 0.95,
      transparent: true,
      opacity: 0.35,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(0, 0, -8);
    ring.scale.setScalar(1.2);
    scene.add(ring);

    // === Wireframe ico in center ===
    const wireGeo = new THREE.IcosahedronGeometry(1, 2);
    const wireMat = new THREE.MeshBasicMaterial({
      color: BRAND,
      wireframe: true,
      transparent: true,
      opacity: 0.18,
    });
    const wire = new THREE.Mesh(wireGeo, wireMat);
    wire.position.set(0, 0, -7);
    wire.scale.setScalar(1.0);
    scene.add(wire);

    // === Floating Glow Orbs - smaller, more diffuse, pushed back ===
    const orbConfigs = [
      { pos: [-6.2, 2.4, -8], color: BRAND, scale: 0.35, speed: 1.1 },
      { pos: [6.4, -2.1, -9], color: BRAND_DEEP, scale: 0.45, speed: 0.8 },
      { pos: [-5.5, -3.0, -10], color: ACCENT_GOLD, scale: 0.25, speed: 1.3 },
      { pos: [5.8, 3.2, -11], color: BRAND, scale: 0.3, speed: 0.9 },
      { pos: [-2.8, 4.2, -12], color: BRAND_DEEP, scale: 0.22, speed: 1.0 },
      { pos: [3.2, -4.0, -11], color: ACCENT_GOLD, scale: 0.2, speed: 1.4 },
    ];
    const orbs = orbConfigs.map((cfg) => {
      const geo = new THREE.IcosahedronGeometry(1, 1);
      const mat = new THREE.MeshStandardMaterial({
        color: cfg.color,
        emissive: cfg.color,
        emissiveIntensity: 0.85,
        roughness: 0.2,
        metalness: 0.85,
        transparent: true,
        opacity: 0.55,
      });
      const m = new THREE.Mesh(geo, mat);
      m.position.set(cfg.pos[0], cfg.pos[1], cfg.pos[2]);
      m.scale.setScalar(cfg.scale);
      m.userData = { basePos: [...cfg.pos], speed: cfg.speed };
      scene.add(m);
      return m;
    });

    // === Particle field (sparkles + stars) ===
    const buildPoints = (count, range, size, color, opacity) => {
      const arr = new Float32Array(count * 3);
      for (let i = 0; i < count; i++) {
        arr[i * 3] = (Math.random() - 0.5) * range[0];
        arr[i * 3 + 1] = (Math.random() - 0.5) * range[1];
        arr[i * 3 + 2] = (Math.random() - 0.5) * range[2] - 4;
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(arr, 3));
      const mat = new THREE.PointsMaterial({
        color,
        size,
        sizeAttenuation: true,
        transparent: true,
        opacity,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      return new THREE.Points(geo, mat);
    };
    const sparklesGreen = buildPoints(180, [16, 10, 12], 0.06, BRAND, 0.7);
    scene.add(sparklesGreen);
    const sparklesGold = buildPoints(90, [14, 8, 10], 0.05, ACCENT_GOLD, 0.5);
    scene.add(sparklesGold);
    const stars = buildPoints(900, [60, 40, 30], 0.03, 0xffffff, 0.5);
    scene.add(stars);

    // === Mouse parallax ===
    let mouseX = 0, mouseY = 0;
    let targetMouseX = 0, targetMouseY = 0;
    const onMove = (e) => {
      targetMouseX = (e.clientX / window.innerWidth - 0.5) * 2;
      targetMouseY = (e.clientY / window.innerHeight - 0.5) * 2;
    };
    window.addEventListener('mousemove', onMove, { passive: true });

    // === Resize ===
    const onResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', onResize);

    // === Visibility pause ===
    let paused = false;
    const onVis = () => { paused = document.hidden; };
    document.addEventListener('visibilitychange', onVis);

    // === Animate ===
    const clock = new THREE.Clock();
    const tick = () => {
      animRef.current = requestAnimationFrame(tick);
      if (paused) return;
      const t = clock.getElapsedTime();

      // Camera parallax
      mouseX += (targetMouseX - mouseX) * 0.04;
      mouseY += (targetMouseY - mouseY) * 0.04;
      camera.position.x = mouseX * 1.2;
      camera.position.y = mouseY * 0.8;
      camera.lookAt(0, 0, 0);

      // Ring rotation
      ring.rotation.x = t * 0.08;
      ring.rotation.y = t * 0.12;
      ring.rotation.z = Math.sin(t * 0.3) * 0.15;

      // Wireframe
      wire.rotation.x = t * 0.2;
      wire.rotation.y = t * 0.15;

      // Orbs: float + rotate
      orbs.forEach((m) => {
        const { basePos, speed } = m.userData;
        m.position.y = basePos[1] + Math.sin(t * 0.6 * speed + basePos[0]) * 0.45;
        m.position.x = basePos[0] + Math.cos(t * 0.4 * speed + basePos[1]) * 0.25;
        m.rotation.x = t * 0.15 * speed;
        m.rotation.y = t * 0.2 * speed;
      });

      // Particles drift
      sparklesGreen.rotation.y = t * 0.04;
      sparklesGreen.rotation.x = Math.sin(t * 0.1) * 0.05;
      sparklesGold.rotation.y = -t * 0.03;
      stars.rotation.y = t * 0.01;

      renderer.render(scene, camera);
    };
    tick();

    cleanupRef.current = () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVis);
      renderer.dispose();
      ringGeo.dispose();
      ringMat.dispose();
      wireGeo.dispose();
      wireMat.dispose();
      orbs.forEach((m) => { m.geometry.dispose(); m.material.dispose(); });
      [sparklesGreen, sparklesGold, stars].forEach((p) => { p.geometry.dispose(); p.material.dispose(); });
      if (renderer.domElement.parentNode === container) container.removeChild(renderer.domElement);
    };

    return cleanupRef.current;
  }, []);

  return (
    <div className="fixed inset-0 -z-10 pointer-events-none overflow-hidden" data-testid="kitchen-stage-3d">
      {/* Vanilla Three.js canvas mount */}
      <div
        ref={containerRef}
        className="absolute inset-0"
        style={{ background: 'radial-gradient(ellipse at center, #0a1410 0%, #050805 60%, #000000 100%)' }}
      />

      {/* Cinematic overlays */}
      <div className="absolute inset-0 pointer-events-none" style={{
        background: 'radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.55) 100%)'
      }} />
      <div className="absolute inset-0 pointer-events-none opacity-[0.04] mix-blend-overlay" style={{
        backgroundImage: "repeating-linear-gradient(0deg, transparent 0, transparent 2px, rgba(255,255,255,0.05) 2px, rgba(255,255,255,0.05) 3px)"
      }} />
      <div className="absolute inset-0 pointer-events-none opacity-[0.06] mix-blend-overlay" style={{
        backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")"
      }} />
    </div>
  );
};

export default KitchenStage3D;
