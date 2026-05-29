import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';

const ThemeContext = createContext({ theme: 'light', toggleTheme: () => {} });

const USER_PREF_KEY = 'ganoh_theme_user';     // set only when the user explicitly toggles
const LEGACY_KEY = 'ganoh_theme';             // older app version key — preserved as fallback

// Routes that should default to DARK theme on first visit (cardápio / menu pages)
const isMenuPath = (path) => {
  if (!path) return false;
  if (!/^\/(runner|gym-londres)(\/|$)/.test(path)) return false;
  if (path.endsWith('/cozinha')) return false;
  if (path.endsWith('/estoque')) return false;
  if (path.endsWith('/live')) return false;
  if (path.includes('/pedido/')) return false;
  return true;
};

const getInitialTheme = () => {
  try {
    // Highest priority: explicit user choice
    const userPref = localStorage.getItem(USER_PREF_KEY);
    if (userPref === 'dark' || userPref === 'light') return userPref;
    // Legacy fallback only respected on non-menu paths so that menu pages always
    // default to DARK on a fresh entry until the user manually toggles.
    const legacy = localStorage.getItem(LEGACY_KEY);
    const path = typeof window !== 'undefined' ? window.location.pathname : '/';
    if (isMenuPath(path)) return 'dark';
    if (legacy === 'dark' || legacy === 'light') return legacy;
    return 'light';
  } catch {
    return 'light';
  }
};

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(getInitialTheme);
  const overlayRef = useRef(null);
  const [transitioning, setTransitioning] = useState(false);
  const userHasToggledRef = useRef(false);

  // Apply theme class to <html>
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    // Only persist as USER preference if the user has toggled explicitly.
    // We still write the legacy key so other parts of the app keep working.
    try {
      localStorage.setItem(LEGACY_KEY, theme);
      if (userHasToggledRef.current) {
        localStorage.setItem(USER_PREF_KEY, theme);
      }
    } catch (e) { /* ignore */ }
  }, [theme]);

  // React to in-app navigation: if user hasn't toggled yet, switch theme to the
  // path's natural default (dark on menu pages, light elsewhere).
  useEffect(() => {
    const onNav = () => {
      if (userHasToggledRef.current) return;
      try {
        if (localStorage.getItem(USER_PREF_KEY)) return; // user has explicit pref
      } catch { /* ignore */ }
      const next = isMenuPath(window.location.pathname) ? 'dark' : 'light';
      setTheme((cur) => (cur === next ? cur : next));
    };
    window.addEventListener('popstate', onNav);
    const _push = window.history.pushState;
    const _replace = window.history.replaceState;
    window.history.pushState = function (...args) {
      _push.apply(this, args);
      onNav();
    };
    window.history.replaceState = function (...args) {
      _replace.apply(this, args);
      onNav();
    };
    return () => {
      window.removeEventListener('popstate', onNav);
      window.history.pushState = _push;
      window.history.replaceState = _replace;
    };
  }, []);

  // Triggered by click on toggle button — origin is { x, y } of the click
  const toggleTheme = useCallback((origin) => {
    if (transitioning) return;
    setTransitioning(true);
    userHasToggledRef.current = true;

    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    const targetColor = nextTheme === 'dark' ? '#0a0a0a' : '#fafaf7';

    // Build overlay if not present
    let overlay = overlayRef.current;
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.style.position = 'fixed';
      overlay.style.inset = '0';
      overlay.style.zIndex = '99999';
      overlay.style.pointerEvents = 'none';
      overlay.style.willChange = 'clip-path';
      document.body.appendChild(overlay);
      overlayRef.current = overlay;
    }

    const { x = window.innerWidth / 2, y = 0 } = origin || {};
    const maxRadius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y)
    );

    // Stage 1: water drop falling - tiny circle at top expands gently
    overlay.style.background = `radial-gradient(circle at center, ${targetColor} 70%, ${targetColor}cc 100%)`;
    overlay.style.transition = 'none';
    overlay.style.clipPath = `circle(0px at ${x}px ${y}px)`;
    // Force reflow
    // eslint-disable-next-line no-unused-expressions
    overlay.offsetHeight;

    // Stage 2: ripple expands across the screen
    overlay.style.transition = 'clip-path 850ms cubic-bezier(0.65, 0, 0.35, 1)';
    overlay.style.clipPath = `circle(${maxRadius}px at ${x}px ${y}px)`;

    // After ripple completes, swap theme and fade out overlay
    const onEnd = () => {
      overlay.removeEventListener('transitionend', onEnd);
      setTheme(nextTheme);
      // Tiny delay so React applies the theme class before fade-out
      requestAnimationFrame(() => {
        overlay.style.transition = 'opacity 250ms ease-out';
        overlay.style.opacity = '0';
        setTimeout(() => {
          overlay.style.opacity = '1';
          overlay.style.clipPath = `circle(0px at ${x}px ${y}px)`;
          setTransitioning(false);
        }, 280);
      });
    };
    overlay.addEventListener('transitionend', onEnd);
  }, [theme, transitioning]);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, transitioning }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
